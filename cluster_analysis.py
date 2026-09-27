"""Prepare bulk results for cluster charts without importing GUI libraries.

Raw ``_analysis_data`` is retained separately from visible table strings so
changing selected columns or rounding the table does not change the charts.
The existing bulk asterisk reasons are the sole contamination flag.
"""

import math
import re
from collections.abc import Mapping


SPECTRAL_COLUMNS = ("WR",) + tuple(
    f"{family}{subclass}" for family in "OBAFGKM" for subclass in range(10)
) + ("BD",)
LUMINOSITY_ROWS = ("WD", "VI", "V", "IV", "III", "II", "I")
BROWN_DWARF_NOTE = (
    "L, T, Y and brown dwarf labels without a luminosity class are grouped "
    "in BD / V for this chart; V is a display convention for these objects."
)

_COLUMN_INDEX = {name: index for index, name in enumerate(SPECTRAL_COLUMNS)}
_ROW_INDEX = {name: index for index, name in enumerate(LUMINOSITY_ROWS)}
_MISSING_LABELS = {"", "N/A", "NA", "NONE", "NULL", "NAN", "--", "-"}


def _value(row, name):
    raw = row.get("_analysis_data")
    if isinstance(raw, Mapping) and name in raw:
        return raw[name]
    return row.get(name)


def _finite_number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _exclude_row(row, result, include_contaminated):
    result["total"] += 1
    if row.get("_query_failed", False):
        result["failed"] += 1
        return True
    if row.get("_cluster_warning_reasons") and not include_contaminated:
        result["excluded_contaminated"] += 1
        return True
    return False


def prepare_cmd_data(rows, include_contaminated=False):
    """Return finite, in-range CMD points and mutually exclusive row counts.

    Limits are inclusive: New BP-RP -1 through 4 and absolute magnitude -10
    through 15. Missing/non-numeric/non-finite values count as ``missing``.
    Failed queries and excluded contaminated rows are counted before values
    are validated. Neither rows nor their raw analysis fields are changed.
    """
    result = {
        "points": [], "total": 0, "included": 0,
        "excluded_contaminated": 0, "missing": 0, "out_of_range": 0,
        "failed": 0,
    }
    for row in rows:
        if _exclude_row(row, result, include_contaminated):
            continue
        color = _finite_number(_value(row, "new_bp_rp"))
        magnitude = _finite_number(_value(row, "absolute_magnitude"))
        if color is None or magnitude is None:
            result["missing"] += 1
            continue
        if not (-1 <= color <= 4 and -10 <= magnitude <= 15):
            result["out_of_range"] += 1
            continue
        result["points"].append({
            "source_id": _value(row, "source_id"),
            "new_bp_rp": color,
            "absolute_magnitude": magnitude,
            "contaminated": bool(row.get("_cluster_warning_reasons")),
        })
        result["included"] += 1
    return result


def _parse_spectral_classification(value):
    """Return (cell, status, assumed BD/V, multiple estimates present)."""
    if value is None:
        return None, "missing", False, False
    label = str(value).strip().upper()
    if label in _MISSING_LABELS:
        return None, "missing", False, False
    # Preserve the estimator's order as requested: use only its first listed
    # classification, even if a later estimate would be easier to place.
    alternatives = re.split(r"[,;/|]|\bOR\b", label)
    return (*_parse_single_spectral_classification(alternatives[0].strip()),
            len(alternatives) > 1)


def _parse_single_spectral_classification(label):
    label = re.sub(r"\s*\*+\s*$", "", label)
    label = re.sub(r"\s+", "", label)
    if label == "WR":
        return ("WR", "I"), "included", False
    if label in {"BD", "BROWNDWARF"} or re.fullmatch(r"[LTY][0-9]?(?:DWARF)?", label):
        return ("BD", "V"), "included", True
    subdwarf = re.fullmatch(r"SD([OBAFGKM][0-9])(?:VI)?", label)
    if subdwarf:
        return (subdwarf.group(1), "VI"), "included", False
    normal = re.fullmatch(
        r"(WR|[OBAFGKM][0-9]|BD|[LTY][0-9]?)(WD|VI|IV|III|II|IAB|IA|IB|I|V)",
        label,
    )
    if normal:
        spectral, luminosity = normal.groups()
        if spectral[0] in "LTY":
            spectral = "BD"
        if luminosity in {"IA", "IB", "IAB"}:
            luminosity = "I"
        return (spectral, luminosity), "included", False
    return None, "missing", False


def parse_spectral_classification(value):
    """Return the first estimate's (spectral column, row), or None if unknown.

    Recognizes labels emitted by ``Main.format_star_classification``, sd
    prefixes, and common supergiant suffixes. Brown dwarfs lacking an explicit
    luminosity class use the documented BD/V display convention.
    """
    return _parse_spectral_classification(value)[0]


def prepare_spectral_data(rows, include_contaminated=False):
    """Count each star's first listed estimate in one spectral grid cell.

    ``counts`` is indexed by LUMINOSITY_ROWS, then SPECTRAL_COLUMNS.
    ``missing`` includes unknown/unusable first estimates; ``ambiguous`` stays
    zero for compatibility. Exclusion counts and included partition ``total``.
    ``assumed_bd_v`` and ``first_estimate_used`` are subsets of included, with
    the latter counting objects that had multiple estimates to choose from.
    """
    result = {
        "counts": [[0] * len(SPECTRAL_COLUMNS) for _ in LUMINOSITY_ROWS],
        "total": 0, "included": 0, "excluded_contaminated": 0,
        "missing": 0, "ambiguous": 0, "failed": 0, "assumed_bd_v": 0,
        "first_estimate_used": 0,
    }
    for row in rows:
        if _exclude_row(row, result, include_contaminated):
            continue
        cell, status, assumed_bd_v, multiple_estimates = _parse_spectral_classification(
            _value(row, "star_type")
        )
        if cell is None:
            result[status] += 1
            continue
        spectral, luminosity = cell
        result["counts"][_ROW_INDEX[luminosity]][_COLUMN_INDEX[spectral]] += 1
        result["included"] += 1
        result["assumed_bd_v"] += int(assumed_bd_v)
        result["first_estimate_used"] += int(multiple_estimates)
    return result
