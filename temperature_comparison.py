"""Local comparison and radius estimates; never reinterpret historical records."""
from math import log10
from temperature_model import number
from temperature_legacy import explorer_temperature_fallback


COMPARISON_FIELDS = {
    "explorer_comparison_temperature": "Explorer comparison temperature (approximate)",
    "explorer_comparison_radius": "Explorer comparison radius (approximate)",
    "explorer_comparison_classification": "Explorer comparison classification (approximate)",
    "explorer_comparison_notes": "Explorer comparison assumptions",
    "radius_approx_solar": "Approximate radius — G-band method",
    "radius_approx_temperature_source": "Approximate radius temperature source",
    "radius_approx_absolute_g": "Approximate radius absolute G used",
    "radius_approx_extinction_assumptions": "Approximate radius extinction assumptions",
    "radius_approx_notes": "Approximate radius review notes",
    "bc_g": "Supplied G-band bolometric correction",
    "bc_g_applicable": "Bolometric correction applicability confirmed",
    "bc_g_source": "Bolometric correction source",
    "bolometric_luminosity": "Bolometric luminosity",
    "bolometric_radius_temperature_source": "Bolometric radius temperature source",
}
RADIUS_EXPLANATION = ("Uses G-band brightness as a proxy for total luminosity. "
    "Assumes a solar-like bolometric correction; accuracy depends on the stellar spectrum.")


def safe_radius(magnitude, temperature, solar_magnitude=4.67):
    m, t = number(magnitude), number(temperature)
    if m is None or t is None or t <= 0:
        return None
    try:
        value = number(10 ** (0.2 * (solar_magnitude - m)) * (5772.0 / t) ** 2)
        return value if value is not None and value > 0 else None
    except (OverflowError, ZeroDivisionError):
        return None


def calculate_local_comparisons(source, derived, methods):
    """Reuse Explorer equations with available local inputs; no new requests."""
    out = dict.fromkeys(COMPARISON_FIELDS)
    ag = number(derived.get("mean_g_band_extinction"))
    mg = number(derived.get("absolute_magnitude"))
    extinction_source = derived.get("extinction_source")
    extinction_status = derived.get("extinction_status")
    if ag is None:
        # Gaia may supply A_G even when its colour reddening is absent.
        catalogue_ag = number(source.get("ag_gspphot"))
        if catalogue_ag is not None and catalogue_ag >= 0:
            ag = catalogue_ag
            extinction_source = "Gaia GSP-Phot A_G (independent of colour-reddening availability)"
            extinction_status = "catalogue estimate; review extinction bounds"
    if mg is None:
        g, d = number(source.get("phot_g_mean_mag")), number(derived.get("adopted_distance_pc", derived.get("distance_parsecs")))
        if g is not None and d is not None and d > 0:
            mg = g - 5 * log10(d) + 5
            if ag is not None and ag >= 0:
                mg -= ag
    corrected = mg is not None and ag is not None and ag >= 0
    if corrected:
        assumptions = f"A_G = {ag:g} mag; {extinction_source}; {extinction_status}"
    else:
        # An uncorrected measurement is not an inferred zero extinction.
        g, d = number(source.get("phot_g_mean_mag")), number(derived.get("adopted_distance_pc", derived.get("distance_parsecs")))
        mg = g - 5 * log10(d) + 5 if g is not None and d is not None and d > 0 else None
        assumptions = "Uncorrected absolute G; extinction unknown, not assumed zero"
    out.update(radius_approx_absolute_g=mg, radius_approx_extinction_assumptions=assumptions,
        radius_approx_temperature_source=derived.get("adopted_temperature_source"),
        radius_approx_solar=safe_radius(mg, derived.get("effective_temperature")),
        radius_approx_notes=RADIUS_EXPLANATION + " Conditional approximate estimate; no uncertainty inferred. "
            + str(derived.get("temperature_concerns") or ""))
    colour = number(derived.get("new_bp_rp"))
    colour_note = "Selected extinction-corrected BP-RP"
    if colour is None:
        colour = number(source.get("bp_rp"))
        colour_note = "Observed BP-RP; reddening unknown, not assumed zero"
    absolute = {"absolute_magnitude": mg}
    visual = methods.calculate_visual_absolute_magnitude({"new_bp_rp": colour}, absolute)
    t, method = explorer_temperature_fallback(colour, visual["visual_absolute_magnitude"], source.get("metallicity"))
    t = round(t, 6) if t is not None else None  # Original Explorer rounding.
    temperature = {"effective_temperature": t}
    try:
        radius = methods.calculate_legacy_radius(methods.calculate_luminosity(absolute), temperature)["radius"]
        radius = number(radius)
    except (OverflowError, ZeroDivisionError):
        radius = None
    out.update(explorer_comparison_temperature=t, explorer_comparison_radius=radius,
        explorer_comparison_classification=methods.calculate_star_type(source, temperature, visual)["star_type"],
        explorer_comparison_notes=f"Approximate ordinary-star equivalent; {method}. {colour_note}. {assumptions}. "
            "Original Explorer formulas using locally available inputs and raw Gaia metallicity when present; "
            "not an independent measurement or a chemical identification.")
    from temperature_carbon import is_carbon
    if is_carbon(source):
        warning = " Carbon-rich spectra may bias ordinary-star colour and G-band estimates; chemical identification takes precedence."
        out["explorer_comparison_notes"] += warning
        out["radius_approx_notes"] += warning
    # BC must be explicitly vetted for this object, passband and adopted parameters.
    bc = number(source.get("bc_g"))
    applicable = source.get("bc_g_applicable") is True
    provenance = source.get("bc_g_source")
    out.update(bc_g=bc, bc_g_applicable=source.get("bc_g_applicable"), bc_g_source=provenance,
        radius=None, physical_property_status="Bolometric radius unavailable: no applicable, sourced BC_G or valid corrected inputs")
    if applicable and provenance and bc is not None and corrected:
        radius = safe_radius(mg + bc, derived.get("effective_temperature"), 4.74)
        if radius is not None:
            try:
                lum = number(10 ** (-.4 * (mg + bc - 4.74)))
            except OverflowError:
                lum = None
            if lum is not None and lum > 0:
                out.update(radius=radius, bolometric_luminosity=lum,
                    bolometric_radius_temperature_source=derived.get("adopted_temperature_source"),
                    physical_property_status=f"Conditional Stefan–Boltzmann estimate; BC_G from {provenance}; {assumptions}; no uncertainty inferred")
    return out
