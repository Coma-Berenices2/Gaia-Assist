"""Named Gaia DR3 services and lossless TAP VOTable decoding."""
from dataclasses import dataclass
import io
import math
import re
import xml.etree.ElementTree as ET

ESA_ENDPOINT = "https://gea.esac.esa.int/tap-server/tap"
GAVO_ENDPOINT = "https://dc.g-vo.org/tap"


@dataclass(frozen=True)
class CatalogueService:
    key: str
    label: str
    endpoint: str
    dr3_schema: str = "gaiadr3"

    @property
    def distance_endpoint(self):
        return ESA_ENDPOINT if self.key == "esa" else GAVO_ENDPOINT

    @property
    def distance_table(self):
        return "external.gaiaedr3_distance" if self.key == "esa" else "gedr3dist.main"


SERVICES = {
    "esa": CatalogueService("esa", "ESA Gaia (official)", ESA_ENDPOINT),
    "ari": CatalogueService("ari", "ARI Heidelberg", "https://gaia.ari.uni-heidelberg.de/tap"),
    "aip": CatalogueService("aip", "Gaia@AIP", "https://gaia.aip.de/tap"),
    "mast": CatalogueService("mast", "MAST", "https://mast.stsci.edu/vo-tap/api/v0.1/gaiadr3", "dbo"),
}
SERVICE_LABELS = {key: value.label for key, value in SERVICES.items()}
ID_FIELDS = {"source_id", "ap_source_id", "dr3_source_id", "dr2_source_id", "dr1_source_id"}
TEXT_FIELDS = ID_FIELDS | {"flag", "flags_esphs", "flags_gspspec", "flags_flame", "spectraltype_esphs", "libname_gspphot"}


def prepare_query(query, service, count):
    if service.key == "mast":
        if re.search(r"\bgaiadr[12]\.", query, re.I):
            raise ValueError("MAST's selected service is DR3 only. Use a DR3 ID or select ESA, ARI, or AIP for DR1 crossmatching.")
        query = re.sub(r"\bgaiadr3\.", "dbo.", query, flags=re.I)
        # Live MAST tests returned OVERFLOW without TOP, even for one ID.
        if not re.search(r"\bSELECT\s+(?:DISTINCT\s+)?TOP\b", query, re.I):
            query = re.sub(r"\bSELECT\b", "SELECT TOP " + str(count + 10), query, count=1, flags=re.I)
    return query


def parse_votable(raw):
    """Retain exact IDs, character flags and missing values across TD/binary.

    Reject every ERROR/OVERFLOW marker, including those after the result table.
    Original bytes need not be modified to work around Windows long-null parsing.
    """
    root = ET.fromstring(raw)
    infos = [e for e in root.iter() if e.tag.rsplit("}", 1)[-1] == "INFO"
             and e.attrib.get("name", "").upper() == "QUERY_STATUS"]
    status = [e.attrib.get("value", "").upper() for e in infos]
    if "OK" not in status or any(s in ("ERROR", "OVERFLOW") for s in status):
        raise ValueError("TAP status " + str(status) + ": " + "; ".join("".join(e.itertext()) for e in infos)[:600])
    tables = [e for e in root.iter() if e.tag.rsplit("}", 1)[-1] == "TABLE"]
    if len(tables) != 1:
        raise ValueError("Expected one TAP result table")
    element = tables[0]
    fields = [e for e in element if e.tag.rsplit("}", 1)[-1] == "FIELD"]
    names = [f.attrib["name"].lower() for f in fields]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate TAP result column")
    tabledata = next((e for e in element.iter() if e.tag.rsplit("}", 1)[-1] == "TABLEDATA"), None)
    if tabledata is not None:
        rows = []
        for tr in tabledata:
            cells = list(tr)
            if len(cells) != len(fields):
                raise ValueError("TAP row/column count mismatch")
            row = {}
            for name, field, cell in zip(names, fields, cells):
                value = cell.text
                dtype = field.attrib.get("datatype", "char")
                null = next((e.attrib.get("null") for e in field if e.tag.rsplit("}", 1)[-1] == "VALUES"), None)
                if value is None or value == "" or value == null:
                    value = None
                elif name in ID_FIELDS:
                    if dtype not in ("long", "int", "short", "unsignedByte", "char", "unicodeChar") or not re.fullmatch(r"[0-9]+", value):
                        raise ValueError("Catalogue identifier is not an exact integer/string")
                elif name in TEXT_FIELDS or dtype in ("char", "unicodeChar"):
                    value = str(value)
                elif dtype in ("long", "int", "short", "unsignedByte"):
                    value = int(value)
                elif dtype in ("float", "double"):
                    value = float(value)
                    if not math.isfinite(value):
                        value = None
                elif dtype == "boolean":
                    value = value.lower() in ("1", "t", "true")
                else:
                    raise ValueError("Unsupported TAP datatype: " + dtype)
                row[name] = value
            rows.append(row)
        return rows
    # Astropy's Windows parser can overflow on VALUES/null for datatype long.
    long_nulls = {}
    for field in fields:
        if field.attrib.get("datatype") == "long":
            for child in field:
                if child.tag.rsplit("}", 1)[-1] == "VALUES" and "null" in child.attrib:
                    long_nulls[field.attrib["name"].lower()] = int(child.attrib.pop("null"))
    from astropy.io.votable import parse_single_table
    table = parse_single_table(io.BytesIO(ET.tostring(root))).to_table(use_names_over_ids=True)
    rows = []
    for record in table:
        row = {}
        for name in table.colnames:
            key = name.lower()
            value = record[name]
            if bool(getattr(value, "mask", False)):
                value = None
            elif hasattr(value, "item"):
                value = value.item()
            if isinstance(value, bytes):
                value = value.decode("utf-8")
            if key in long_nulls and value == long_nulls[key]:
                value = None
            if isinstance(value, float) and not math.isfinite(value):
                value = None
            if key in ID_FIELDS and value is not None and (isinstance(value, (float, bool)) or not str(value).isascii() or not str(value).isdigit()):
                raise ValueError("Catalogue identifier is not an exact integer/string")
            if key in TEXT_FIELDS and value is not None:
                value = str(value)
            row[key] = value
        rows.append(row)
    return rows
