"""Joined Gaia lookups with separate source/AP caches and graceful degradation."""
import scientist_network as net
from temperature_schema import AP_FIELDS, PHOTOMETRY_FIELDS

SOURCE_FIELDS = ("source_id", "ra", "dec", "l", "b", "pmra", "pmdec", "ra_error", "dec_error",
    "parallax", "parallax_over_error", "astrometric_excess_noise", "astrometric_excess_noise_sig",
    "ruwe", "phot_bp_rp_excess_factor", "radial_velocity", "radial_velocity_error",
    "phot_g_mean_mag", "bp_rp", *PHOTOMETRY_FIELDS)
PARAMETER_FIELDS = ("classprob_dsc_combmod_quasar", "classprob_dsc_combmod_galaxy",
                    "classprob_dsc_combmod_star", *AP_FIELDS)


def build_query(ids, kind="joined"):
    if any(not isinstance(i, str) or not i.isdigit() for i in ids):
        raise ValueError("Gaia identifiers must be exact digit strings")
    schema = net.service().dr3_schema
    top = f"TOP {len(ids)+10} "
    if kind == "parameters":
        return f"SELECT {top}source_id, {', '.join(PARAMETER_FIELDS)} FROM {schema}.astrophysical_parameters WHERE source_id IN ({','.join(ids)})"
    fields = ", ".join("g."+key for key in SOURCE_FIELDS)
    join = ""
    if kind == "joined":
        fields += ", a.source_id AS ap_source_id, " + ", ".join("a."+key for key in PARAMETER_FIELDS)
        join = f" LEFT OUTER JOIN {schema}.astrophysical_parameters AS a ON g.source_id=a.source_id"
    return f"SELECT {top}{fields} FROM {schema}.gaia_source AS g{join} WHERE g.source_id IN ({','.join(ids)})"


def index_rows(rows, ids):
    found = {}
    for row in rows:
        identifier = row.get("source_id")
        if isinstance(identifier, (float, bool)) or not isinstance(identifier, (str, int)) or not str(identifier).isascii() or not str(identifier).isdigit():
            raise net.NetworkFailure("Gaia response source ID is not an exact integer/string")
        identifier = str(identifier)
        if identifier not in ids or identifier in found:
            raise net.NetworkFailure("Gaia response contains an unexpected or duplicate source ID")
        ap_id = row.get("ap_source_id")
        if ap_id is not None and (isinstance(ap_id, (float, bool)) or str(ap_id) != identifier):
            raise net.NetworkFailure("Gaia source/AP identifiers do not match")
        found[identifier] = row
    return found


def query_rows(ids, kind="joined", **kwargs):
    rows = net.tap_query(build_query(ids, kind), len(ids), **kwargs)
    index_rows(rows, ids)  # Validate before writing any successful cache entry.
    return rows


def fetch(ids, release="DR3", on_basic=None):
    """One joined job normally; recover basic records if optional join fails.

    A successfully returned null row is cached, never a reason for another job.
    Cache keys include release and the complete requested schema.
    """
    import Main_temperature as app
    context = net.CURRENT.get()
    options = context.options if context else net.settings()
    force = bool(context and context.force_refresh)
    selected = net.service(options)
    ids = list(dict.fromkeys(ids))
    source_rows, parameters, statuses, errors = {}, {}, {}, {}
    def key(kind, identifier):
        fields = SOURCE_FIELDS if kind == "source" else PARAMETER_FIELDS
        return net.cache_key(kind, [release, identifier, fields])
    for identifier in ids:
        sh, sr = net.cache_get(key("source", identifier), force=force, options=options)
        ph, pr = net.cache_get(key("parameters", identifier), force=force, options=options)
        if sh:
            source_rows[identifier] = sr
        if ph:
            parameters[identifier] = pr
            statuses[identifier] = app.astrophysical_query_status(pr is not None)
    if context and all(i in source_rows and i in parameters for i in ids):
        context.report("Using cached Gaia results; recalculating locally")
    def compose(identifier):
        sr = source_rows.get(identifier)
        if sr is None:
            return None
        result = app.build_source_data_from_gaia_rows(sr, parameters.get(identifier) or app.default_astrophysical_row())
        result.update(gaia_catalogue_service=selected.label, gaia_catalogue_endpoint=selected.endpoint,
                      gaia_catalogue_release="Gaia DR3", gaia_catalogue_retrieved_utc=sr.get("_catalogue_retrieved_utc"))
        result.update(statuses.get(identifier, {"gaia_ap_status": "pending", "gaia_ap_message": "Waiting for optional Gaia parameters"}))
        return result
    for identifier in ids:
        if on_basic and source_rows.get(identifier) is not None and identifier not in parameters:
            on_basic(compose(identifier))
    missing = [i for i in ids if i not in source_rows]
    # Cache successes with no matching source as well as missing optional fields.
    if missing:
        try:
            rows = net.cached("joined", [release, missing, SOURCE_FIELDS, PARAMETER_FIELDS],
                lambda: query_rows(missing, limit=options.optional_timeout))
            found = index_rows(rows, missing)
            for identifier in missing:
                row = found.get(identifier)
                sr = None if row is None else {k: row.get(k) for k in SOURCE_FIELDS}
                if sr is not None:
                    sr["_catalogue_retrieved_utc"] = row.get("_catalogue_retrieved_utc")
                pr = None if row is None or row.get("ap_source_id") is None else {k: row.get(k) for k in PARAMETER_FIELDS}
                source_rows[identifier], parameters[identifier] = sr, pr
                statuses[identifier] = app.astrophysical_query_status(pr is not None)
                net.cache_put(key("source", identifier), sr)
                net.cache_put(key("parameters", identifier), pr)
        except net.QueryCancelled:
            raise
        except net.NetworkFailure as error:
            # Failed enrichment is not cached as catalogue absence. Use remaining
            # time for a source-only lookup, not repeated joins or per-star jobs.
            state = "query_timed_out" if isinstance(error, net.QueryTimeout) else "query_failed"
            for identifier in missing:
                statuses[identifier] = {"gaia_ap_status": state, "gaia_ap_message": str(error)}
            try:
                rows = query_rows(missing, "source")
                found = index_rows(rows, missing)
                for identifier in missing:
                    source_rows[identifier] = found.get(identifier)
                    net.cache_put(key("source", identifier), source_rows[identifier])
                    if on_basic and source_rows[identifier] is not None:
                        on_basic(compose(identifier))
            except net.QueryCancelled:
                raise
            except net.NetworkFailure as basic_error:
                errors.update({i: basic_error for i in missing})
    # Source cache can satisfy the visible preview while optional enrichment runs.
    enrich = [i for i in ids if source_rows.get(i) is not None and i not in parameters and i not in statuses]
    if enrich:
        if context:
            context.report("Waiting for Gaia parameters; basic results available")
        try:
            rows = query_rows(enrich, "parameters", limit=options.optional_timeout)
            found = index_rows(rows, enrich)
            for identifier in enrich:
                parameters[identifier] = found.get(identifier)
                statuses[identifier] = app.astrophysical_query_status(identifier in found)
                net.cache_put(key("parameters", identifier), parameters[identifier])
        except net.QueryCancelled:
            raise
        except net.NetworkFailure as error:
            for identifier in enrich:
                statuses[identifier] = {"gaia_ap_status": "query_timed_out" if isinstance(error, net.QueryTimeout) else "query_failed", "gaia_ap_message": str(error)}
    results = {}
    for identifier in ids:
        record = compose(identifier)
        if record is not None:
            results[identifier] = record
        elif identifier not in errors:
            errors[identifier] = app.QueryServiceError(selected.label, "Query completed; no source found for "+identifier)
    return results, errors
