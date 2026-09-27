# Gaia Assist

Gaia Assist retrieves Gaia DR3 measurements and helps explore stellar properties through a desktop app or a local browser interface. Start **`Main.py`** and choose **Explorer** or **Scientist**.

| Mode | Purpose | Direct desktop entry point |
| --- | --- | --- |
| Explorer | Simple object lookup and the original approximate calculations | `Main.py` → Explorer |
| Scientist | Temperature comparisons, explicit distance selection, provenance and scientific review notes | `Main_temperature.py` |

Scientist is currently **2.5**. It is the focus of future scientific-accuracy improvements. Both modes remain experimental; estimated classifications are not spectroscopic measurements or proof of cluster membership.

## Install and run

Download the **whole repository** using GitHub's **Code → Download ZIP**, extract it, and open a terminal in the extracted folder. Do not download `Main.py` alone. Keep the Python files together with their original names and capitalization.

Use **Python 3.10 or newer**; the current test suite has been run with Python 3.13 on Windows. A desktop display and Tkinter are required for the desktop app. Other operating systems have not been fully verified.

### Windows

Install Python with the Tcl/Tk component enabled, then run:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe Main.py
```

These commands do not require activating the environment or changing PowerShell's execution policy. Choose Explorer or Scientist in the launch window.

### macOS / Linux

With Python and Tkinter installed:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python Main.py
```

Tkinter comes with many Python installers but some Linux distributions package it separately. If `import tkinter` fails, install the Tkinter package matching your Python installation. The app also needs a writable project folder for logs, cached inputs and saved results.

### Python dependencies

`requirements.txt` lists the directly used third-party packages: `astropy`, `astroquery`, `requests`, `numpy` and `matplotlib`. Pip installs their transitive dependencies. Tkinter and SQLite are Python components, not additional pip requirements.

Internet access is required for uncached catalogue, name-resolution, dust-map and sky-image requests. No local Gaia database, API key or GitHub account is needed to use the app. External services can return missing values or be temporarily unavailable.

## Which files do other users need?

The supported distribution includes **all 24 application Python files below**, plus `requirements.txt`. Include `README.md` and `LICENSE` when redistributing. Documentation, tests and deployment configuration belong in the repository but are not runtime dependencies.

```text
Gaia-Assist/
├── Main.py                         # Desktop entry point and Explorer
├── app_launcher.py                 # Explorer / Scientist chooser
├── Main_temperature.py             # Scientist desktop and calculations
├── WebMain.py                      # Explorer browser server
├── WebMain_temperature.py          # Scientist browser server
├── cluster_analysis.py
├── cluster_plots.py
├── cluster_analysis_window.py
├── scientist_aux.py
├── scientist_catalogue.py
├── scientist_distance.py
├── scientist_network.py
├── temperature_carbon.py
├── temperature_cluster_analysis.py
├── temperature_cluster_plots.py
├── temperature_cluster_window.py
├── temperature_comparison.py
├── temperature_evaluation.py
├── temperature_legacy.py
├── temperature_model.py
├── temperature_reference.py
├── temperature_schema.py
├── temperature_storage.py
├── temperature_ui.py
├── requirements.txt
├── README.md
├── LICENSE
├── .gitignore
├── render.yaml                     # Optional Explorer web deployment
├── tests/                          # Developer regression tests
└── SCIENTIST_*.md / TEMPERATURE_EXPERIMENT.md
```

`scientist_network.py` must remain alongside the other files: bounded requests launch it as a separate Python worker. There is no separate `temperature.py` entry point; Scientist uses `Main_temperature.py`.

The two web entry points are optional for desktop-only use. `benchmark_scientist_network.py` and the recorded verification/benchmark JSON files are development evidence, not runtime dependencies. No local spreadsheet or downloaded calibration file is required by the current calculation code.

Do **not** upload or distribute these generated/local items:

- `saved_objects/` and `saved_objects_temperature/` (users' saved results).
- `*.log`, `gaia_missing_values_log.txt` and `temperature_missing_values_log.txt`.
- `scientist_cache.sqlite3*` and `scientist_network_settings.json`.
- `.venv/`, `__pycache__/`, credentials, `.env` files and build/distribution output.

The application creates its own result folders, logs and cache as needed. The repository's `.gitignore` excludes them.

## Desktop workflow

1. Launch `Main.py` and choose a mode.
2. Enter a Gaia DR3 source ID. DR1/DR2 IDs are resolved to DR3 counterparts; common-name lookup through CDS Sesame is experimental.
3. Query the object. Read the measurement quality, assumptions and selection notes alongside the numerical results.
4. Use **Explain** to open field definitions and expanded long values, or **Copy** to select field names, values and units together. Scientist abbreviates long notes on screen while retaining full text for copying and exports.
5. Click **Show Sky Image** for the optional, centred **5.0′ × 5.0′ DSS2 colour (Optical)** cutout. Desktop image loading follows the numerical results, and the image window opens only when requested.
6. Save the results. Explorer saves text; Scientist also saves JSON and CSV and can reload saved results without recalculating history. JSON is preferred for complete records and nested settings.

Retrieved values include positions, proper motion, parallax and quality indicators, Gaia photometry, radial velocity and **radial velocity error**. Additional calculations include extinction, magnitudes, temperature estimates, brightness, radius approximations and tentative classifications.

### Bulk queries and charts

Use **Bulk Query** to paste IDs/names or load input rows, select columns and review the paginated results. Blue asterisks identify stars with the specified potentially unreliable measurements; clicking the warning explains why they may warrant exclusion from cluster analysis.

After a completed desktop bulk query containing at least **10 objects**, **Advanced Cluster Analysis** offers:

- A CMD with New BP−RP horizontally from −1 to 4 and absolute magnitude vertically from −10 at the top to 15 at the bottom. Out-of-range or incomplete points are omitted.
- A spectral classification count grid, with spectral subtypes across columns and luminosity classes down rows. The first listed estimated type is used when there are several possibilities.

Users can include or exclude flagged stars and save figures as PNG, PDF or SVG and chart data as CSV. Scientist keeps carbon-star candidates separate from the ordinary spectral grid. These charts do not independently establish cluster membership.

## Scientist settings and interpretation

### Distance

**Distance Settings** provides:

- **Baseline:** the existing inverse-parallax result, `1000 / parallax_mas`, retaining the Scientist validity checks (finite positive parallax and parallax signal-to-noise at least 5).
- **Bayesian geometric:** the published Bailer-Jones EDR3 geometric distance when usable, otherwise an explicit fallback to the valid baseline.
- **Automatic** (default): retains a usable baseline when fractional parallax uncertainty is at most **10%**; otherwise prefers a usable Bayesian geometric estimate. The threshold is configurable application policy, not a universal scientific boundary.

Baseline, Bayesian median and 16th/84th percentile bounds remain separate from the adopted distance. Catalogue flags and astrometric warnings remain visible. Distance-dependent extinction, magnitudes, radius estimates and classification use the adopted distance consistently. Published distances are not given a second parallax zero-point correction. See [distance implementation and catalogue references](SCIENTIST_DISTANCE.md).

### Temperature, radius and classification

Scientist compares applicable Gaia and BP−RP temperature estimates, records the adopted source and preserves missing values and applicability warnings. An explicitly approximate Explorer fallback is available when stronger estimates are unavailable.

Fresh results also include separately labelled Explorer comparison temperature, radius and classification. These are distinct from historical `legacy_*` values imported from old files.

**Approximate radius — G-band method** uses G-band brightness as a proxy for total luminosity and records the adopted temperature and extinction assumptions. It does not replace **Bolometric Radius**, which requires valid inputs and an applicable, sourced bolometric correction. Carbon-star candidate identification is not overwritten by an ordinary-star-equivalent estimate. See [comparisons and radius](SCIENTIST_COMPARISON_AND_RADIUS.md) and [temperature methods and limitations](TEMPERATURE_EXPERIMENT.md).

### Responsiveness and caching

Scientist publishes preliminary results before optional enrichment, batches catalogue requests, caches successful matches and no-match results, and supports cancellation, timeout settings and force refresh. A failed request is not cached as confirmed catalogue absence. Changing scientific settings and rerunning reuses cached inputs where possible. Loading saved files preserves their recorded calculations.

See [network behaviour and carbon-star handling](SCIENTIST_NETWORK_AND_CARBON.md). Service response times vary; earlier benchmarks are observations, not performance guarantees.

## Local browser versions

With dependencies installed, run one of:

```sh
python WebMain.py
python WebMain_temperature.py
```

Use the Python executable from your virtual environment in place of `python` when needed. Explorer defaults to port **65000** and Scientist to **65001**. Open the address printed by the server, normally `http://127.0.0.1:65000/` or `http://127.0.0.1:65001/`.

`HOST`, `PORT` and `GAIA_ASSIST_PORT` can configure the server. The current default bind address is `0.0.0.0`; set `HOST=127.0.0.1` for local-only access. These simple servers do not implement user authentication and are intended for trusted use. Stop them with Ctrl+C.

The browser interfaces support single/bulk queries and saves. Scientist also offers distance/temperature controls and saved-file loading. Desktop sky-image windows and Advanced Cluster Analysis are desktop features; browser capabilities should not be assumed identical. Web saves go to the server's result folder.

`render.yaml` retains the Explorer deployment command `python WebMain.py`. Deploying Scientist instead requires explicitly changing that command to `python WebMain_temperature.py` in the hosting configuration. The existing hosted deployment is not changed by choosing Scientist in the desktop launcher.

## Development and verification

From the project root, with dependencies and Tkinter available:

```sh
python -m unittest discover -s tests -q
```

The suite includes native Tk tests, so a graphical desktop is needed for the full run. The latest application verification passed **126 tests** on Windows/Python 3.13. Tests cover scientific selection policies, invalid/missing inputs, exact Gaia IDs, caching/cancellation, display/copy behaviour, bulk analysis and save/load compatibility. They are not a validation of every astrophysical model against observations.

Main implementation notes:

- [Scientist distance selection](SCIENTIST_DISTANCE.md)
- [Explorer comparisons and approximate radius](SCIENTIST_COMPARISON_AND_RADIUS.md)
- [Network/cache and carbon-star candidates](SCIENTIST_NETWORK_AND_CARBON.md)
- [Temperature methods and development history](TEMPERATURE_EXPERIMENT.md)

## Credits and licence

Gaia measurements are obtained from the ESA Gaia Archive. Distance, extinction and temperature methods and their primary references are documented in the linked Scientist notes. Sky cutouts use ESA services with CDS hips2fits fallback; DSS imagery is credited to STScI/NASA, with colour processing by CDS.

Gaia Assist is an independent project, not an official ESA application. Verify important results against source data and appropriate scientific literature.

Distributed under the [MIT licence](LICENSE).
