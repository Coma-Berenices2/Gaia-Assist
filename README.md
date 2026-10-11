# Gaia Assist

An open-source tool for exploring Gaia DR3 stellar data, comparing scientific methods, and building transparent, reproducible analysis workflows.

**[Try Online](https://gaia-assist.onrender.com)** · **[Latest Release](https://github.com/Coma-Berenices2/Gaia-Assist/releases)**

<!-- The release link opens the repository's Releases page. Replace it with the exact public-beta release URL when available. -->

## Screenshot

> **Screenshot coming soon:** add a Scientist results screenshot showing a Gaia source ID, catalogue measurements, distance and temperature estimates, and quality/provenance notes.

<!-- Replace the placeholder above with a real screenshot, for example:
![Gaia Assist Scientist results, including measurements, estimates and quality notes](docs/images/scientist-results.png)
-->

**Status: Public Beta** — Gaia Assist is actively being developed and scientifically validated. Review sources, assumptions and quality warnings before using derived parameters for scientific work.

## Quick Start

1. **[Open Gaia Assist online](https://gaia-assist.onrender.com)** and choose **Scientist** to inspect methods and quality notes, or **Explorer** for a simpler view.
2. Select **DR3** and enter a numeric Gaia DR3 source ID.
3. Click **Start Query** and wait for the results; optional information may finish loading afterward.
4. Compare the Gaia measurements with the derived stellar parameters. Review their sources, uncertainties where available, quality flags and **Calculation details** in Scientist mode.
5. Use **Save** to retain the result; see [Save and reopen your work](#save-and-reopen-your-work) for formats and reopening guidance.

The online application offers a browser workflow. For local use, sky-image windows and advanced cluster charts, follow the [desktop setup](#installation-and-desktop-setup). See [Browser interface](#optional-use-a-browser-interface) for local hosting and feature differences.

## Explore

Look up individual stars and inspect Gaia measurements, photometry, coordinates and quality indicators. Start with **Explorer** for a simpler view, then switch to **Scientist** to inspect sources, assumptions and comparison results. Both modes include calculated estimates.

## Analyze

Compare temperature and distance estimates in **Scientist**, inspect calculation provenance, and review the assumptions behind derived magnitudes and radii. Use [Bulk Query](#query-several-objects) to analyze several objects, export results, and explore selected populations with desktop colour–magnitude diagrams and classification charts.

## Research

Use saved records, structured exports and method documentation to support transparent analysis workflows. A **reproducible NGC 2546 case study is in development**, with planned documentation of queries, candidate selection and diagnostic figures. It is not yet a completed or validated research result.

Ongoing research work includes scientific validation, cluster membership analysis, extinction-corrected colour–magnitude diagrams and isochrone analysis. These are development goals; the current charts alone do not establish cluster membership.

## Scientific limitations

- **Derived parameters require independent validation before publication-quality use.** Some methods remain under scientific review; inspect the source data, method references and recorded assumptions.
- A suggested stellar classification is an estimate, not a measured spectral type. Population charts and quality flags do not confirm cluster membership; an unflagged object is not automatically a member.
- Temperature and radius estimates depend on available measurements, supported method ranges and extinction assumptions. The approximate G-band radius assumes a solar-like bolometric correction; read the [Scientist results](#understand-scientist-results) guidance before interpreting it.
- Missing or unavailable values are not zero. When extinction is unavailable, Scientist labels the G magnitude **Not de-dusted** rather than treating extinction as zero.
- **Common Name (Testing)** lookup is experimental. Verify the matched source and coordinates. Carbon-star candidate flags also require review and do not confirm a carbon-star identification.

Gaia Assist is an independent project using Gaia and other astronomical services, not an official ESA application.

## Detailed documentation

- [Installation and desktop setup](#installation-and-desktop-setup)
- [Look up your first object](#look-up-your-first-object)
- [Understand Scientist results](#understand-scientist-results)
- [Bulk queries and cluster charts](#query-several-objects)
- [Save and reopen your work](#save-and-reopen-your-work)
- [Browser interface](#optional-use-a-browser-interface)
- [Troubleshooting](#troubleshooting)
- [Methods and references](#learn-more-about-the-methods)
- [License](#license)

## Installation and desktop setup

### 1. Download the application

On this repository's GitHub page, choose **Code → Download ZIP**, then extract the ZIP. Keep the extracted files together. Downloading only `Main.py` will not work: it uses the other Python files in the folder.

You need **Python 3.10 or newer**, internet access for catalogue queries, and a writable application folder. The application has been tested on Windows with Python 3.13; macOS and Linux have not been fully verified. No Gaia API key or GitHub account is required.

### 2. Install and launch on Windows

Install Python with its **Tcl/Tk** component enabled. Open PowerShell or Terminal in the extracted folder containing `Main.py` and `requirements.txt`, then run these commands one at a time:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe Main.py
```

The first two commands prepare the application. **For later visits, run only the last command** from the same folder.

If Windows does not recognize `py`, try `python` in the first command. The environment does not need to be activated.

<details>
<summary>macOS and Linux setup</summary>

With Python and Tkinter installed, open a terminal in the extracted application folder:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python Main.py
```

For later visits, run only the last command. Some Linux distributions provide Tkinter as a separate system package; install the package matching your Python version if the application reports that `tkinter` is missing.

</details>

### 3. Choose a mode

| Mode | Use it when you want… |
| --- | --- |
| **Explorer** | A simpler interface with the original approximate temperature, radius and classification calculations. |
| **Scientist** | More detailed temperature and distance selection, comparison results, recorded assumptions and scientific review notes. |

Scientist is the focus of ongoing scientific improvements. More detail does not make every estimate reliable for every kind of star; read the accompanying warnings.

## Look up your first object

1. Select the input catalogue, normally **DR3**.
2. Enter the object's numeric Gaia source ID. For DR1 or DR2 IDs, choose the matching release; the application searches for its DR3 counterpart.
3. Click **Start Query** and wait for the results. In Scientist mode, initial results can appear before optional information finishes loading.
4. Review the measurements and quality indicators, then the calculated properties.
5. Click **Save** if you want to keep the result.

To search by an astronomical name, choose **Common Name (Testing)**. Name lookup is experimental: check the matched source and coordinates before using the result.

Use **Switch to Scientist** or **Switch to Explorer** during your session. Each mode retains its own inputs and results while you switch; switching does not automatically run another query.

### Read, explain and copy results

- **Explain** is the default. Click a field name to read its definition.
- Switch to **Copy** to select field names, values and units together.
- In Scientist mode, long values may end in `...`. In Explain mode, click to read the full value; in Copy mode, hover over it to see the full text. Full text is retained when copying and saving.
- Use **Calculation details** in Scientist mode to inspect supporting information and review notes.

### View the surrounding sky

In the desktop application, click **Show Sky Image** to open a separate image window. It shows a **5.0′ × 5.0′ DSS2 colour, Optical** cutout centred on the object's coordinates. Image retrieval follows the numerical results so it does not hold up their initial display. The image window opens only when requested.

## Understand Scientist results

Read a value together with its source and review notes. Missing or unavailable values are not zero.

| Result | How to interpret it |
| --- | --- |
| Gaia measurements | Catalogue values such as parallax, photometry and radial velocity, with errors and quality indicators where available. |
| Adopted temperature | The temperature selected from the available, applicable estimates. Check the recorded source and warnings. |
| Explorer comparison results | Approximate temperature, radius and classification calculated using the original Explorer methods, for comparison with Scientist results. |
| Adopted distance | The distance selected by the current distance policy. Baseline and Bayesian estimates remain separately identifiable. |
| **Approximate radius — G-band method** | Uses G-band brightness as a proxy for total luminosity. Assumes a solar-like bolometric correction; accuracy depends on the stellar spectrum. |
| Bolometric radius | A separate calculation requiring an applicable bolometric correction and valid inputs. It can be unavailable even when the approximate radius is shown. |

When neither Gaia nor the NADC dust map supplies usable G-band extinction, Scientist uses observed **Mean G** directly. **G magnitude correction status** labels it **Not de-dusted**; extinction remains unknown rather than being recorded as zero. Absolute magnitude still requires a valid adopted distance.

Temperature and radius estimates depend on the available measurements and extinction assumptions. Review those assumptions before comparing stars. Carbon-star candidate warnings need particular care: an ordinary-star comparison classification does not replace the carbon-star identification, and a candidate flag is not confirmation.

### Choose a distance policy

Open **Distance Settings** in Scientist mode:

- **Automatic** is the default. It uses a valid inverse-parallax estimate when fractional parallax uncertainty meets the configured threshold, otherwise preferring a usable published Bayesian geometric distance. The default threshold is 10%.
- **Baseline** uses the inverse-parallax calculation when it passes the application's validity checks.
- **Bayesian geometric** prefers the published geometric distance, with an explicit fallback when needed.

The selected distance affects derived magnitudes, extinction calculations and radius estimates. The threshold is an application setting, not a universal guarantee of accuracy. Selection notes explain which distance was actually used.

Scientist reuses cached catalogue responses where possible. Use force refresh when you need a new service response; changing settings does not always require downloading the same data again. Loading a saved record preserves its recorded calculations.

## Query several objects

1. Open **Bulk Query**.
2. Enter **one object per row**, or use **Load Text File** to load `.txt` or `.csv` input containing one object per row.
3. Choose the input catalogue and result columns.
4. Start the bulk query, review the results, then use **Save Bulk Results** to keep them.

In Scientist's desktop field selector, **View in Categories** groups fields by subject (distance, brightness, colour/temperature, extinction, radius, quality, coordinates and more). Drag a section heading to move that whole group, or drag fields within a section to change their order. Switch back to the default layout to see the same selection and order as a flat grid. Scroll to reach all fields and hover over a box to read its full name. **Select All** deselects everything when all fields are already selected; otherwise it selects everything.

A **blue asterisk** after an object's ID flags potentially problematic measurements: unreliable RUWE, missing or negative parallax, unreliable parallax-over-error, or unreliable corrected excess flux, where those fields are available. Click the asterisk to read the warning. For cluster analysis, consider whether to exclude the flagged object; an unflagged object is not automatically a cluster member.

### Make cluster charts

After a completed desktop bulk query with at least **10 objects**, open **Advanced Cluster Analysis**. Choose whether to include or exclude flagged objects, then generate:

- **Colour–magnitude diagram (CMD):** New BP−RP runs left to right from −1 to 4; absolute magnitude runs from −10 at the top to 15 at the bottom. Objects outside these ranges, or without the necessary values, are omitted.
- **Spectral classification grid:** spectral subtypes run across the columns and luminosity classes down the rows. Each cell shows an object count. When an object has several estimated types, only the first listed type is counted. Scientist treats carbon-star candidates separately from the ordinary classification grid.

Save figures as **PNG, PDF or SVG**, and chart data as **CSV**. These charts help explore the selected objects; they do not determine cluster membership by themselves.

## Save and reopen your work

Explorer saves results in `saved_objects/`. Scientist saves results in `saved_objects_temperature/`, with text and structured export formats. The application creates these folders as needed.

In Scientist mode, use **Load Saved Results** to reopen a saved JSON or supported older text record. **Prefer JSON for reopening:** it retains the full record, including sources, assumptions and settings. CSV is useful for tables and further analysis; text is convenient for reading.

Older imported records retain their historical values. Loading them does not automatically recalculate them with the current model. Keep a backup of your saved-results folders before replacing or updating the application.

## Optional: use a browser interface

Use the desktop application for sky-image windows and advanced cluster charts. To use a local browser interface on Windows, run the following from the application folder after installation.

```powershell
$env:HOST = '127.0.0.1'
.\.venv\Scripts\python.exe WebMain.py
```

Open `http://127.0.0.1:65000/`, choose **Explorer** or **Scientist**, and use the switch button at the top to change modes. Both run on the same server. Each workspace retains its inputs and results while switching; refreshing or closing the browser page ends that unsaved session.

`WebMain_temperature.py` also opens the combined interface, on port 65001 by default. Render uses `WebMain.py` and its assigned port. If a different port is configured, use the address printed in the terminal.

Keep the terminal open while using the interface; press **Ctrl+C** there to stop it. Browser saves are written to the computer running the application. Browser and desktop features are not identical. The local command above restricts access to your own computer.

## Troubleshooting

| Problem | What to try |
| --- | --- |
| `Main.py` or `requirements.txt` cannot be found | Open the terminal in the extracted folder containing those files. |
| A Python module is missing | Repeat the installation command above, then launch with the same `.venv` Python executable. Keep all downloaded Python files together. |
| `tkinter` is missing | Install Python's Tcl/Tk component or the matching Tkinter system package. It is not installed through `requirements.txt`. |
| The window closes immediately | Launch from a terminal using the command above so you can read the error. |
| A query fails or takes too long | Check your connection, input ID and selected release. Catalogue services can be temporarily unavailable; retry later. Scientist also provides cancellation and network timeout settings. |
| Temperature, distance or radius is unavailable | Read the source/status and review notes. The required data may be missing, invalid or outside a method's supported range. |
| A sky image does not load | The image service may be unavailable even when Gaia results succeed. Retry the image later. |
| A star is missing from a chart | Check its required values, plot range, estimated classification and the include/exclude setting for flagged objects. |
| Results cannot be saved | Move the application to a writable folder and check the save error. |

## Learn more about the methods

For calculation details, assumptions and references:

- [Temperature methods and limitations](TEMPERATURE_EXPERIMENT.md)
- [Distance selection](SCIENTIST_DISTANCE.md)
- [Explorer comparisons and approximate radius](SCIENTIST_COMPARISON_AND_RADIUS.md)
- [Catalogue requests, caching and carbon-star handling](SCIENTIST_NETWORK_AND_CARBON.md)

## License

Distributed under the [MIT license](LICENSE).
