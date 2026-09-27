"""Temperature/photometry building blocks for Gaia Assist (2026-09-17).

This is a reference module, not an automatic stellar classifier.
Callers must establish photometric quality, extinction and stellar class.
No Gaia metallicity or missing extinction is silently accepted as truth.
See IMPLEMENTATION_GUIDE.md for provenance, routing and limitations.
Python standard library only.
"""
from dataclasses import dataclass
from bisect import bisect_right
import math


@dataclass(frozen=True)
class TemperatureEstimate:
    teff_k: float | None
    uncertainty_k: float | None
    method: str
    status: str
    notes: tuple[str, ...] = ()


def _finite(*values):
    try:
        return all(v is not None and math.isfinite(float(v)) for v in values)
    except (TypeError, ValueError, OverflowError):
        return False


def _unavailable(method, reason):
    return TemperatureEstimate(None, None, method, "unavailable", (reason,))


# Mucciarelli, Bellazzini & Massari (2021), Table 1.
# (colour lower, colour upper, residual scatter in K, b0...b5).
# Intrinsic (dereddened) EDR3/DR3 colours; Fe/H approximately -4 to 0.
MB21 = {
    ("dwarf", "bp_rp"): (.39, 1.50, 61., (.4929, .5092, -.0353, .0192, -.0020, -.0395)),
    ("giant", "bp_rp"): (.33, 1.81, 83., (.5323, .4775, -.0344, -.0110, -.0020, -.0009)),
    ("dwarf", "g_rp"): (.25, .81, 62., (.5050, .6532, .2284, .0260, -.0011, -.0726)),
    ("giant", "g_rp"): (.22, .92, 71., (.5472, .5914, .2347, -.0119, -.0012, .0060)),
}


def mb21_temperature(colour0, feh, *, stellar_class, colour_name="bp_rp",
                     sigma_colour0=None, sigma_feh=None,
                     covariance_colour_feh=0., metallicity_source="unspecified"):
    """Return an explicitly conditional estimate; never extrapolate/clamp.

    sigma_colour0 must INCLUDE reddening uncertainty. Formal error propagation
    assumes locally Gaussian errors; near a domain boundary use Monte Carlo.
    Class must be supplied: the paper's split is logg >3 versus logg <3.
    'dwarf' is a calibration bin, not proof of luminosity class V.
    feh is a vetted measurement or an explicitly labelled adopted value.
    Unknown errors produce uncertainty=None, not a zero-error estimate.
    """
    method = f"MB21_{stellar_class}_{colour_name}"
    key = (stellar_class, colour_name)
    if key not in MB21:
        return _unavailable(method, "Unknown/ambiguous calibration class or colour")
    if not _finite(colour0, feh):
        return _unavailable(method, "Missing/non-finite intrinsic colour or Fe/H")
    c, z = float(colour0), float(feh)
    lo, hi, scatter, b = MB21[key]
    if not lo <= c <= hi:
        return _unavailable(method, f"Intrinsic colour outside [{lo}, {hi}]")
    if not -4. <= z <= 0.:
        return _unavailable(method, "Fe/H outside adopted calibration range [-4, 0]")
    b0, b1, b2, b3, b4, b5 = b
    theta = b0 + b1*c + b2*c*c + b3*z + b4*z*z + b5*z*c
    if theta <= 0.:
        return _unavailable(method, "Non-positive inverse temperature")
    t = 5040. / theta
    notes = [f"Metallicity input: {metallicity_source}",
             "Conditional on supplied stellar class, reddening and Fe/H"]
    if sigma_colour0 is None or sigma_feh is None:
        notes.append("Total uncertainty unavailable; colour and Fe/H errors required")
        return TemperatureEstimate(t, None, method, "conditional", tuple(notes))
    if not _finite(sigma_colour0, sigma_feh, covariance_colour_feh):
        return _unavailable(method, "Non-finite uncertainty/covariance")
    sc, sz, cov = map(float, (sigma_colour0, sigma_feh, covariance_colour_feh))
    if sc < 0 or sz < 0 or abs(cov) > sc*sz + 1.e-15:
        return _unavailable(method, "Invalid uncertainties/covariance")
    factor = -5040. / theta**2
    dc = factor * (b1 + 2.*b2*c + b5*z)
    dz = factor * (b3 + 2.*b4*z + b5*c)
    variance = dc**2*sc**2 + dz**2*sz**2 + 2.*dc*dz*cov + scatter**2
    if c-sc < lo or c+sc > hi or z-sz < -4. or z+sz > 0.:
        notes.append("Uncertainty crosses calibration boundary; do not clip Monte Carlo draws")
    if metallicity_source == "unspecified":
        notes.append("Specify whether Fe/H is measured, calibrated or assumed")
    return TemperatureEstimate(t, math.sqrt(max(0., variance)), method,
                               "conditional", tuple(notes))


def mann_vjh_temperature(v0, j0, h0, *, dwarf_population_verified=False,
                         sigma_v0=None, sigma_j0=None, sigma_h0=None):
    """Mann et al. (2015), corrected Table 2 (2016 erratum), V-J plus J-H.

    Use actual Johnson V and 2MASS J,H after extinction correction.
    Guard 3.5<=V-J<=6.0 and .5<=J-H<=.7 is OUR conservative application
    subset, not the authors' full published colour limits. Callers must verify
    an ordinary dwarf population consistent with the calibration sample.
    Excludes giants, strongly peculiar stars, and unverified young PMS stars.
    Error calculation assumes independent dereddened V,J,H errors; if shared
    dust/model errors are appreciable, propagate their covariance separately.
    The shared J term between both colours is handled correctly below.
    """
    method = "Mann2015_VJ_JH_conservative_subset"
    if not dwarf_population_verified:
        return _unavailable(method, "Dwarf/calibration-population check required")
    if not _finite(v0, j0, h0):
        return _unavailable(method, "Missing/non-finite Johnson V or 2MASS J,H")
    x, y = float(v0)-float(j0), float(j0)-float(h0)
    if not (3.5 <= x <= 6. and .5 <= y <= .7):
        return _unavailable(method, "Outside conservative V-J / J-H application subset")
    t = 3500. * (2.769 - 1.421*x + .4284*x**2 - .06133*x**3
                 + .003310*x**4 + .1333*y + .05416*y**2)
    if not 2700. <= t <= 4100.:
        return _unavailable(method, "Outside calibration temperature population")
    notes = ["Actual Johnson V and 2MASS photometry required",
             "No raw Gaia metallicity correction; conditional on dwarf population"]
    errors = (sigma_v0, sigma_j0, sigma_h0)
    if any(e is None for e in errors):
        return TemperatureEstimate(t, None, method, "conditional",
                                   tuple(notes + ["Photometry/extinction uncertainty missing"]))
    if not _finite(*errors) or any(float(e) < 0 for e in errors):
        return _unavailable(method, "Invalid magnitude errors")
    dx = 3500.*(-1.421 + 2.*.4284*x - 3.*.06133*x*x + 4.*.003310*x**3)
    dy = 3500.*(.1333 + 2.*.05416*y)
    sv, sj, sh = map(float, errors)
    var = (dx*sv)**2 + ((-dx+dy)*sj)**2 + (dy*sh)**2 + 48.**2 + 60.**2
    return TemperatureEstimate(t, math.sqrt(var), method, "conditional", tuple(notes))


# Small, explicitly approximate late-K/M dwarf reference; Mamajek v2022.04.16.
# These BP-RP colours are DR2-based: NOT a precision Gaia DR3 calibration.
# Do not use this reference alone to publish an M-dwarf census.
_COOL_DWARF_REFERENCE = (
    (1.53, 4300.), (1.70, 4100.), (1.73, 3990.), (1.79, 3930.),
    (1.84, 3850.), (1.97, 3770.), (2.09, 3660.), (2.13, 3620.),
    (2.23, 3560.), (2.39, 3470.), (2.50, 3430.), (2.78, 3270.),
    (2.94, 3210.), (3.16, 3110.), (3.35, 3060.), (3.71, 2930.),
    (4.16, 2810.),
)


def approximate_cool_dwarf_temperature(bp_rp0, *, assume_dwarf=False):
    """Opt-in rough display estimate; no invented precision or auto subtype."""
    method = "Mamajek2022_DR2_colour_reference"
    if not assume_dwarf or not _finite(bp_rp0):
        return _unavailable(method, "Explicit dwarf assumption and intrinsic colour required")
    c = float(bp_rp0)
    xs = [row[0] for row in _COOL_DWARF_REFERENCE]
    if not xs[0] <= c <= xs[-1]:
        return _unavailable(method, "Outside reference colour interval")
    i = min(bisect_right(xs, c)-1, len(xs)-2)
    x0, t0 = _COOL_DWARF_REFERENCE[i]
    x1, t1 = _COOL_DWARF_REFERENCE[i+1]
    t = t0 + (t1-t0)*(c-x0)/(x1-x0)
    return TemperatureEstimate(t, None, method, "approximate",
        ("DR2-based colours: unvalidated DR3 systematic uncertainty",
         "Assumes ordinary dwarf; reddening/photometric quality must be checked",
         "Do not use alone for membership, mass, age or a precise spectral subtype"))


def magnitude_error(flux_over_error):
    """High-S/N linear approximation only; faint fluxes require fuller modelling."""
    if not _finite(flux_over_error) or float(flux_over_error) <= 0.:
        return None
    return 2.5 / math.log(10.) / float(flux_over_error)


def gaia_flux_excess_check(observed_bp_rp, excess_factor, g_mag, *, nsigma=3.):
    """Riello et al. (2021) C*. Use OBSERVED colour, never dereddened colour.

    'passes' is a photometric consistency flag, not membership or binarity.
    G<=4: saturation prevents use of this rejection threshold.
    """
    result = {"c_star": None, "sigma_c_star": None, "passes": None,
              "status": "unavailable"}
    if not _finite(observed_bp_rp, excess_factor, g_mag, nsigma) or nsigma <= 0:
        return result
    x, c, g = map(float, (observed_bp_rp, excess_factor, g_mag))
    if not -1. <= x <= 7. or c <= 0.:
        return result
    if x < .5:
        f = 1.154360 + .033772*x + .032277*x*x
    elif x < 4.:
        f = 1.162004 + .011464*x + .049255*x*x - .005879*x**3
    else:
        f = 1.057572 + .140537*x
    result["c_star"] = c-f
    if g <= 4.:
        result["status"] = "bright_saturation_review"
        return result
    sigma = .0059898 + 8.817481e-12*g**7.618399
    result.update(sigma_c_star=sigma, passes=abs(c-f) < nsigma*sigma,
                  status="evaluated")
    return result


def bolometric_luminosity_radius(g_mag, distance_pc, ag, bc_g, teff_k):
    """Requires a vetted BC_G = Mbol - MG in the correct Gaia system.

    Values are conditional point estimates. Missing BC returns no L/R.
    For uncertain distances/temperatures/BC, propagate their joint posterior.
    No direct inversion of parallax is performed here.
    """
    if not _finite(g_mag, distance_pc, ag, bc_g, teff_k):
        return {"MG": None, "Mbol": None, "L_sun": None, "R_sun": None}
    g, d, a, bc, t = map(float, (g_mag, distance_pc, ag, bc_g, teff_k))
    if d <= 0. or t <= 0. or a < 0.:
        return {"MG": None, "Mbol": None, "L_sun": None, "R_sun": None}
    mg = g - 5.*math.log10(d) + 5. - a
    mbol = mg + bc
    lum = 10.**(-.4*(mbol-4.74))
    radius = math.sqrt(lum) * (5772./t)**2
    return {"MG": mg, "Mbol": mbol, "L_sun": lum, "R_sun": radius}
