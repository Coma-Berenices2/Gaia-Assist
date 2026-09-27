"""Experimental temperature policy. No catalogue I/O or GUI dependencies.

Casagrande et al. 2021: doi:10.1093/mnras/stab2304, author's DR3 colte.py.
Application screens and assumptions are deliberately separate from formulas.
"""
from dataclasses import dataclass
import math
import random

VERSION = "temperature-comparison-2.5"


def number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (ValueError, TypeError, OverflowError):
        return None


def bounds(value, low, high):
    value, low, high = map(number, (value, low, high))
    if None in (value, low, high) or not low <= value <= high:
        return None
    return value - low, high - value


@dataclass(frozen=True)
class TemperatureOptions:
    distance_mode: str = "Automatic"
    distance_auto_threshold: float = 0.10
    method: str = "Casagrande2021"
    population: str = "auto"
    population_reason: str = ""
    metallicity_mode: str = "solar"
    feh: float | None = None
    feh_error: float | None = None
    metallicity_source: str = ""
    metallicity_vetted: bool = False
    blue_metallicity_cutoff: float = 0.35
    allow_explorer_fallback: bool = True
    zero_reddening: bool = False
    override: str = "auto"
    override_reason: str = ""
    min_snr: float = 20.0
    excess_nsigma: float = 3.0
    wide_interval: float = 0.05
    disagreement_k: float = 300.0
    disagreement_fraction: float = 0.05

    def __post_init__(self):
        if number(self.distance_auto_threshold) is None or not 0 < self.distance_auto_threshold <= 1:
            raise ValueError("Distance threshold must be a fraction greater than 0 and at most 1")
        for field, allowed in (
            ("distance_mode", {"Baseline", "Bayesian geometric", "Automatic"}),
            ("method", {"Casagrande2021", "Mucciarelli2021"}),
            ("population", {"auto", "dwarf", "giant"}),
            ("metallicity_mode", {"solar", "trusted", "raw_gaia"}),
            ("override", {"auto", "Gaia GSP-Phot", "Gaia ESP-HS", "BP-RP"}),
        ):
            if getattr(self, field) not in allowed:
                raise ValueError(f"Invalid {field}")
        if self.population != "auto" and not self.population_reason.strip():
            raise ValueError("Record the evidence for the population assumption.")
        if self.override != "auto" and not self.override_reason.strip():
            raise ValueError("Record a reason for the temperature override.")
        if self.metallicity_mode == "trusted" and (
            number(self.feh) is None or not self.metallicity_source.strip()
        ):
            raise ValueError("Trusted [Fe/H] requires a finite value and its provenance.")
        if self.feh_error is not None and (number(self.feh_error) is None or self.feh_error < 0):
            raise ValueError("[Fe/H] uncertainty must be finite and nonnegative.")
        if number(self.blue_metallicity_cutoff) is None or not 0 <= self.blue_metallicity_cutoff <= 2.55:
            raise ValueError("Blue metallicity cutoff must be between 0 and 2.55 (0 disables the screen).")
        for key in ("min_snr", "excess_nsigma", "wide_interval", "disagreement_k", "disagreement_fraction"):
            if number(getattr(self, key)) is None or getattr(self, key) <= 0:
                raise ValueError(f"{key} must be finite and positive")


def casagrande_value(c, h, z):
    a = 7980.8845 - 4138.3457*c + 1264.9366*c*c - 130.4388*c**3
    b = 285.8393 - 324.2196*c + 106.8511*c*c - 4.9825*c**3
    d = 4.5138 - 203.7774*c + 126.6981*c*c - 14.7442*c**3
    return a + h*b + z*d + 40.7376*z*h*c


def casagrande_in_domain(c, h, z):
    c, h, z = map(number, (c, h, z))
    return (None not in (c, h, z) and 0 <= h <= 4.8 and -3 <= z <= .6
            and .2 <= c <= (2.0 if h > 3.2 else 2.55))


def casagrande_gradient(c, h, z):
    return (
        -4138.3457 + 2*1264.9366*c - 3*130.4388*c*c
        + h*(-324.2196 + 2*106.8511*c - 3*4.9825*c*c)
        + z*(-203.7774 + 2*126.6981*c - 3*14.7442*c*c) + 40.7376*z*h,
        285.8393 - 324.2196*c + 106.8511*c*c - 4.9825*c**3 + 40.7376*z*c,
        4.5138 - 203.7774*c + 126.6981*c*c - 14.7442*c**3 + 40.7376*h*c,
    )


def casagrande_uncertainty(c, h, z, covariance=None):
    """Conditional local error including supplied covariance; unknown stays None."""
    if covariance is None:
        return None
    import numpy as np
    cov = np.asarray(covariance, dtype=float)
    if (cov.shape != (3, 3) or not np.isfinite(cov).all()
            or not np.allclose(cov, cov.T) or np.linalg.eigvalsh(cov).min() < -1e-12):
        raise ValueError("Covariance must be finite, symmetric and positive semidefinite")
    gradient = np.asarray(casagrande_gradient(c, h, z))
    return math.sqrt(max(0, float(gradient @ cov @ gradient)) + 55**2 + 20**2)


def casagrande_estimate(c, h, z, *, population_supported=False, errors=None):
    """Errors are (lower, upper) widths for C,h,z, including reddening in C.

    Split-normal Monte Carlo approximates asymmetric catalogue intervals. Unknown
    covariances are NOT inferred from these intervals. Out-of-domain draws are
    counted, never clipped or extrapolated; >5% suppresses the formal interval.
    """
    result = {"temperature": None, "method": "Casagrande2021 BP-RP", "eligible": False,
              "uncertainty": None, "lower": None, "upper": None, "concerns": [], "status": "unavailable"}
    if any(number(value) is None for value in (c, h, z)):
        missing = [label for label, value in zip(("intrinsic BP-RP", "gravity", "composition"), (c, h, z)) if number(value) is None]
        result["concerns"].append("Missing usable " + ", ".join(missing))
        return result
    if not casagrande_in_domain(c, h, z):
        result["status"] = "outside_domain"
        limit = 2.0 if h > 3.2 else 2.55
        result["concerns"].append(f"Outside calibration colour domain 0.20–{limit:.2f}, or application limits logg 0–4.8 / Fe/H -3–0.6; no extrapolation")
        return result
    t = casagrande_value(c, h, z)
    if not 3600 <= t <= 9000:
        result["status"] = "outside_domain"
        result["concerns"].append("Outside approximate fitted temperature population (3600–9000 K)")
        return result
    result.update(temperature=t, eligible=population_supported, status="conditional" if population_supported else "needs_review")
    if not population_supported:
        result["concerns"].append("Population hypothesis unconfirmed")
    if not 4000 <= t <= 6700:
        result["concerns"].append("Outside independently validated 4000–6700 K interval")
    if errors is None or any(e is None for e in errors):
        result["concerns"].append("Input uncertainty missing; total temperature uncertainty unknown")
        return result
    if len(errors) != 3 or any(len(e) != 2 or any(number(v) is None or v < 0 for v in e) for e in errors):
        raise ValueError("Three finite, nonnegative asymmetric input errors required")
    rng = random.Random(1729)
    samples = []
    for _ in range(2048):
        draw = []
        for center, (lo, hi) in zip((c, h, z), errors):
            q = rng.gauss(0, 1)
            draw.append(center + q*(lo if q < 0 else hi))
        if casagrande_in_domain(*draw):
            td = casagrande_value(*draw)
            if 3600 <= td <= 9000:
                samples.append(td + rng.gauss(0, math.hypot(55, 20)))
    rejected = 1 - len(samples)/2048
    result["rejected_draw_fraction"] = rejected
    result["concerns"].append("Conditional Monte Carlo: unprovided input correlations omitted; formal error is not total accuracy")
    if rejected > .05:
        result["concerns"].append("Uncertainty crosses calibration boundary; interval withheld")
    elif samples:
        samples.sort()
        lo, hi = samples[int(.16*(len(samples)-1))], samples[int(.84*(len(samples)-1))]
        result.update(lower=lo, upper=hi, uncertainty=(hi-lo)/2)
    return result


def red_dwarf_screen(c, mv, reliable=False):
    if number(c) is None or number(mv) is None:
        return "uncertain (intrinsic colour or estimated Mv unavailable)"
    candidate = c > 1.8 and mv > 8.69
    if not reliable:
        return "uncertain " + ("candidate" if candidate else "screen") + " (distance/extinction/V transformation)"
    return "candidate (heuristic)" if candidate else "not selected; does not rule out a dwarf or brighter binary"


def select_adopted_temperature(gaia, colour, *, shared_concerns=(), options=None, gaia_candidates=None):
    """Single deterministic selection policy; eligibility is separate from quality."""
    options = options or TemperatureOptions()
    def eligible(e):
        t = number(e.get("temperature"))
        return bool(e.get("eligible") and t is not None and t > 0)
    ge, ce = eligible(gaia), eligible(colour)
    gaia_source = gaia.get("source", "Gaia GSP-Phot")
    issues = list(shared_concerns)
    issues += gaia.get("concerns", [])
    issues += colour.get("concerns", [])
    conflict = ge and ce and abs(gaia["temperature"]-colour["temperature"]) > max(
        options.disagreement_k,
        options.disagreement_fraction*(gaia["temperature"]+colour["temperature"])/2,
    )
    if conflict:
        issues.append("Significant Gaia/colour disagreement")
    if not ge and not ce:
        source = None
        reason = (gaia.get("unavailable_reason", "No eligible Gaia temperature") + "; BP-RP: "
                  + colour.get("unavailable_reason", "no applicable estimate; see calculation details"))
    elif ge and not ce:
        source, reason = gaia_source, f"Only {gaia_source} temperature is eligible"
    elif ce and not ge:
        source, reason = "BP-RP", "Only the supported colour estimate is eligible"
    elif shared_concerns:
        source, reason = gaia_source, "Shared concerns; retain Gaia provisionally (see review notes)"
    elif gaia.get("specific_issues") and colour.get("preferential"):
        source, reason = "BP-RP", "Valid colour method preferred because Gaia has: " + "; ".join(gaia["specific_issues"])
    elif conflict:
        source, reason = gaia_source, "Unresolved disagreement; retain Gaia provisionally, do not average"
    else:
        source, reason = gaia_source, "Default preference for Gaia BP/RP spectral fit; retain colour comparison"
    candidates = {gaia_source: gaia, "BP-RP": colour, **(gaia_candidates or {})}
    if options.override != "auto":
        allowed = eligible(candidates.get(options.override, {}))
        if allowed:
            source, reason = options.override, "User override: " + options.override_reason.strip()
        else:
            issues.append("Requested override is ineligible and was not applied")
    chosen = candidates.get(source, {})
    status = "unavailable" if source is None else "estimated"
    if source == "BP-RP":
        status = "approximate" if colour.get("approximate") else "conditional"
    # An explained Gaia-specific problem is resolved by a strong colour estimate.
    unresolved = shared_concerns or (conflict and not (source == "BP-RP" and colour.get("preferential") and gaia.get("specific_issues")))
    if source and (unresolved or chosen.get("review") or (source != "BP-RP" and chosen.get("specific_issues"))):
        status = "needs_review"
    issues += chosen.get("concerns", [])
    return {"effective_temperature": chosen.get("temperature") if source else None,
            "adopted_temperature_source": source, "temperature_selection_reason": reason,
            "temperature_status": status, "temperature_concerns": "; ".join(dict.fromkeys(issues)) or "None identified by application screens",
            "temperature_override_reason": options.override_reason if options.override != "auto" else None}


def evaluate_temperatures(source, context, options=None):
    # Imported at call time to keep the formula/selection helpers independent.
    from temperature_evaluation import evaluate_temperatures as evaluate
    return evaluate(source, context, options)
