"""Versioned, lossless experiment saves and read-only legacy text import."""
import csv
import json
from pathlib import Path

from temperature_model import VERSION, number
from temperature_carbon import CARBON_FIELDS
from temperature_comparison import COMPARISON_FIELDS
from scientist_distance import RAW_FIELDS as DISTANCE_RAW_FIELDS, DERIVED_FIELDS as DISTANCE_FIELDS

REQUIRED_EXPORT_FIELDS = (*DISTANCE_RAW_FIELDS, *DISTANCE_FIELDS, *COMPARISON_FIELDS, "radius", "physical_property_status", *CARBON_FIELDS, "calculation_version", "effective_temperature",
    "adopted_temperature_source", "temperature_status", "temperature_concerns", "classification_status")


def save_csv(path, records, columns):
    """Flat, full-precision CSV companion; source identifiers and flags stay text."""
    with Path(path).open("x", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), extrasaction="ignore")
        writer.writeheader()
        for row in records:
            data = row.get("_analysis_data", row)
            writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value
                             for key, value in data.items()})


def save_records(path, records):
    # Exclusive creation protects previous records even if a filename is reused.
    with Path(path).open("x", encoding="utf-8") as handle:
        json.dump({"schema_version": 2, "calculation_version": VERSION, "records": records},
                  handle, indent=2, ensure_ascii=False, allow_nan=False)


def normalize_record(record, columns):
    record = dict(record)
    old = not record.get("calculation_version")
    result = dict.fromkeys(columns)
    result.update(record)
    for key, value in result.items():
        if isinstance(value, str) and value in ("-", "", "None", "null"):
            result[key] = None
    if old:
        for key in ("effective_temperature", "radius", "star_type"):
            result["legacy_" + key] = result.get(key)
            result[key] = None
        result["calculation_version"] = "legacy (not recalculated)"
        result["classification_status"] = "unclassified; legacy label preserved separately"
        result["temperature_status"] = "unavailable"
        result["temperature_selection_reason"] = "Legacy file; original temperature retained but not adopted by the new model"
    identifier = result.get("source_id")
    if isinstance(identifier, float):
        raise ValueError("Saved Gaia ID was a float; exact digits cannot be guaranteed")
    if identifier is not None:
        result["source_id"] = str(identifier)
    if result.get("carbon_star_status") is None:
        from temperature_carbon import annotate_classification
        annotate_classification(result, result)
    return result


def load_records(path, columns):
    text = Path(path).read_text(encoding="utf-8-sig")
    if Path(path).suffix.lower() == ".csv":
        rows = list(csv.DictReader(text.splitlines()))
        if not rows or "source_id" not in rows[0]:
            raise ValueError("Not a saved Scientist result CSV")
        return [normalize_record({key: _csv_value(key, value) for key, value in row.items()}, columns) for row in rows]
    if text.lstrip().startswith("{"):
        payload = json.loads(text)
        if payload.get("schema_version") != 2 or not isinstance(payload.get("records"), list):
            raise ValueError("Unsupported saved-result format")
        records = []
        for row in payload["records"]:
            if "_analysis_data" in row:
                row = {**row, "_analysis_data": normalize_record(row["_analysis_data"], columns)}
            else:
                row = normalize_record(row, columns)
            records.append(row)
        return records
    aliases = {label: key for key, label in columns.items()}
    aliases.update({"Effective Temperature": "effective_temperature", "Radius": "radius", "Star Type": "star_type",
                    "Luminosity (Solar Units)": "luminosity", "Visual Absolute Magnitude": "visual_absolute_magnitude",
                    "Visual Apparent Magnitude": "visual_apparent_magnitude"})
    lines = list(csv.reader(text.splitlines(), delimiter="\t"))
    def value(key, text):
        if text in ("-", "", "None", "null"):
            return None
        if key in ("source_id", "bayesian_source_id", "bayesian_distance_flag", "flags_esphs", "spectraltype_esphs", "carbon_reference"):
            return text  # never pass a Gaia ID through float
        if key in ("bp_rp_temperature_approximate", "bc_g_applicable"):
            return text.lower() == "true"
        if key == "temperature_options":
            # Human-readable legacy text may use Python dict formatting. Never eval it.
            return text
        numeric = number(text)
        return numeric if numeric is not None else text
    for i, line in enumerate(lines):
        if line == ["Field", "Value", "Unit"]:
            record = {aliases[row[0]]: value(aliases[row[0]], row[1])
                      for row in lines[i+1:] if len(row) >= 2 and row[0] in aliases}
            return [normalize_record(record, columns)]
        if line and line[0] == "Input Row":
            keys = [aliases.get(label) for label in line[1:]]
            records = []
            for row in lines[i+2:]:
                if not row:
                    continue
                record = {key: value(key, cell) for key, cell in zip(keys, row[1:]) if key}
                record["_input_value"] = row[0]
                records.append(normalize_record(record, columns))
            return records
    raise ValueError("No saved Gaia table found in this file")


def _csv_value(key, value):
    if value == "":
        return None
    if key in ("source_id", "bayesian_source_id", "bayesian_distance_flag", "flags_esphs", "spectraltype_esphs", "carbon_reference"):
        return value
    if key == "temperature_options":
        return json.loads(value)
    if key in ("bp_rp_temperature_approximate", "bc_g_applicable"):
        return value.lower() == "true"
    numeric = number(value)
    return numeric if numeric is not None else value
