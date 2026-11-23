# Scientist database selection

The desktop and browser Scientist interfaces now offer **Database** with four explicit choices:

| Choice | Gaia DR3 TAP endpoint | Gaia tables | Geometric distances |
| --- | --- | --- | --- |
| ESA Gaia (official), default | `https://gea.esac.esa.int/tap-server/tap` | `gaiadr3.gaia_source`, `gaiadr3.astrophysical_parameters` | ESA `external.gaiaedr3_distance` |
| ARI Heidelberg | `https://gaia.ari.uni-heidelberg.de/tap` | Same Gaia names | GAVO `gedr3dist.main` |
| Gaia@AIP | `https://gaia.aip.de/tap` | Same Gaia names | GAVO `gedr3dist.main` |
| MAST | `https://mast.stsci.edu/vo-tap/api/v0.1/gaiadr3` | `dbo.gaia_source`, `dbo.astrophysical_parameters` | GAVO `gedr3dist.main` |

GAVO's distance endpoint is `https://dc.g-vo.org/tap`. These are the published Bailer-Jones et al. (2021) EDR3 geometric estimates. The existing Scientist distance policy, percentile bounds and flag interpretation are retained, with no second parallax correction and no photogeometric substitution.

## Use it for the temporary ESA outage

1. Restart the application and select **Scientist**.
2. Set **Database → ARI Heidelberg** in the main window. The same choice is available under **Network Settings**.
3. Open **Bulk Query**, use **Load Text File** with the candidate list, choose DR3 and the result fields, and start the query.
4. Inspect the measurements, availability/quality notes and recorded providers before interpreting the results. Save the new run separately from historical Explorer results.

The desktop preference is stored in `scientist_network_settings.json`. Old settings files without a database field still select ESA. In the browser, the selector applies to both single and bulk requests and is scoped to the request; it does not change other users' active requests. A running query/bulk run captures its settings, so a later UI selection cannot move its remaining batches to another service.

The choice is explicit: an alternative does not silently fall back to ESA or another mirror. A missing source is reported; absent AP rows retain source measurements; an AP failure remains distinguishable from catalogue absence. Alternative choices also route optional distances to GAVO, removing the old hidden dependency on ESA's external distance table. Dust-map and sky-image services are independent and still behave as before. This is online mirror selection, not a strict offline mode. Explorer's original query path is unchanged.

## Transport and cache behavior

ESA retains its JSON transport and existing synchronous/asynchronous threshold. Alternatives use short synchronous POST queries with VOTable responses and the existing cancellation, request/overall deadlines, worker process and concurrency limit. Transient sync requests can retry safely without creating persistent UWS jobs. There is no per-star retry caused by blank astrophysical values.

The decoder handles TABLEDATA and binary VOTables, checks all `QUERY_STATUS` entries including trailing `ERROR` and `OVERFLOW`, preserves exact ID strings and character flags such as `01`, and keeps missing values unavailable. It includes the Windows 64-bit null-metadata parsing fix discovered while fetching ARI data. MAST queries include an explicit `TOP` plus `MAXREC`, as live testing showed overflow responses without `TOP`. DR3 schema references are mapped to `dbo`; MAST DR1 crossmatching is rejected with an explanatory error rather than sent to ESA.

Raw cache keys now include the selected provider and endpoint. The cache version changed, so the old cache remains on disk but is not reused under the new keys; first queries can require fresh downloads. Within the selected provider, temperature/distance settings changes can still reuse raw catalogue inputs. Force refresh bypasses that provider's cache. Failed or invalid results are not cached as successful absence. Source/AP IDs and duplicate/unexpected response IDs are checked before caching.

New results retain the Gaia database, endpoint, DR3 release and original retrieval UTC time. Distance results retain their database, endpoint, table and original retrieval UTC time. Cache reads preserve the original retrieval time instead of pretending a new request occurred. Provider fields are kept in saved JSON and exports even when bulk columns are hidden. Historical records lacking these fields remain readable and are not assigned invented provenance.

## Evidence and limits

Earlier live queries on **11 October 2026** returned a real candidate's source and AP row from ARI, AIP and MAST. ARI then returned **495 source records and 487 AP rows** for the supplied list, and GAVO returned **495 geometric-distance rows**. The eight absent AP rows were successful no-matches, not query failures. These are candidate IDs; no membership confirmation follows from catalogue availability.

This integration replays six original one-object VOTables captured from those three working services, including ARI binary data and AIP/MAST TABLEDATA. The fixtures' original queries, endpoints, UTC times and response hashes are in `tests/fixtures/gaia_mirrors/provenance.json`. Tests verify transport routing, the worker's selected-service snapshot, explicit TOP/schema selection, exact IDs/flags, overflow rejection, absent/failed AP behavior, independent caches, original timestamps, saved provenance and the browser's per-request choice.

## Optional distances and classification fallback

The missing-values logger now recognizes both catalogue and derived fields, including distance metadata. New or unknown fields are recorded by their field names. An unwritable diagnostic log produces a debug warning and does not abort the results. Empty diagnostic messages and unavailable retrieval timestamps are not treated as missing measurements.

An optional geometric-distance timeout, service error, no-match or invalid interval retains the Gaia measurements. Scientist uses the existing inverse-parallax fallback when parallax is positive and its signal-to-noise is at least 5, including when Bayesian geometric mode was requested. The adopted method and selection reason show the fallback; the original distance query status and error remain available for diagnosis. Such failures do not generate a whole-query error popup.

If a full HR-diagram classification cannot be calculated, a usable adopted temperature can provide a rough family such as `A-like (temperature only)`. Its classification status explicitly says that the luminosity class is unresolved. Missing distance or extinction is not replaced by invented values, and temperature-only labels do not enter the spectral/luminosity census. Ordinary-star temperature estimates remain secondary to a Gaia carbon-star candidate tag, and galaxy/quasar identifications do not receive a stellar fallback. Explorer comparisons retain their original calculation and are not silently promoted to the Scientist classification. New calculations record version `temperature-comparison-2.6`; saved historical records are not recalculated on load.

The reported source `5541418314860750080` was replayed through the corrected desktop and browser query pipelines using its actual previously downloaded AIP/GAVO cache records. Both finished successfully. Its geometric distance was retrieved (about 907.87 pc), Automatic mode adopted inverse parallax (about 928.44 pc), and the adopted 9318 K temperature yielded `A-like (temperature only)`. Extinction remains unavailable, so a secure luminosity class cannot be inferred; the separate Explorer comparison remains `A4V, A5V`. This replay made no new database request.

The initial integration run could not make a new live request from the restricted workspace. Subsequent user application logs show successful source/AP and GAVO requests from all three mirror selections on 11 October 2026; the corrected app also completes the reported source using those cached records. The current complete regression suite passes all **151 tests**, including desktop/browser single and bulk results, simulated optional-distance failures, diagnostic logging failures, missing distance/extinction, and browser routing. The browser-routing tests required permission to use local sockets. The generated browser JavaScript previously passed its syntax check. The 495-object Scientist analysis has not been run or scientifically reviewed by this integration task.

References: [ARI TAP](https://gaia.ari.uni-heidelberg.de/tap.html), [AIP scripted access](https://gaia.aip.de/cms/services/scripted-access/), [MAST Gaia DR3 TAP](https://mast.stsci.edu/vo-tap/api/v0.1/gaiadr3/), [GAVO table metadata](https://dc.g-vo.org/tableinfo/gedr3dist.main), [Bailer-Jones catalogue](https://bailer-jones.www3.mpia.de/gedr3_distances.html).
