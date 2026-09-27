# Scientist 2.3: query timing, caching and carbon-star candidates

Launch `Main.py`, select Scientist, and rerun the query. Explorer's file and calculations are unchanged. The new behaviour is shared by the Scientist desktop and web applications.

## Query strategy and measured limits

The original September 21 log shows successful first attempts taking about 13m28s for source data and 11m48s for parameters. It does not identify queue, execution, polling or download time. Blank catalogue temperatures are not evidence that either request was retried.

Scientist now normally makes one `LEFT OUTER JOIN` from `gaiadr3.gaia_source` to optional `gaiadr3.astrophysical_parameters`. Sources without a parameter row remain in the result. Single IDs and batches of up to 20 use synchronous TAP; larger requests use bounded asynchronous jobs. Default bulk batches contain 20 IDs. Duplicate input IDs share the remote lookup but retain their individual input rows.

Two small, sequential live comparisons were run against ESA on September 21. These are observations under changing server/network conditions, not controlled server-performance measurements:

| Request | Sync elapsed | Async outcome |
|---|---:|---|
| One source, source table only | 7.942 s | Request timed out at 8.707 s |
| One source, joined parameters | 9.474 s | Request timed out at 8.701 s |
| Two sources, joined, first pass | Timed out at 8.710 s | Timed out at 8.710 s |
| Two sources, joined, second pass | 6.510 s | Overall wait timed out |
| Twenty sources, joined, second pass | 7.818 s | Overall wait timed out |

The first pass used an 8-second socket timeout; the second used 12 seconds, both with a 15-second operation budget. In the second benchmark, best-effort cleanup added approximately 1.7 seconds after the async wait limit; remote abort could not be confirmed. The final implementation reserves cleanup time **within** the async operation budget. Benchmark timeouts do not establish how long those server jobs would have taken to finish. The sample supports using the short synchronous path here; neither sync nor a join guarantees faster server execution. Raw results are retained in `scientist_network_benchmark.json` and `scientist_network_batch_benchmark.json`. The opt-in benchmark script never runs at startup.

If the joined request fails or times out, Scientist uses remaining time for a source-only query. This is recovery of basic data, not a retry because GSP fields are blank. A subsequent lookup can display the cached basic record immediately while requesting missing optional parameters. Successful null fields and absent parameter rows are cached; neither starts another request. Failures/timeouts are never cached as proof that catalogue data are absent.

## Progress, deadlines and cancellation

`temperature_debug.log` records monotonic elapsed durations for resolution, cache hit/miss, HTTP submission/headers, download, parsing, async queue/execution phases when reported by Gaia, dust lookup and temperature calculation. Synchronous submission-to-headers includes network and server work; it cannot separate unreported server queueing from execution. Async phase durations are observations at the polling interval, not exact server timestamps.

The interface reports stages such as waiting for Gaia data/parameters, cached results, and dust lookup. Basic results and an available approximate colour temperature are displayed before optional dust lookup. Desktop and web bulk tables update completed rows incrementally. Cached basic rows are shown before separate parameter enrichment. Browser updates use a streamed response and disconnect cancellation; desktop events carry a query generation so a stale result cannot overwrite another query. Loading saved results cancels the active query generation.

**Network Settings** configures per-request timeout (15 s), overall time per query/batch (60 s), optional-data wait (20 s), cache expiry (24 h), batch size, sync threshold, attempts and polling interval. Web controls expose request/overall/optional waits and cache expiry; other defaults come from the same local settings file. A large bulk run is a sequence of individually bounded batches, not one 60-second run. **Force refresh** bypasses existing cache entries. **Cancel** retains already displayed results.

Network operations run in a killable process that imports only the network worker, not the desktop launcher or its Gaia singleton. This bounds DNS, socket stalls, parsing and repeated polling without accumulating abandoned network threads. At most three network children and three per-batch calculation workers run concurrently. Async cancellation requests `PHASE=ABORT` when the job address is known; cancellation is best effort, and failure to confirm it is logged. An ambiguous job-creation POST is not resubmitted, since doing so could create duplicate jobs.

GET retries are limited to transient connection/timeouts and HTTP 408/429/500/502/503/504, with bounded backoff and the same deadline. Empty successful responses and deterministic query errors are not retried. Bulk failures do not trigger a fresh job for every star. UI states distinguish `retrieved` (possibly blank values), `no_row`, `query_failed`, `query_timed_out`, and a pending enrichment.

## Cache and local recalculation

`scientist_cache.sqlite3` stores source rows, optional parameter rows, successful empty responses, name/release resolutions and dust results. Keys include schema version, Gaia release, exact source ID and requested fields; dust keys include service URL, coordinate system, both coordinates and distance. Each entry has a creation timestamp and configurable expiry. The cache stores raw inputs, so changing temperature settings reruns calculations locally rather than needlessly repeating remote calls. The local cache and network preference files are excluded from version control.

## Carbon-star candidates

ESA documents that [`spectraltype_esphs` is supplied by ESP-ELS](https://gea.esac.esa.int/archive/documentation/GDR3/Gaia_archive/chap_datamodel/sec_dm_astrophysical_parameter_tables/ssec_dm_astrophysical_parameters.html), despite its historical suffix. Whitespace and case are normalized for interpretation, with masked/null values handled as unavailable; the original tag is retained for export.

`CSTAR` produces the prominent badge **Carbon-star candidate — Gaia** and this explanation:

> Gaia’s spectral classifier detected features consistent with a carbon star. This candidate flag does not by itself confirm the classification.

This works with blank temperatures, gravity and metallicity. Other returned tags are recorded as **no candidate tag returned**; missing tags as **tag unavailable**. Neither means “not a carbon star.” There is no hard-coded confirmation for La Superba or any other source, and no external-identification lookup has been added. Fresh results retain an empty external-reference field.

Temperature selection retains its order: applicable calibrated colour estimates, comparison/adoption with usable Gaia estimates, then the enabled Explorer-compatible fallback when neither is eligible. A CSTAR tag keeps its review warnings without deleting that fallback. If observed colour must be used, it is explicitly labelled uncorrected; no gravity, metallicity measurement or error bar is invented.

For a candidate using an approximate colour estimate, the results show its value and: **Based on an ordinary-star formula; carbon-rich spectra may bias this estimate.** Any inferred ordinary K/M subtype is moved to **Ordinary-Star-Equivalent Estimate (Not Established Class)**. Chemical candidate status remains separate from temperature provenance and inferred luminosity/subtype information.

**Carbon-star candidates** filters are available in desktop/web bulk tables and desktop cluster charts. Filtering does not delete source records. Candidates remain eligible for the CMD under the existing plot limits and user-selected contamination filter. Spectral summaries count carbon candidates separately and do not also put them into ordinary K/M grid cells. The candidate is a chemical designation, not a luminosity-class row.

## Saved results and checks

Single and bulk saves produce JSON, text and CSV companions. JSON/CSV retain numerical precision; display/text temperatures are rounded. Carbon status, original tag, identification source/reference, method, approximate flag and review notes are retained even when bulk columns are hidden. CSV and text imports preserve exact ID digits and leading zeroes in flags. Existing saved records remain readable; missing candidate metadata is derived from stored tags without fetching a new identification or recalculating temperatures.

106 offline tests pass, covering the original features and new cache/null/timeout/retry paths, cancellation and worker reaping, partial bulk failures, stale previews, tag normalization, fallback preservation, separate spectral totals, CMD retention, and JSON/text/CSV round trips. Real worker processes are tested with a **mock slow service**, independently of the live ESA comparisons above. Browser JavaScript syntax and streaming event generation are checked; the web checks are not a full browser-driven end-to-end test.

The regression input BP−RP = 2.593668, no metallicity and no reddening correction returns approximately **3472.88 K** through the existing colour-only polynomial. This checks fallback execution only. It is **not** a physical temperature benchmark or confirmed classification for source `1542553623374596352`.
