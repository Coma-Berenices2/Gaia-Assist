"""Chemical candidate status is independent of temperature and luminosity class."""
CARBON_FIELDS = ("spectraltype_esphs", "carbon_star_status", "carbon_star_badge",
    "carbon_identification_source", "carbon_reference", "carbon_review_reason",
    "ordinary_star_equivalent", "bp_rp_temperature_method", "bp_rp_temperature_approximate")
EXPLANATION = "Gaia’s spectral classifier detected features consistent with a carbon star. This candidate flag does not by itself confirm the classification."
FALLBACK_NOTE = "Based on an ordinary-star formula; carbon-rich spectra may bias this estimate."


def normalized_tag(value):
    if value is None or bool(getattr(value, "mask", False)):
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    tag = str(value or "").strip().upper()
    return "" if tag in ("", "--", "-", "NONE", "NULL", "NAN") else tag


def is_carbon(record):
    record = record.get("_analysis_data", record)
    return record.get("carbon_star_status") in ("candidate", "externally identified") or normalized_tag(record.get("spectraltype_esphs")) == "CSTAR"


def identification(source):
    tag = normalized_tag(source.get("spectraltype_esphs"))
    candidate = tag == "CSTAR"
    return {
        "carbon_star_status": "candidate" if candidate else "no candidate tag returned" if tag else "tag unavailable",
        "carbon_star_badge": "Carbon-star candidate — Gaia" if candidate else None,
        "carbon_identification_source": "Gaia DR3 ESP-ELS" if candidate else None,
        "carbon_reference": None,
        "carbon_review_reason": EXPLANATION if candidate else "No carbon-star conclusion can be drawn from an absent CSTAR tag.",
    }


def annotate_classification(source, result):
    result.update(identification(source))
    result["ordinary_star_equivalent"] = None
    if result["carbon_star_status"] != "candidate":
        return
    original = result.get("star_type")
    result["ordinary_star_equivalent"] = original if original and original != "N/A" else None
    result["star_type"] = "Carbon-star candidate — Gaia"
    if original and original != "N/A":
        result["classification_status"] = "chemical candidate; ordinary-star-equivalent estimate only, not established spectral class"
    else:
        result["classification_status"] = "chemical candidate; luminosity/subtype unclassified"
    if result.get("bp_rp_temperature_approximate") and result.get("adopted_temperature_source") == "BP-RP":
        result["classification_status"] += "; approximate temperature"
        result["carbon_review_reason"] += f" Approximate colour temperature: {result['effective_temperature']:.0f} K. " + FALLBACK_NOTE
        result["temperature_concerns"] = result.get("temperature_concerns", "") + "; " + FALLBACK_NOTE
