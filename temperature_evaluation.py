"""Input-driven Scientist calculation; final classification is downstream."""
from dataclasses import asdict
from temperature_carbon import normalized_tag

from temperature_model import (
    VERSION, TemperatureOptions, bounds, number, casagrande_estimate,
    casagrande_in_domain, casagrande_value, red_dwarf_screen, select_adopted_temperature,
)
from temperature_reference import (
    approximate_cool_dwarf_temperature, gaia_flux_excess_check, mb21_temperature,
)


def photometry_quality(source, options):
    quality = gaia_flux_excess_check(source.get("bp_rp"), source.get("phot_bp_rp_excess_factor"), source.get("phot_g_mean_mag"), nsigma=options.excess_nsigma)
    reasons = []
    for band in ("bp", "rp"):
        snr = number(source.get(f"phot_{band}_mean_flux_over_error"))
        if snr is None:
            reasons.append(f"Required quality information missing: {band.upper()} signal-to-noise")
        elif snr < options.min_snr:
            reasons.append(f"{band.upper()} signal-to-noise failed ({snr:g} < {options.min_snr:g})")
        mag = number(source.get(f"phot_{band}_mean_mag"))
        if mag is None:
            reasons.append(f"Required quality information missing: {band.upper()} magnitude for bright-source screen")
        elif mag < 5:
            reasons.append(f"Bright-source calibration concern: {band.upper()} magnitude < 5")
    if quality["passes"] is False:
        reasons.append("Corrected BP/RP flux-excess check failed")
    elif quality["passes"] is None:
        if quality["status"] == "bright_saturation_review":
            reasons.append("Bright-source calibration concern: G <= 4; C* tolerance unassessed")
        else:
            missing = [name for key, name in (("bp_rp", "observed BP-RP"), ("phot_bp_rp_excess_factor", "BP/RP excess factor"), ("phot_g_mean_mag", "G magnitude")) if number(source.get(key)) is None]
            reasons.append("Required quality information missing: " + ", ".join(missing) if missing else "Corrected BP/RP flux-excess check outside its supported input domain")
    return quality, reasons


def gaia_temperature_candidates(source, options, unsupported=False):
    """ESP-HS applicability uses documented fields and conservative app screens.

    Flags: first digit 0=BP/RP+RVS, 1=BP/RP only; second 1..5 is
    spectral-tag confidence. Requiring grade 1 for a concern-free candidate is
    an application choice. The catalogue's 68% uncertainty is never rescaled
    or used as a stand-alone reliability rank.
    """
    t = number(source.get("teff_gspphot"))
    ge = t is not None and t > 0 and not unsupported
    errors = bounds(t, source.get("teff_gspphot_lower"), source.get("teff_gspphot_upper"))
    concerns = []
    if ge:
        if errors is None or number(source.get("teff_gspphot_lower")) <= 0:
            concerns.append("missing or malformed Gaia temperature bounds")
        elif max(errors)/t > options.wide_interval:
            concerns.append("wide Gaia temperature interval (> configured fraction)")
    gsp = {"temperature": t, "eligible": ge, "source": "Gaia GSP-Phot", "specific_issues": concerns, "concerns": concerns}
    ht = number(source.get("teff_esphs"))
    hu = number(source.get("teff_esphs_uncertainty"))
    gmag = number(source.get("phot_g_mean_mag"))
    tag = normalized_tag(source.get("spectraltype_esphs"))
    flags = str(source.get("flags_esphs") or "").strip()
    valid_flag = len(flags) == 2 and flags[0] in "01" and flags[1] in "12345"
    applicable = ht is not None and 7000 <= ht <= 50000 and gmag is not None and gmag < 17.65 and tag in {"O", "B", "A"} and not unsupported
    hs_notes = []
    if ht is None or ht <= 0:
        hs_notes.append("ESP-HS temperature unavailable")
    elif not applicable:
        hs_notes.append("ESP-HS applicability unconfirmed: requires O/B/A catalogue tag, G < 17.65 and 7000–50000 K")
    if not valid_flag:
        hs_notes.append("ESP-HS processing/quality flags missing or unsupported")
    elif flags[1] != "1":
        hs_notes.append("ESP-HS spectral-tag confidence requires review (application grade-1 preference)")
    if ht is not None and ht > 0:
        if hu is None or hu <= 0:
            hs_notes.append("ESP-HS temperature uncertainty missing or invalid")
        elif hu/ht > options.wide_interval:
            hs_notes.append("ESP-HS temperature uncertainty exceeds configured fraction")
        if valid_flag and flags[0] == "0":
            hs_notes.append("ESP-HS BP/RP+RVS uncertainties may be underestimated by factors 5–10")
        hs_notes.append("ESP-HS assumes solar composition and shares Gaia spectra; agreement is not independent validation")
    hs = {"temperature": ht, "eligible": applicable and valid_flag, "source": "Gaia ESP-HS", "concerns": hs_notes,
          "review": bool(not valid_flag or flags[1:] != "1" or flags[:1] == "0" or hu is None or hu <= 0 or (ht and hu/ht > options.wide_interval))}
    candidates = {"Gaia GSP-Phot": gsp, "Gaia ESP-HS": hs}
    # Availability alone does not displace an eligible GSP-Phot estimate.
    chosen = gsp if ge or not hs["eligible"] else hs
    if not chosen["eligible"]:
        ap_status = source.get("gaia_ap_status")
        if ap_status == "query_timed_out":
            reason = "Gaia parameter request timed out; catalogue availability unknown"
        elif ap_status == "query_failed":
            reason = "Gaia parameter request failed; retry the query"
        elif ap_status == "no_row":
            reason = "Gaia query succeeded but no parameter row exists for this source"
        elif t is None and ht is None:
            reason = "Gaia query succeeded but both catalogue temperatures are blank" if ap_status == "retrieved" else "Neither Gaia catalogue temperature was supplied"
        else:
            reason = "No eligible Gaia temperature; see catalogue values and ESP-HS review notes"
        chosen["unavailable_reason"] = reason
        chosen["concerns"] = chosen["concerns"] + [reason] + hs_notes
    comparison = []
    if ge and hs["eligible"] and abs(t-ht) > max(options.disagreement_k, options.disagreement_fraction*(t+ht)/2):
        comparison.append("GSP-Phot / ESP-HS disagreement requires review; retain GSP-Phot by default")
    return chosen, candidates, comparison


def evaluate_temperatures(source, context, options=None):
    options = options or TemperatureOptions()
    c = number(context.get("new_bp_rp"))
    h = number(source.get("logg_gspphot"))
    h_errors = bounds(h, source.get("logg_gspphot_lower"), source.get("logg_gspphot_upper"))
    h_usable = h is not None and 0 <= h <= 4.8
    quality, quality_reasons = photometry_quality(source, options)
    q_good = not quality_reasons
    shared = list(quality_reasons)
    if context.get("extinction_status") != "usable":
        shared.append("Extinction uncertain or unavailable")
    ruwe = number(source.get("ruwe"))
    if ruwe is not None and ruwe > 1.4:
        shared.append("RUWE > 1.4: astrometric/binary review, not temperature rejection")
    object_type = str(source.get("object_type") or "").lower()
    nonstellar = object_type.startswith(("quasar", "galaxy"))
    carbon_tag = normalized_tag(source.get("spectraltype_esphs")) == "CSTAR"
    unsupported = nonstellar or object_type.startswith(("white dwarf", "wolf-rayet", "carbon star")) or carbon_tag
    unsupported_reason = ("Gaia CSTAR tag flags a possible carbon star; ordinary-star BP-RP calibration withheld pending review"
                          if carbon_tag else "Object type unsupported by ordinary-star BP-RP calibration")
    population, population_source = options.population, options.population_reason
    screen = red_dwarf_screen(c, context.get("visual_absolute_magnitude"), context.get("cmd_reliable", False))
    mv = number(context.get("visual_absolute_magnitude"))
    quick_candidate = c is not None and c > 1.8 and mv is not None and mv > 8.69
    low_gravity = h_usable and h <= 3
    conflict = bool(low_gravity and (quick_candidate or population == "dwarf"))
    if conflict:
        shared.append("Low gravity conflicts with dwarf evidence; dwarf fallback disabled, measured gravity retained")
    if population == "auto":
        if h_usable:
            population = "dwarf hypothesis" if h >= 4 else "giant hypothesis" if h <= 3 else "ordinary star; luminosity class unresolved"
            population_source = "measured Gaia gravity; calibration domain is not final luminosity class"
        elif h is None and screen.startswith("candidate"):
            population, population_source = "dwarf", "Quick red-dwarf candidate evidence (heuristic)"
        else:
            population, population_source = "ambiguous", "Gravity unavailable or outside application domain"
    assumed_h = h is None and population in ("dwarf", "giant") and not unsupported
    if assumed_h:
        h = 4. if population == "dwarf" else 2.
        h_errors = None  # an assumed value is not a zero-error gravity measurement
    if unsupported:
        shared.append(unsupported_reason)
    gravity_notes = []
    if h_usable and h_errors is None:
        gravity_notes.append("Gravity bounds missing or malformed; actual gravity retained, uncertainty unknown")
    elif assumed_h:
        gravity_notes.append("Gravity assumed from recorded evidence; uncertainty unknown; see sensitivity examples")
    if options.metallicity_mode == "solar":
        z, z_error, z_source = 0., None, "solar composition assumed; not a measured zero"
    elif options.metallicity_mode == "trusted":
        z, z_error = number(options.feh), number(options.feh_error)
        z_source = "User-supplied [Fe/H]: " + options.metallicity_source
        z_source += "; user confirms vetting (not independently verified by app)" if options.metallicity_vetted else "; vetting unconfirmed; provenance text alone does not validate a measurement"
    else:
        z, z_error = number(source.get("mh_gspphot")), None
        z_source = "uncalibrated Gaia M/H diagnostic used as Fe/H; reliability not upgraded"
    requested_z, requested_z_source = z, z_source
    blue_suppressed = c is not None and c < options.blue_metallicity_cutoff
    metallicity_reason = "Requested composition used within the selected calibration's domain"
    if blue_suppressed:
        z, z_error = 0., None
        metallicity_reason = f"Intrinsic BP-RP {c:.3f} < {options.blue_metallicity_cutoff:g}: metallicity correction suppressed by application screen, not a spectral boundary"
        z_source = "solar composition assumed by blue-colour safeguard; not a measured zero"
    z_errors = None if z_error is None else (z_error, z_error)
    c_errors = context.get("colour_errors")
    # No final dwarf/giant class is required for measured intermediate gravity.
    supported = (h_usable or assumed_h) and not unsupported
    ordinary = casagrande_estimate(c, h, z, population_supported=supported, errors=(c_errors, h_errors, z_errors))
    colour = {**ordinary, "concerns": list(ordinary["concerns"])}
    if options.method == "Mucciarelli2021":
        mbclass = ("dwarf" if h > 3 else "giant") if h is not None and h != 3 else "ambiguous"
        estimate = mb21_temperature(c, z, stellar_class=mbclass, sigma_colour0=max(c_errors) if c_errors else None,
                                   sigma_feh=z_error, metallicity_source=z_source)
        mbstatus = "conditional" if estimate.teff_k is not None else "outside_domain" if any("outside" in n.lower() for n in estimate.notes) else "unavailable"
        colour = {"temperature": estimate.teff_k, "uncertainty": estimate.uncertainty_k, "method": estimate.method,
                  "eligible": supported and estimate.teff_k is not None, "status": mbstatus,
                  "concerns": list(estimate.notes), "lower": None, "upper": None}
    dwarf_supported = not unsupported and not conflict and (
        (h_usable and h >= 4) or (assumed_h and population == "dwarf") or
        (screen.startswith("candidate") and (h is None or h > 3)))
    cool = approximate_cool_dwarf_temperature(c, assume_dwarf=dwarf_supported)
    if options.method == "Casagrande2021" and colour["temperature"] is None and cool.teff_k is not None:
        colour = {"temperature": cool.teff_k, "eligible": True, "method": cool.method, "approximate": True,
                  "status": "approximate", "concerns": list(cool.notes), "uncertainty": None, "lower": None, "upper": None}
        z, z_source = None, "Not used by approximate cool-dwarf interpolation"
        metallicity_reason = "No metallicity correction is calibrated for this interpolation"
    colour["concerns"] += gravity_notes + [z_source, metallicity_reason, "Intrinsic colour = observed BP-RP minus chosen reddening, applied once"]
    if unsupported:
        colour["eligible"] = False
        colour["concerns"].append(unsupported_reason)
    if not colour["eligible"]:
        blockers = []
        if h is None:
            blockers.append("gravity missing and no supported gravity assumption")
        if unsupported:
            blockers.append(unsupported_reason)
        if c is None:
            blockers.append("intrinsic colour unavailable")
        if not blockers:
            blockers.extend(colour["concerns"][:1])
        colour["unavailable_reason"] = "; ".join(blockers)
    composition_review = options.metallicity_mode == "raw_gaia" or (options.metallicity_mode == "trusted" and not options.metallicity_vetted)
    colour["review"] = bool(shared or gravity_notes or composition_review)
    colour["preferential"] = bool(colour["eligible"] and not colour.get("approximate") and q_good and not shared
        and context.get("extinction_status") == "usable" and not assumed_h and h_errors is not None
        and options.metallicity_mode == "trusted" and options.metallicity_vetted and not blue_suppressed
        and colour.get("uncertainty") is not None and 4000 <= colour["temperature"] <= 6700)
    if colour["temperature"] is not None:
        colour["status"] = "needs_review" if colour["review"] or not colour["eligible"] else "approximate" if colour.get("approximate") else "conditional"
    hypotheses = []
    if h is None and not unsupported:
        for kind, hh in (("dwarf", 4.), ("giant", 2.)):
            trial = casagrande_estimate(c, hh, z)
            value = trial["temperature"]
            hypotheses.append(f"{kind}, logg={hh}: {value:.1f} K (not eligible)" if value else f"{kind}: {trial['status']}")
    sensitivity = []
    if options.method == "Casagrande2021" and None not in (c, h, z):
        for name, trial_h, trial_z in (("logg -0.5", h-.5, z), ("logg +0.5", h+.5, z), ("Fe/H -0.5", h, z-.5), ("Fe/H +0.5", h, z+.5)):
            if casagrande_in_domain(c, trial_h, trial_z):
                sensitivity.append(f"{name}: {casagrande_value(c, trial_h, trial_z):.1f} K")
    # A colour-calibration restriction must not erase a published Gaia stellar
    # temperature. Keep it with review concerns; a spectral tag is not a final class.
    gaia, candidates, gaia_comparison = gaia_temperature_candidates(source, options, nonstellar)
    shared += gaia_comparison
    selection = select_adopted_temperature(gaia, colour, shared_concerns=shared, options=options, gaia_candidates=candidates)
    scientific_colour = dict(colour)
    fallback_used = False
    fallback_colour, fallback_colour_source = None, None
    if options.allow_explorer_fallback and selection["effective_temperature"] is None and not nonstellar:
        from temperature_legacy import explorer_temperature_fallback
        fallback_colour = c if c is not None else number(source.get("bp_rp"))
        fallback_colour_source = "intrinsic BP-RP" if c is not None else "observed BP-RP; reddening unavailable, not corrected"
        legacy_z = number(source.get("metallicity"))
        if legacy_z is None:
            legacy_z = number(source.get("mh_gspphot"))
        if fallback_colour is not None and fallback_colour < 0:
            legacy_z = None  # Explorer's blue branch does not use composition.
        legacy_t, legacy_method = explorer_temperature_fallback(fallback_colour, mv, legacy_z)
        if legacy_t is not None:
            fallback_used = True
            original_reason = selection["temperature_selection_reason"]
            colour = {"temperature": legacy_t, "eligible": True, "method": legacy_method,
                      "approximate": True, "review": True, "status": "needs_review",
                      "uncertainty": None, "lower": None, "upper": None,
                      "concerns": [original_reason,
                          "Approximate Explorer fallback requested when scientific methods are unavailable; applicability and accuracy unvalidated",
                          "Input: " + fallback_colour_source,
                          "No measured gravity or temperature uncertainty inferred; not suitable for precise stellar classification"]}
            selection = select_adopted_temperature(gaia, colour, shared_concerns=shared,
                                                   options=options, gaia_candidates=candidates)
            selection["temperature_selection_reason"] = "Approximate Explorer BP-RP fallback; Gaia and calibrated colour temperatures unavailable. Review required."
            h = None
            z = legacy_z
            z_source = "Raw Gaia metallicity used by legacy Explorer relation; unvalidated" if z is not None else "No metallicity input; legacy Explorer colour-only relation"
            metallicity_reason = "Explorer compatibility fallback; scientific calibration composition policy does not apply"
    correlation = "Gaia photometry shared; agreement is not independent validation"
    if context.get("extinction_source") == "Gaia GSP-Phot" or (h_usable and not assumed_h):
        correlation += "; fitted Gaia reddening/gravity shared; covariance unavailable"
    hs = candidates["Gaia ESP-HS"]
    return {**selection,
        "gaia_temperature": gaia["temperature"] if gaia["eligible"] else None, "gaia_temperature_source": gaia["source"] if gaia["eligible"] else None,
        "esphs_status": "needs_review" if hs["eligible"] and hs["review"] else "conditional" if hs["eligible"] else "unavailable",
        "esphs_notes": "; ".join(hs["concerns"]),
        "bp_rp_temperature": colour["temperature"], "bp_rp_temperature_error": colour.get("uncertainty"),
        "bp_rp_temperature_lower": colour.get("lower"), "bp_rp_temperature_upper": colour.get("upper"),
        "bp_rp_temperature_method": colour["method"], "bp_rp_temperature_status": colour["status"],
        "bp_rp_temperature_approximate": bool(colour.get("approximate")),
        "bp_rp_temperature_notes": "; ".join(colour["concerns"]),
        "scientific_bp_rp_temperature": scientific_colour["temperature"],
        "scientific_bp_rp_status": scientific_colour["status"],
        "scientific_bp_rp_notes": "; ".join(scientific_colour["concerns"]),
        "fallback_colour": fallback_colour, "fallback_colour_source": fallback_colour_source,
        "casagrande_temperature": ordinary["temperature"], "casagrande_status": ordinary["status"],
        "cool_dwarf_temperature": cool.teff_k, "cool_dwarf_notes": "; ".join(cool.notes),
        "gravity_adopted": h, "gravity_source": "Not used by Explorer fallback" if fallback_used else "unavailable" if h is None else "assumed representative value" if assumed_h else "Gaia GSP-Phot model",
        "metallicity_adopted": z, "metallicity_source": z_source,
        "metallicity_requested": requested_z, "metallicity_requested_source": requested_z_source,
        "metallicity_policy_reason": metallicity_reason,
        "population_hypothesis": population + ": " + population_source,
        "temperature_hypotheses": "; ".join(hypotheses) or None, "temperature_sensitivity": "; ".join(sensitivity) or None,
        "temperature_shared_inputs": correlation, "red_dwarf_candidate": screen,
        "photometry_status": "; ".join(quality_reasons) or "passes application screens",
        "corrected_excess_flux": quality["c_star"],
        "bp_rp_excess_correctness": "Acceptable" if quality["passes"] is True else "Unreliable" if quality["passes"] is False else "Unassessed",
        "calculation_version": VERSION, "temperature_options": asdict(options),
    }
