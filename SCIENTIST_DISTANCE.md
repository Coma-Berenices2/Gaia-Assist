# Scientist 2.5: baseline and published geometric distances

Explorer is unchanged. Scientist now queries the Bailer-Jones et al. (2021), AJ 161, 147 EDR3 **geometric** catalogue as optional enrichment, independently of GSP temperature, gravity or metallicity. No local Bayesian inference or photogeometric substitution is implemented.

## Verified access and provenance

On 2026-09-23, a live request to ESA's `https://gea.esac.esa.int/tap-server/tap` verified `external.gaiaedr3_distance`. `TAP_SCHEMA.columns` reports `source_id` as a long integer, `flag` as text, and `r_med_geo`, `r_lo_geo`, `r_hi_geo` in parsecs. The latter fields are the posterior median, 16th percentile and 84th percentile. The exact requests and responses are stored in `scientist_distance_service_verification.json`. Test matches included source 1542553623374596352 (median 314.0529 pc, interval 296.1741–330.8101 pc) and 5891675303053080704 (median 707.51666 pc).

The [author's catalogue page](https://bailer-jones.www3.mpia.de/gedr3_distances.html) identifies this ESA table. The [Gaia DR3 release description](https://www.cosmos.esa.int/web/gaia/dr3) confirms that DR3 and EDR3 have identical source lists and shared astrometry. The app first resolves DR1/DR2/name inputs to DR3 using its existing resolver, then matches exact DR3 identifiers. It never joins DR1 or DR2 identifiers directly to this table.

The [author's FAQ](https://bailer-jones.www3.mpia.de/gedr3_distances/FAQ.html) explains that the published inference already includes parallax zero-point treatment. This implementation applies no second correction. It neither averages the two distances nor uses a baseline-derived absolute magnitude as independent distance evidence.

## Selection and checks

The existing Scientist baseline is retained: `1000/parallax_mas`, requiring finite positive parallax and finite `parallax_over_error >= 5`. Missing, zero or negative parallax is never inverted. The lower-level `calculate_distance` helper is additionally hardened to reject negative/nonfinite input; its previous pipeline callers already excluded it. No baseline is fabricated for a Bayesian-only result.

Use **Distance Settings** on desktop or the **Distance settings** section on the web:

- **Baseline:** retains the original inverse-parallax result, including unavailability.
- **Bayesian geometric:** uses a valid published geometric interval; otherwise explicitly falls back to the valid baseline.
- **Automatic** (default): keeps a valid baseline when fractional parallax uncertainty is at most 0.10, otherwise prefers a valid geometric estimate. The threshold is configurable; it is an application policy, not a universal boundary or proof of accuracy. The fractional uncertainty uses `parallax_error/abs(parallax)`, falling back to `1/parallax_over_error` only if the error is unavailable and the parallax and signal-to-noise are positive.

Bayesian eligibility requires an exact source-ID match and finite `0 < lower <= median <= upper`. Raw invalid intervals remain inspectable. Negative or zero measured parallax does not disqualify a valid published Bayesian result.

The [catalogue flag documentation](https://dc.g-vo.org/tableinfo/gedr3dist.main) explicitly advises against using its informational flag as a rejection filter. The app decodes missing G / the HEALpixel magnitude limit and possible geometric-posterior multimodality as review notes. Flag 99 concerns missing photogeometric inputs, so it does not reject a geometric distance; modality information is unassessed. Missing or unrecognized flags retain valid numerical estimates with a review status. Photogeometric-only flag components do not veto a geometric estimate.

RUWE, low/missing parallax signal-to-noise and significant astrometric excess noise remain warnings for every method. The downstream CMD evidence screen is conservative: it retains the baseline S/N >= 10 condition, while Bayesian evidence also requires a sufficiently narrow interval and no unresolved distance warnings. Missing RUWE and flagged intervals therefore cannot silently become strong classification evidence. These screens do not validate the prior or remove correlated/systematic errors.

## One adopted distance, separate comparisons

`adopted_distance_pc` is the explicit input for distance-dependent dust lookup and absolute magnitudes. Brightness, G-band radius, temperature screening, classification and CMD coordinates follow from these recomputed inputs. Published geometric distance stays fixed during this single downstream pass; no distance–extinction–temperature feedback loop is run.

`distance_parsecs` and `distance_lightyears` remain compatibility fields. On **fresh calculations** they alias the adopted distance. Existing loaded records keep the original values without relabelling or recalculation. Baseline distances and status occupy separate fields. All displayed distance types include consistent pc/light-year conversions (the existing factor 3.26156); percentile bounds are never converted into a symmetric error.

The ratio and percentage change compare geometric median to valid baseline. Distance-only diagnostics are `-5*log10(f)` magnitudes, `f*f` brightness and `f` approximate radius, explicitly conditional on fixed extinction and temperature. Baseline absolute G, brightness and approximate radius are also recomputed as labelled comparisons holding the **current** extinction and adopted temperature fixed. They are not claimed to represent a separate baseline dust-map fit. If required inputs are missing they remain unavailable. Actual downstream outputs are recalculated from their own inputs, not multiplied by these diagnostic factors.

## Requests, saved records and UI

Basic results are published before optional distance enrichment. Distance batches use the existing deadline, request timeout, cancellation and process cleanup. A one-second reserve helps local finalization; optional timeout/failure becomes an explicit status rather than dropping a Gaia source. Cancellation discards late distance responses before caching/merging. Desktop query generations and browser abort controls continue to guard the current selection.

Each exact resolved ID is cached with EDR3/catalogue version, table, endpoint and field schema; the existing SQLite timestamps and configurable expiry apply. Successful no-match and incomplete rows are cached. Failures/timeouts are not cached as absence. Force refresh is explicit. Changing selection mode and rerunning reuses cached raw inputs; dust cache keys include the adopted distance, so a changed distance gets its appropriate extinction lookup when needed.

Distance fields are grouped in the main display, with provenance and fixed-input diagnostics in Calculation details. Long values retain the existing ellipsis/full-text behaviour. JSON, CSV, text, bulk and chart exports include baseline, Bayesian interval, adopted method, flags and provenance. Loading never recalculates history, and populated older distance fields remain visible. Save files are not overwritten.

Validation includes original-baseline eligibility, asymmetric and invalid intervals, all selection modes and boundary cases, negative/zero parallaxes without GSP inputs, flag interpretation, exact ID matching, cache/expiry/version/force-refresh behavior, optional timeout/failure and cancellation, stale UI events, adopted-distance consistency, fixed-input factors versus full recalculation, bulk/cache reuse and save/load/export compatibility. The live verification used only read-only ESA queries. Browser JavaScript is syntax checked; no full interactive browser end-to-end test is claimed.
