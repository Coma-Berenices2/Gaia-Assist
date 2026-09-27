"""Published EDR3 geometric distances and explicit Scientist distance policy.

ESA schema verified 2026-09-23; see scientist_distance_service_verification.json.
No photogeometric substitution, local prior inference or second zero-point correction.
"""
from math import log10, isfinite
import scientist_network as net
from temperature_model import number

CATALOGUE = "Bailer-Jones et al. 2021, AJ 161, 147 — Gaia EDR3 geometric"
VERSION = "EDR3 / 2021AJ....161..147B"
TABLE = "external.gaiaedr3_distance"
REFERENCE = "https://bailer-jones.www3.mpia.de/gedr3_distances.html"
LY_PER_PC = 3.26156  # Preserve the application's existing conversion.
FIELDS = ("source_id", "r_med_geo", "r_lo_geo", "r_hi_geo", "flag")
RAW_FIELDS = {
    "bayesian_distance_pc": "Bayesian geometric distance",
    "bayesian_distance_lower_pc": "Bayesian distance — 16th percentile",
    "bayesian_distance_upper_pc": "Bayesian distance — 84th percentile",
    "bayesian_source_id": "Distance catalogue source ID",
    "bayesian_distance_flag": "Distance catalogue information flag",
    "bayesian_lookup_status": "Distance catalogue query status",
    "bayesian_lookup_message": "Distance catalogue query details",
    "bayesian_catalogue": "Distance catalogue",
    "bayesian_catalogue_version": "Distance catalogue version",
    "bayesian_catalogue_reference": "Distance catalogue reference",
}
DERIVED_FIELDS = {
    "baseline_distance_pc": "Baseline inverse-parallax distance",
    "baseline_distance_ly": "Baseline inverse-parallax distance (light-years)",
    "baseline_distance_status": "Baseline distance status",
    "bayesian_distance_ly": "Bayesian geometric distance (light-years)",
    "bayesian_distance_lower_ly": "Bayesian 16th percentile (light-years)",
    "bayesian_distance_upper_ly": "Bayesian 84th percentile (light-years)",
    "bayesian_quality_status": "Bayesian catalogue / quality status",
    "bayesian_quality_notes": "Bayesian distance interpretation",
    "adopted_distance_pc": "Adopted distance",
    "adopted_distance_ly": "Adopted distance (light-years)",
    "adopted_distance_method": "Adopted distance method",
    "distance_selection_reason": "Distance selection reason",
    "distance_review_notes": "Distance review notes",
    "distance_mode": "Recorded distance selection mode",
    "distance_auto_threshold": "Automatic distance threshold",
    "parallax_fractional_uncertainty": "Fractional parallax uncertainty",
    "distance_ratio": "Bayesian-to-baseline distance ratio",
    "distance_change_percent": "Bayesian-to-baseline change",
    "distance_delta_absolute_magnitude": "Distance-only absolute magnitude change",
    "distance_brightness_factor": "Distance-only brightness ratio factor",
    "distance_radius_factor": "Distance-only approximate radius factor",
    "distance_diagnostic_assumptions": "Distance comparison assumptions",
    "baseline_absolute_g": "Baseline absolute G (fixed extinction)",
    "baseline_g_brightness_ratio": "Baseline G-band brightness ratio (fixed extinction)",
    "baseline_radius_approx_solar": "Baseline approximate radius (fixed extinction and temperature)",
    "baseline_comparison_extinction": "Baseline comparison G extinction",
    "baseline_comparison_temperature": "Baseline comparison temperature",
}
DISPLAY_ORDER = (
    "adopted_distance_pc", "adopted_distance_ly", "adopted_distance_method", "distance_selection_reason",
    "baseline_distance_pc", "baseline_distance_ly", "baseline_distance_status",
    "bayesian_distance_pc", "bayesian_distance_ly", "bayesian_distance_lower_pc", "bayesian_distance_upper_pc",
    "bayesian_quality_status", "distance_review_notes", "distance_ratio", "distance_change_percent",
)
DETAIL_FIELDS = (set(RAW_FIELDS) | set(DERIVED_FIELDS)) - set(DISPLAY_ORDER)


def exact_id(value):
    if isinstance(value, bool) or not isinstance(value, (str, int)) or not str(value).isdigit():
        raise ValueError("Gaia IDs must be exact digit strings or integers")
    return str(int(value))


def cache_key(identifier):
    return net.cache_key("bayesian-geometric", ["Gaia EDR3=DR3", VERSION, net.BASE, TABLE, FIELDS, identifier])


def catalogue_record(row, status="retrieved", message=""):
    return {
        "bayesian_distance_pc": row.get("r_med_geo") if row else None,
        "bayesian_distance_lower_pc": row.get("r_lo_geo") if row else None,
        "bayesian_distance_upper_pc": row.get("r_hi_geo") if row else None,
        "bayesian_distance_flag": str(row["flag"]) if row and row.get("flag") is not None else None,
        "bayesian_source_id": exact_id(row["source_id"]) if row else None,
        "bayesian_lookup_status": status, "bayesian_lookup_message": message or None,
        "bayesian_catalogue": CATALOGUE, "bayesian_catalogue_version": VERSION,
        "bayesian_catalogue_reference": REFERENCE,
    }


def fetch(ids):
    """Bounded optional batches. No-match and incomplete successful rows are cached."""
    ids = list(dict.fromkeys(exact_id(i) for i in ids))
    context = net.CURRENT.get()
    options = context.options if context else net.settings()
    records, missing = {}, []
    for identifier in ids:
        if context and context.cancel.is_set():
            raise net.QueryCancelled("Query cancelled")
        hit, row = net.cache_get(cache_key(identifier), force=bool(context and context.force_refresh), options=options)
        if hit:
            records[identifier] = catalogue_record(row, "retrieved" if row else "no_match")
        else:
            missing.append(identifier)
    for start in range(0, len(missing), options.batch_size):
        batch = missing[start:start+options.batch_size]
        try:
            if context:
                context.report("Basic results available; looking up optional geometric distances")
            query = f"SELECT {', '.join(FIELDS)} FROM {TABLE} WHERE source_id IN ({','.join(batch)})"
            limit = min(options.optional_timeout, max(.01, context.check()-1.0)) if context else options.optional_timeout
            rows = net.tap_query(query, len(batch), limit=limit)
            if context:
                context.check()
            found = {}
            for row in rows:
                identifier = exact_id(row.get("source_id"))
                if identifier not in batch or identifier in found:
                    raise net.NetworkFailure("Distance response contains an unexpected or duplicate source ID")
                found[identifier] = {k: str(v) if isinstance(v, float) and not isfinite(v) else v for k, v in row.items()}
            for identifier in batch:
                row = found.get(identifier)
                net.cache_put(cache_key(identifier), row)
                records[identifier] = catalogue_record(row, "retrieved" if row else "no_match")
        except net.QueryCancelled:
            raise
        except (net.NetworkFailure, ValueError) as error:
            status = "query_timed_out" if isinstance(error, net.QueryTimeout) else "query_failed"
            for identifier in batch:
                records[identifier] = catalogue_record(None, status, str(error))
    return records


def baseline_distance(source):
    p, snr = number(source.get("parallax")), number(source.get("parallax_over_error"))
    if p is None or p <= 0:
        return None, "Unavailable: finite positive parallax required; no inversion performed"
    if snr is None or snr < 5:
        return None, "Unavailable: existing Scientist baseline requires parallax_over_error >= 5"
    baseline = number(1000.0/p)
    if baseline is None or baseline <= 0:
        return None, "Unavailable: inverse-parallax result outside finite numeric range"
    return baseline, "Existing inverse-parallax estimate; positive parallax and parallax_over_error >= 5; uncorrected parallax"


def bayesian_quality(source):
    lo, med, hi = (number(source.get(k)) for k in ("bayesian_distance_lower_pc", "bayesian_distance_pc", "bayesian_distance_upper_pc"))
    lookup = source.get("bayesian_lookup_status") or "not_requested"
    if lookup != "retrieved":
        return False, lookup, "Geometric catalogue availability: " + lookup
    try:
        matches = exact_id(source.get("bayesian_source_id")) == exact_id(source.get("source_id"))
    except ValueError:
        matches = False
    if not matches:
        return False, "invalid_source_match", "Catalogue source ID does not exactly match the resolved Gaia DR3 ID"
    if lo is None or med is None or hi is None or not 0 < lo <= med <= hi:
        return False, "invalid_interval", "Requires finite 0 < 16th percentile <= median <= 84th percentile; raw values retained"
    flag = str(source.get("bayesian_distance_flag") or "").strip()
    notes = ["16th–84th posterior percentile interval; not a symmetric error. Published parallax treatment retained; no extra zero-point correction."]
    review = False
    if flag == "99":
        notes.append("Flag 99: photogeometric inputs missing; geometric result remains usable. Geometric modality information unavailable.")
        review = True
    elif len(flag) == 5 and flag[0] in "012" and all(c in "01" for c in flag[1:3]) and all(c in "0123" for c in flag[3:]):
        if flag[0] != "1":
            notes.append("No G magnitude" if flag[0] == "0" else "Fainter than the prior model's HEALpixel G limit")
            review = True
        if flag[1] == "1":
            notes.append("Geometric posterior possibly multimodal (Hartigan dip test); interval may span modes")
            review = True
        notes.append("Remaining flag digits describe photogeometric inference; they do not reject the geometric estimate.")
    else:
        notes.append("Catalogue information flag missing or unrecognized; quality cannot be fully assessed")
        review = True
    notes.append("Flags are informational, not recommended rejection filters; prior and astrometric systematic effects remain.")
    return True, "usable; needs_review" if review else "usable; conditional catalogue estimate", " ".join(notes)


def evaluate_distance(source, options):
    baseline, baseline_status = baseline_distance(source)
    usable, quality, quality_notes = bayesian_quality(source)
    bayes = number(source.get("bayesian_distance_pc")) if usable else None
    p, error, snr = (number(source.get(k)) for k in ("parallax", "parallax_error", "parallax_over_error"))
    fraction = error/abs(p) if error is not None and error >= 0 and p is not None and p != 0 else None
    fraction_source = "parallax_error / abs(parallax)"
    if fraction is None and error is None and p is not None and p > 0 and snr is not None and snr > 0:
        fraction = 1/snr
        fraction_source = "1 / catalogue parallax_over_error (parallax_error unavailable)"
    mode, threshold = options.distance_mode, options.distance_auto_threshold
    chosen, method = baseline, "Baseline inverse parallax" if baseline is not None else "unavailable"
    if mode == "Baseline":
        reason = "Baseline mode: retain the existing inverse-parallax result" if baseline is not None else "Baseline mode: baseline invalid; no positive distance invented"
    elif mode == "Automatic" and baseline is not None and fraction is not None and fraction <= threshold:
        reason = f"Automatic: baseline fractional parallax uncertainty {fraction:.4g} <= {threshold:.4g}; configurable application policy, not proof of accuracy"
    elif bayes is not None:
        chosen, method = bayes, "Bayesian geometric (published EDR3)"
        reason = "Bayesian geometric mode: usable published geometric estimate" if mode == "Bayesian geometric" else "Automatic: baseline invalid, uncertainty unavailable, or above policy threshold; prefer usable geometric estimate"
    else:
        reason = f"{mode}: Bayesian geometric unavailable ({quality}); " + ("fallback to valid baseline" if baseline is not None else "baseline also unavailable")
    warnings = []
    ruwe = number(source.get("ruwe"))
    if ruwe is None:
        warnings.append("RUWE unavailable; astrometric quality unassessed")
    elif ruwe < .8 or ruwe > 1.4:
        warnings.append(f"RUWE={ruwe:g}: retain existing astrometric/binary review; neither distance repairs suspect astrometry")
    if snr is None or snr < 5:
        warnings.append("Parallax signal-to-noise missing or below 5; Bayesian distance may be prior sensitive")
    excess = number(source.get("astrometric_excess_noise_sig"))
    if excess is not None and excess > 2:
        warnings.append("Significant astrometric excess noise; review both distance estimates")
    if source.get("object_type", "") and str(source["object_type"]).lower().startswith(("galaxy", "quasar")):
        warnings.append("Galactic stellar prior is not established for this object type")
    if "needs_review" in quality:
        warnings.append(quality_notes)
    result = {**{key: source.get(key) for key in RAW_FIELDS}, "baseline_distance_pc": baseline, "baseline_distance_status": baseline_status,
        "bayesian_quality_status": quality, "bayesian_quality_notes": quality_notes,
        "adopted_distance_pc": chosen, "adopted_distance_method": method, "distance_selection_reason": reason,
        "distance_review_notes": "; ".join(warnings) or "Conditional estimate; catalogue prior and parallax systematics remain",
        "distance_mode": mode, "distance_auto_threshold": threshold, "parallax_fractional_uncertainty": fraction,
        "distance_diagnostic_assumptions": "Distance-only factors hold extinction and adopted temperature fixed; estimates share the same parallax and are not independent. Fractional uncertainty uses " + fraction_source,
        "distance_ratio": None, "distance_change_percent": None, "distance_delta_absolute_magnitude": None,
        "distance_brightness_factor": None, "distance_radius_factor": None}
    # Diagnostics can compare a numerically valid interval even when flagged for review.
    if baseline is not None and bayes is not None:
        f = number(bayes/baseline)
        if f is not None and f > 0:
            result.update(distance_ratio=f, distance_change_percent=number(100*(f-1)),
                distance_delta_absolute_magnitude=-5*log10(f), distance_brightness_factor=number(f*f), distance_radius_factor=f)
    for stem in ("baseline_distance", "adopted_distance", "bayesian_distance", "bayesian_distance_lower", "bayesian_distance_upper"):
        value = number(result.get(stem+"_pc", source.get(stem+"_pc")))
        result[stem+"_ly"] = value*LY_PER_PC if value is not None else None
    # Conservative screen used for downstream CMD evidence, not a quality certificate.
    if chosen is not None and method.startswith("Bayesian"):
        spread = max(chosen-number(source["bayesian_distance_lower_pc"]), number(source["bayesian_distance_upper_pc"])-chosen)/chosen
        result["_distance_cmd_usable"] = spread <= threshold and not warnings
    else:
        result["_distance_cmd_usable"] = baseline is not None and snr is not None and snr >= 10 and not warnings
    return result


def baseline_diagnostics(source, result):
    """Comparison only: recompute from inputs at fixed current extinction and T."""
    from temperature_comparison import safe_radius
    d, g, ag = (number(v) for v in (result.get("baseline_distance_pc"), source.get("phot_g_mean_mag"), result.get("mean_g_band_extinction")))
    t = number(result.get("effective_temperature"))
    out = dict.fromkeys(("baseline_absolute_g", "baseline_g_brightness_ratio", "baseline_radius_approx_solar"))
    out.update(baseline_comparison_extinction=ag, baseline_comparison_temperature=t)
    if d is not None and d > 0 and g is not None and ag is not None and ag >= 0:
        mg = g-5*log10(d)+5-ag
        try:
            luminosity = number(10**(.4*(4.67-mg)))
        except OverflowError:
            luminosity = None
        out.update(baseline_absolute_g=mg, baseline_g_brightness_ratio=luminosity, baseline_radius_approx_solar=safe_radius(mg,t))
    return out
