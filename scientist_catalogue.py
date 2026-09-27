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
    if kind == "parameters":
        return f"SELECT source_id, {', '.join(PARAMETER_FIELDS)} FROM gaiadr3.astrophysical_parameters WHERE source_id IN ({','.join(ids)})"
    fields = ", ".join("g."+key for key in SOURCE_FIELDS)
    join = ""
    if kind == "joined":
        fields += ", a.source_id AS ap_source_id, " + ", ".join("a."+key for key in PARAMETER_FIELDS)
        join = " LEFT OUTER JOIN gaiadr3.astrophysical_parameters AS a ON g.source_id=a.source_id"
    return f"SELECT {fields} FROM gaiadr3.gaia_source AS g{join} WHERE g.source_id IN ({','.join(ids)})"


def fetch(ids, release="DR3", on_basic=None):
    """One joined job normally; recover basic records if optional join fails.

    A successfully returned null row is cached, never a reason for another job.
    Cache keys include release and the complete requested schema.
    """
    import Main_temperature as app
    context = net.CURRENT.get()
    options = context.options if context else net.settings()
    force = bool(context and context.force_refresh)
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
                lambda: net.tap_query(build_query(missing), len(missing), limit=options.optional_timeout))
            found = {str(row["source_id"]): row for row in rows}
            for identifier in missing:
                row = found.get(identifier)
                sr = None if row is None else {k: row.get(k) for k in SOURCE_FIELDS}
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
                rows = net.tap_query(build_query(missing, "source"), len(missing))
                found = {str(r["source_id"]): r for r in rows}
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
            rows = net.tap_query(build_query(enrich, "parameters"), len(enrich), limit=options.optional_timeout)
            found = {str(r["source_id"]): r for r in rows}
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
            errors[identifier] = app.QueryServiceError("ESA Gaia", "Query completed; no source found for "+identifier)
    return results, errors
