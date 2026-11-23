"""Scientist fields and display formatting; stored measurements remain unrounded."""
from math import isfinite
from temperature_model import GSP_EDGE_TOLERANCE_K, GSP_COMPRESSED_INTERVAL_K
from temperature_comparison import COMPARISON_FIELDS, RADIUS_EXPLANATION
from scientist_distance import RAW_FIELDS as DISTANCE_RAW_FIELDS, DERIVED_FIELDS as DISTANCE_FIELDS, DETAIL_FIELDS as DISTANCE_DETAILS
AP_FIELDS = tuple(
    f"{name}_gspphot{suffix}"
    for name in ("teff", "logg", "mh", "ag", "ebpminrp")
    for suffix in ("", "_lower", "_upper")
) + ("libname_gspphot", "logposterior_gspphot", "mcmcaccept_gspphot",
     "teff_esphs", "teff_esphs_uncertainty", "flags_esphs", "spectraltype_esphs")
PHOTOMETRY_FIELDS = ("phot_bp_mean_mag", "phot_rp_mean_mag", "parallax_error") + tuple(
    f"phot_{band}_mean_flux_over_error" for band in ("g", "bp", "rp")
)
GAIA_FIELDS = {}
UNITS = {}
EXPLANATIONS = {}
for name, label, unit in (
    ("teff", "Gaia GSP-Phot Temperature", "K"),
    ("logg", "Gaia GSP-Phot Surface Gravity", "log10(cm/s²)"),
    ("mh", "Gaia Raw Metallicity (M/H)", "dex"),
    ("ag", "Gaia GSP-Phot G Extinction", "mag"),
    ("ebpminrp", "Gaia GSP-Phot BP-RP Reddening", "mag"),
):
    for suffix, extra in (("", ""), ("_lower", " Lower Bound"), ("_upper", " Upper Bound")):
        key = f"{name}_gspphot{suffix}"
        GAIA_FIELDS[key] = label + extra
        UNITS[key] = unit
        EXPLANATIONS[key] = label + ". Gaia model estimate; catalogue lower/upper bounds are 16th/84th percentiles, not total accuracy. Parameters share fitted inputs and may have systematic errors."
GAIA_FIELDS.update(dict(zip(PHOTOMETRY_FIELDS, (
    "Mean BP", "Mean RP", "Parallax Error", "G Flux S/N", "BP Flux S/N", "RP Flux S/N",
))))
GAIA_FIELDS.update(libname_gspphot="Gaia Atmosphere Library", logposterior_gspphot="Gaia Log Posterior", mcmcaccept_gspphot="Gaia MCMC Acceptance")
GAIA_FIELDS.update(teff_esphs="Gaia ESP-HS Temperature", teff_esphs_uncertainty="Gaia ESP-HS Formal Uncertainty", flags_esphs="Gaia ESP-HS Flags", spectraltype_esphs="Gaia ESP-ELS Spectral Tag")
GAIA_FIELDS.update(gaia_ap_status="Gaia Parameter Query Status", gaia_ap_message="Gaia Parameter Query Details")
GAIA_FIELDS.update(gaia_catalogue_service="Gaia database", gaia_catalogue_endpoint="Gaia catalogue endpoint",
                   gaia_catalogue_release="Gaia catalogue release", gaia_catalogue_retrieved_utc="Gaia catalogue retrieved (UTC)")
EXPLANATIONS.update(gaia_catalogue_service="Database selected for this query. Switching databases uses a separate raw-data cache and does not reclassify cluster membership.",
                    gaia_catalogue_endpoint="TAP endpoint used for these Gaia catalogue inputs.",
                    gaia_catalogue_release="The source data release; all current calculations use Gaia DR3.",
                    gaia_catalogue_retrieved_utc="Original catalogue retrieval time in UTC, retained when raw inputs are reused from cache.")
UNITS.update(teff_esphs="K", teff_esphs_uncertainty="K")
UNITS.update(phot_bp_mean_mag="mag", phot_rp_mean_mag="mag", parallax_error="mas")
DERIVED_FIELDS = {
    "carbon_star_badge": "Carbon-Star Identification",
    "carbon_star_status": "Carbon-Star Status",
    "carbon_identification_source": "Carbon Identification Source",
    "carbon_reference": "External Carbon Identification Reference",
    "carbon_review_reason": "Carbon-Star Interpretation",
    "ordinary_star_equivalent": "Ordinary-Star-Equivalent Estimate (Not Established Class)",
    "scientific_bp_rp_temperature": "Calibrated BP-RP Comparison",
    "scientific_bp_rp_status": "Calibrated BP-RP Status",
    "scientific_bp_rp_notes": "Calibrated BP-RP Limitations",
    "fallback_colour": "Explorer Fallback Colour",
    "fallback_colour_source": "Explorer Fallback Colour Source",
    "gaia_temperature": "Gaia Temperature",
    "gaia_temperature_source": "Gaia Temperature Source",
    "esphs_status": "ESP-HS Eligibility",
    "esphs_notes": "ESP-HS Review Notes",
    "casagrande_temperature": "Casagrande Comparison Temperature",
    "casagrande_status": "Casagrande Domain Status",
    "cool_dwarf_temperature": "Approximate Cool-Dwarf Comparison",
    "cool_dwarf_notes": "Cool-Dwarf Reference Limitations",
    "bp_rp_temperature_approximate": "Colour Estimate Is Approximate",
    "metallicity_requested": "Supplied / Requested Composition",
    "metallicity_requested_source": "Supplied Composition Provenance",
    "metallicity_policy_reason": "Composition Selection Reason",
    "bp_rp_temperature": "BP-RP Temperature",
    "bp_rp_temperature_error": "BP-RP Conditional Temperature Error",
    "bp_rp_temperature_lower": "BP-RP Conditional Lower Bound",
    "bp_rp_temperature_upper": "BP-RP Conditional Upper Bound",
    "bp_rp_temperature_method": "BP-RP Formula",
    "bp_rp_temperature_status": "BP-RP Temperature Status",
    "bp_rp_temperature_notes": "BP-RP Assumptions and Limitations",
    "adopted_temperature_source": "Adopted Temperature Source",
    "temperature_selection_reason": "Temperature Selection Reason",
    "temperature_status": "Adopted Temperature Status",
    "temperature_concerns": "Temperature Review Notes",
    "temperature_override_reason": "Temperature Override Reason",
    "temperature_shared_inputs": "Shared Temperature Inputs",
    "temperature_hypotheses": "Unconfirmed Temperature Hypotheses",
    "temperature_sensitivity": "Assumption Sensitivity (Not Errors)",
    "gravity_adopted": "Gravity Used for BP-RP",
    "gravity_source": "Gravity Source",
    "metallicity_adopted": "Composition Used for BP-RP",
    "metallicity_source": "Composition Source / Assumption",
    "population_hypothesis": "Stellar Population Hypothesis",
    "red_dwarf_candidate": "Quick Red-Dwarf Candidate Screen",
    "photometry_status": "Photometric Quality Screen",
    "extinction_source": "Chosen Extinction Source",
    "extinction_status": "Extinction Status",
    "classification_status": "Estimated Classification Status",
    "visual_magnitude_status": "Estimated V Magnitude Status",
    "physical_property_status": "Bolometric Property Status",
    "calculation_version": "Calculation Version",
    "temperature_options": "Recorded Temperature Settings",
    "legacy_effective_temperature": "Legacy Temperature (Not Adopted)",
    "legacy_radius": "Legacy Radius (Not Bolometric)",
    "legacy_star_type": "Legacy Estimated Classification",
}
GSP_BOUNDARY_FIELDS = {
    "gsp_model_library": "GSP-Phot library checked",
    "gsp_model_boundary_status": "GSP-Phot grid boundary status",
    "gsp_model_boundary_distance_k": "Distance to nearest GSP-Phot temperature boundary",
    "gsp_model_boundary_warning": "GSP-Phot grid boundary notes",
}
DERIVED_FIELDS.update(GSP_BOUNDARY_FIELDS)
UNITS["gsp_model_boundary_distance_k"] = "K"
EXPLANATIONS.update(
    gsp_model_library="The atmosphere library Gaia selected for this GSP-Phot fit, as recorded in libname_gspphot.",
    gsp_model_boundary_status=(
        f"The median triggers review within {GSP_EDGE_TOLERANCE_K:g} K of a documented library limit. "
        f"A stronger concern means the reported 16th–84th percentile interval reaches the same limit "
        f"or lies entirely within {GSP_COMPRESSED_INTERVAL_K:g} K of it. These provisional thresholds screen for a possible grid constraint."
    ),
    gsp_model_boundary_distance_k=(
        "Temperature difference in kelvin between the GSP-Phot median and the nearer documented limit "
        "of its selected library. An empty value means the check could not evaluate this fit."
    ),
    gsp_model_boundary_warning="Identifies the library limit and the evidence for reviewing the GSP-Phot fit. A boundary flag alone cannot establish a temperature error.",
)
DERIVED_FIELDS.update(COMPARISON_FIELDS)
DERIVED_FIELDS.update(DISTANCE_RAW_FIELDS)
DERIVED_FIELDS.update(DISTANCE_FIELDS)
UNITS.update({key: "pc" for key in (*DISTANCE_RAW_FIELDS, *DISTANCE_FIELDS) if key.endswith("_pc")})
UNITS.update({key: "ly" for key in DISTANCE_FIELDS if key.endswith("_ly")})
UNITS.update(distance_change_percent="%", distance_delta_absolute_magnitude="mag", baseline_absolute_g="mag", baseline_comparison_extinction="mag", baseline_comparison_temperature="K", baseline_g_brightness_ratio="G/G_sun", baseline_radius_approx_solar="R_sun")
UNITS.update(explorer_comparison_temperature="K", explorer_comparison_radius="R_sun", radius_approx_solar="R_sun", radius_approx_absolute_g="mag", bc_g="mag", bolometric_luminosity="L_sun")
for key in ("gaia_temperature", "casagrande_temperature", "cool_dwarf_temperature", "effective_temperature", "bp_rp_temperature", "bp_rp_temperature_error", "bp_rp_temperature_lower", "bp_rp_temperature_upper", "legacy_effective_temperature"):
    UNITS[key] = "K"
UNITS.update(gravity_adopted="log10(cm/s²)", metallicity_adopted="dex", legacy_radius="R_sun", luminosity="G/G_sun")
UNITS.update(scientific_bp_rp_temperature="K", fallback_colour="mag")
EXPLANATIONS.update({
    "flags_esphs": "Preserved catalogue string. First digit: 0 = BP/RP and RVS, 1 = BP/RP only. Second digit 1–5 describes spectral-tag confidence; 999 means no valid parameters. Mode 0 formal errors may be underestimated. These are not final stellar classifications.",
    "metallicity_policy_reason": "For intrinsic BP-RP below the configurable blue cutoff (default 0.35), the colour calculation assumes solar composition. This is an application safeguard, not a spectral boundary, and does not change Gaia temperatures or the calibration domain.",
    "effective_temperature": "The adopted temperature used by classification. Both Gaia and colour estimates remain visible. Check source, selection reason and review status; this is not a guarantee of accuracy.",
    "luminosity": "G-band solar brightness ratio: 10**(0.4*(4.67-MG)). A passband quantity, not total bolometric luminosity; it must not be used to infer a bolometric radius.",
    "radius": "Stefan–Boltzmann radius from corrected absolute G plus an explicitly applicable, sourced BC_G = Mbol - MG (solar Mbol 4.74, temperature 5772 K). Unavailable when valid inputs or a vetted correction are absent.",
    "radius_approx_solar": RADIUS_EXPLANATION,
    "star_type": "Estimated classification using the adopted temperature and estimated Johnson V absolute magnitude. When a full classification is unavailable, a labelled approximate temperature-only family may be shown without a luminosity class. Review its status; this is not spectroscopic classification or evidence of cluster membership.",
    "red_dwarf_candidate": "Heuristic: intrinsic BP-RP > 1.8 and estimated Mv > 8.69. A failed screen does not rule out a dwarf; an equal-flux binary is about 0.753 mag brighter. Uncertain distance/extinction/V transformation makes the screen uncertain.",
    "bp_rp_excess_correctness": "Riello C* evaluated on observed BP-RP, with a G-magnitude-dependent tolerance. Missing inputs are unassessed. This is a photometry screen, not membership evidence.",
    "metallicity": "Raw Gaia GSP-Phot M/H retained for inspection. It is not automatically treated as vetted Fe/H by the temperature calibration.",
})
DERIVED_FIELDS.update({
    "g_magnitude_used": "G magnitude used",
    "g_magnitude_status": "G magnitude correction status",
})
UNITS["g_magnitude_used"] = "mag"
EXPLANATIONS["g_magnitude_used"] = "Mean G minus the available G-band extinction. If neither Gaia nor NADC supplies valid G-band extinction, observed Mean G is used directly and is not de-dusted. A valid distance is still required for absolute magnitude."
EXPLANATIONS["g_magnitude_status"] = "States whether the G magnitude used for derived properties was corrected for extinction or is the observed, not de-dusted measurement. Unknown extinction is not zero extinction."
EXPLANATIONS["absolute_magnitude"] = "G-band absolute magnitude using the adopted distance and available extinction correction. When extinction is unavailable, uses observed Mean G; check G magnitude correction status."
for key, label in {**GAIA_FIELDS, **DERIVED_FIELDS}.items():
    EXPLANATIONS.setdefault(key, label + ". Read with the recorded method, assumptions and review notes. Missing information remains unavailable; formal errors do not include every systematic effect.")

TEMPERATURE_DISPLAY_ORDER = (
    "g_magnitude_used", "g_magnitude_status",
    "effective_temperature", "adopted_temperature_source", "temperature_status",
    "temperature_selection_reason", "temperature_concerns",
    "radius_approx_solar", "radius", "physical_property_status",
    "radius_approx_temperature_source", "radius_approx_extinction_assumptions", "radius_approx_notes",
    "star_type", "classification_status",
    "gaia_temperature", "gaia_temperature_source", "bp_rp_temperature",
    "bp_rp_temperature_method", "bp_rp_temperature_status",
    "explorer_comparison_temperature", "explorer_comparison_radius",
    "explorer_comparison_classification", "explorer_comparison_notes",
)

TEMPERATURE_DETAIL_FIELDS = frozenset({
    *GSP_BOUNDARY_FIELDS,
    "scientific_bp_rp_temperature", "scientific_bp_rp_status", "scientific_bp_rp_notes",
    "fallback_colour", "fallback_colour_source",
    *AP_FIELDS, "bp_rp_temperature_error", "bp_rp_temperature_lower", "bp_rp_temperature_upper",
    "bp_rp_temperature_notes", "bp_rp_temperature_approximate", "temperature_shared_inputs",
    "temperature_hypotheses", "temperature_sensitivity", "gravity_adopted", "gravity_source",
    "metallicity_adopted", "metallicity_source", "metallicity_requested", "metallicity_requested_source",
    "metallicity_policy_reason", "population_hypothesis", "temperature_options", "calculation_version",
    "temperature_override_reason", "gaia_ap_message", "esphs_status", "esphs_notes", "casagrande_temperature",
    "casagrande_status", "cool_dwarf_temperature", "cool_dwarf_notes",
})
TEMPERATURE_DETAIL_FIELDS = TEMPERATURE_DETAIL_FIELDS | frozenset(DISTANCE_DETAILS) | frozenset({
    "gaia_catalogue_endpoint", "gaia_catalogue_release", "gaia_catalogue_retrieved_utc",
    "distance_parsecs", "distance_lightyears",
    "carbon_identification_source", "carbon_reference", "carbon_review_reason",
    "radius_approx_absolute_g", "bc_g", "bc_g_applicable", "bc_g_source",
    "bolometric_luminosity", "bolometric_radius_temperature_source",
})


def empty_historical(key, value):
    return key.startswith("legacy_") and (value is None or str(value).strip() in ("", "-", "None"))


def compact_text(value, limit=64):
    text = str(value).replace("\n", " ")
    return text if len(text) <= limit else text[:limit-3] + "..."

EXPLANATIONS["spectraltype_esphs"] = "Original Gaia field. Despite its suffix, this tag is supplied by ESP-ELS from BP/RP spectra. CSTAR indicates a candidate; an absent tag does not rule out carbon-rich chemistry."
EXPLANATIONS["carbon_star_badge"] = "Gaia’s spectral classifier detected features consistent with a carbon star. This candidate flag does not by itself confirm the classification."

def format_display_value(key, value):
    if value is None:
        return "-"
    if UNITS.get(key) == "K":
        try:
            numeric = float(value)
            if isfinite(numeric):
                if key == "gsp_model_boundary_distance_k":
                    return f"{numeric:.6g}"
                return f"{numeric:.0f}"
        except (TypeError, ValueError):
            pass
    return str(value)


def format_export_value(value):
    """Keep full numeric precision and unabridged text in saved tables."""
    return "-" if value is None else str(value)

EXPLANATIONS.update({
    "adopted_distance_pc": "Explicit distance used for extinction lookup, magnitudes, brightness, approximate radius and classification in this calculation. Read the method and selection reason; systematic errors and prior assumptions remain.",
    "baseline_distance_pc": "Original Scientist baseline: 1000/parallax (mas), only for finite positive parallax and parallax_over_error >= 5. This uncorrected inverse-parallax calculation is not Bayesian.",
    "bayesian_distance_pc": "Published Bailer-Jones et al. (2021) EDR3 geometric posterior median in parsecs. Uses parallax and a Galactic direction-dependent prior; no photogeometric substitution and no additional zero-point correction.",
    "bayesian_distance_lower_pc": "Catalogue geometric distance posterior 16th percentile in parsecs. Paired with the 84th percentile, this is an asymmetric posterior interval, not a symmetric plus/minus error.",
    "bayesian_distance_upper_pc": "Catalogue geometric distance posterior 84th percentile in parsecs. See the 16th percentile for the other bound.",
    "distance_ratio": "Bayesian geometric median divided by valid baseline distance; not independent measurements or a universal correction. Fixed extinction and temperature are required for the displayed distance-only diagnostic factors.",
    "distance_auto_threshold": "Configurable Automatic-mode policy: retain an eligible baseline at or below this fractional parallax uncertainty (default 0.10). Not a universal scientific boundary or a guarantee of accuracy.",
    "distance_parsecs": "Compatibility distance field for saved records. Fresh Scientist calculations use the explicit adopted distance; older loaded values retain their original method and are not relabelled Bayesian.",
    "distance_lightyears": "Saved-record compatibility distance in light-years. Fresh calculations alias the explicit adopted distance, using the original conversion of 3.26156 light-years per parsec.",
})


BULK_CATEGORY_ORDER = (
    "Identity and classification", "Coordinates", "Motion and velocity", "Distance and parallax",
    "Brightness and magnitudes", "Colour and temperature", "Extinction and reddening",
    "Radius", "Quality indicators", "Composition and gravity", "Calculation and catalogue notes",
)


def bulk_field_category(key):
    """Assign a stable subject to each field; provenance stays with its subject."""
    if key in GSP_BOUNDARY_FIELDS:
        return "Colour and temperature"
    if key.startswith(("distance_", "bayesian_", "baseline_distance", "parallax")):
        return "Distance and parallax"
    if key in ("ra", "dec", "l", "b", "constellation") or key.startswith(("ra_", "dec_")):
        return "Coordinates"
    if key.startswith(("pmra", "pmdec", "radial_velocity")):
        return "Motion and velocity"
    if "radius" in key or key == "physical_property_status":
        return "Radius"
    if any(word in key for word in ("excess", "ruwe", "flux_over_error")) or key in ("photometry_status", "flags_esphs", "logposterior_gspphot", "mcmcaccept_gspphot"):
        return "Quality indicators"
    if any(word in key for word in ("extinction", "reddening", "ebpminrp")) or key == "ebv" or key.startswith("ag_gspphot"):
        return "Extinction and reddening"
    if any(word in key for word in ("metallicity", "gravity")) or key.startswith(("mh_gspphot", "logg_gspphot")):
        return "Composition and gravity"
    if any(word in key for word in ("magnitude", "luminosity", "brightness")) or key.startswith(("phot_", "bc_g")) or key in ("baseline_absolute_g",):
        return "Brightness and magnitudes"
    if key in ("source_id", "object_type", "star_type", "ordinary_star_equivalent", "red_dwarf_candidate", "population_hypothesis", "spectraltype_esphs", "legacy_star_type") or "classification" in key or key.startswith("carbon_"):
        return "Identity and classification"
    if key == "temperature_options" or key == "calculation_version":
        return "Calculation and catalogue notes"
    if any(word in key for word in ("temperature", "teff", "bp_rp", "colour", "wavelength", "casagrande", "cool_dwarf", "esphs_")):
        return "Colour and temperature"
    return "Calculation and catalogue notes"
