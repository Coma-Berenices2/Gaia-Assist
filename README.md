# Gaia Assist

**Gaia Assist** is a Python desktop application for retrieving and analyzing astronomical data from the **ESA Gaia archive**.

The program takes a Gaia source ID—or, experimentally, the common name of an astronomical object—and retrieves Gaia DR3 data. It then performs additional calculations involving distance, interstellar extinction, photometry, stellar temperature, luminosity, radius, peak wavelength, and stellar classification.

The application provides results through a Tkinter graphical interface, includes a browser-accessible version, and can save analyzed objects or bulk query tables as text files.

> **Status:** Experimental / research project  
> **Main file:** `Main.py`
> **Web version:** `WebMain.py`
> **Slow hosted demo:** https://gaia-assist.onrender.com

---

## Features

Gaia Assist can:

- Query **Gaia DR3** source data.
- Accept Gaia **DR1, DR2, or DR3** source IDs.
- Convert older DR1/DR2 identifiers to their corresponding DR3 source.
- Experimentally resolve an astronomical **common name** through CDS Sesame.
- Retrieve:
  - Gaia source ID
  - Object classification probability
  - Metallicity
  - Equatorial coordinates
  - Galactic coordinates
  - RA and DEC proper motion
  - Coordinate uncertainties
  - Parallax
  - Parallax signal-to-noise
  - RUWE
  - Astrometric excess noise
  - Radial velocity
  - G magnitude
  - BP-RP color
- Determine the constellation from the object's coordinates.
- Evaluate several Gaia measurement-quality indicators.
- Calculate an estimated distance from parallax.
- Query an external dust calculator for **E(B-V)**.
- Correct BP-RP for estimated reddening.
- Calculate absolute and visual magnitudes.
- Estimate effective temperature.
- Estimate luminosity and radius.
- Calculate blackbody peak wavelength using Wien's displacement law.
- Estimate a stellar spectral/evolutionary classification using the program's HR-diagram rules.
- Show field explanations and hover previews for result rows.
- Let users hide Gaia data rows or derived data rows in the main result table.
- Display warnings for potentially problematic measurements.
- Select and copy displayed values.
- Run bulk queries from pasted rows or loaded text/CSV files.
- Arrange bulk result columns by dragging compact field blocks.
- Process Gaia source-table lookups in batches of 20 for faster bulk querying.
- View bulk results in a sheet-like table with 10, 20, or 30 rows per page.
- Save single-object results and combined bulk results to timestamped text files.
- Maintain a missing-value log and debug log.

The main calculation pipeline follows the sequence of quality checks → distance → dust extinction → reddening correction → magnitudes → temperature → luminosity/radius → peak wavelength → stellar classification.

---

## Requirements

The program uses Python and the following external packages:

- `astropy`
- `astroquery`
- `requests`

It also uses Python's built-in:

- `tkinter`
- `logging`
- `threading`
- `queue`
- `re`
- `math`
- `pathlib`
- `datetime`

The external Python dependencies can be installed with:

```bash
pip install astropy astroquery requests
```

`tkinter` must also be available in your Python installation because it provides the graphical user interface.

### Recommended project structure

```text
GaiaAssist/
├── Main.py
├── WebMain.py
├── Requirement.txt
├── README.md
└── saved_objects/          # created automatically when results are saved
```

The application does not require a local Gaia database. It queries remote services when an object is analyzed.

---

## Running the program

Clone or download the repository and enter its directory.

Then run:

```bash
python Main.py
```

The program will open the **Gaia Assist** graphical interface.

The application creates its GUI with Tkinter and starts the program through `main()`, which initializes the `GaiaAssistApp` window and enters the Tkinter event loop.

### Install the required dependencies

After installing Python, open a terminal in the Gaia Assist folder and run:

```bash
pip install -r Requirement.txt
```

This will install the external Python packages required by Gaia Assist.

---

# Running the web version

Gaia Assist also includes a local browser version:

```bash
python WebMain.py
```

The server prints the exact local URL to open, for example:

```text
Gaia Assist Web is running at http://127.0.0.1:65000/
```

You may also choose a port manually:

```bash
python WebMain.py 53021
```

If the chosen port is busy, the web server attempts to fall back to an available port and prints the final URL.

A slow hosted version is available at:

```text
https://gaia-assist.onrender.com
```

The hosted version may respond slowly because it depends on remote Gaia, Sesame, and dust-map services, and because free/hosted web services can take time to wake up.

---

# Using Gaia Assist

## 1. Enter a Gaia source ID

Enter the object's Gaia source ID into the input field.

For example:

```text
5853498713190525696
```

Select the corresponding Gaia release:

- `DR3`
- `DR2`
- `DR1`

The program expects numerical source IDs for these modes.

Then click:

**Start Query**

---

## 2. Using DR2 or DR1

If you select `DR2` or `DR1`, Gaia Assist attempts to find the corresponding Gaia DR3 source.

For DR2, the program uses the Gaia DR3 `dr2_neighbourhood` crossmatch table.

For DR1, it performs a two-stage DR1 → DR2 → DR3 crossmatch.

The final analysis is performed using the corresponding **Gaia DR3** source.

---

## 3. Using a common name

The interface also contains an experimental:

```text
Common Name (Testing)
```

mode.

For example, a user can enter a recognized astronomical object name instead of a Gaia source ID.

The program first queries **CDS Sesame**. If Sesame returns a Gaia identifier, the program attempts to resolve it to Gaia DR3. If only coordinates are returned, Gaia Assist searches for the nearest Gaia DR3 source within **30 arcseconds**. 
### Important

The common-name functionality is explicitly labeled **testing** in the program and should not be considered as reliable as directly entering a Gaia source ID.

---

## 4. Hiding result groups

The main result table includes two visibility controls:

- **Hide Gaia Data** hides raw values queried directly from Gaia.
- **Hide Derived Data** hides values calculated by Gaia Assist.

These controls only affect what is displayed in the main window. They do not change the underlying query or calculation pipeline.

---

# Bulk queries

The desktop and web versions include a bulk query workflow for analyzing many objects together.

Bulk query supports:

- Pasting many object IDs or names into a large input box.
- Loading object rows from a `.txt` or `.csv` file.
- One object per row.
- A single input mode for the entire list: `DR3`, `DR2`, `DR1`, or `Common Name (Testing)`.
- Choosing which result fields to include.
- Dragging compact field blocks to control the final column order.
- Displaying results in a sheet-like table.
- Viewing 10, 20, or 30 objects per page.
- Copying table values.
- Saving all displayed bulk results into one timestamped file.

For speed, Gaia Assist processes Gaia source-table lookups in batches of 20 when possible. It also runs several per-source derived calculations in parallel. DR3 source IDs benefit the most from batching. DR2, DR1, and common-name inputs still require additional resolution steps before the final DR3 data can be queried.

Bulk queries can still take a long time because Gaia Assist may need to contact the ESA Gaia Archive, CDS Sesame, and the NADC dust calculator many times.

---

# What the program calculates

## Distance

For usable positive parallax measurements, the program calculates:

```text
distance (pc) = 1000 / parallax (mas)
```

It then converts parsecs to light-years using the conversion factor contained in the program.

### Important limitation

This is the simple inverse-parallax calculation. It should not automatically be treated as the statistically optimal distance estimate for every Gaia source, particularly when the parallax uncertainty is large.

Gaia Assist therefore evaluates `parallax_over_error` before proceeding with the rest of the calculation pipeline.

---

## Parallax quality

The program classifies `parallax_over_error` using its own thresholds:

| Parallax / Error | Classification |
|---:|---|
| ≥ 20 | Accurate |
| ≥ 10 | Acceptable |
| ≥ 5 | Moderate |
| ≥ 2 | Inaccurate |
| < 2 | Unreliable |

Negative parallax causes the downstream distance-dependent calculations to stop.

---

## Dust extinction and reddening

Gaia Assist sends the object's Galactic longitude, Galactic latitude, and calculated distance to the external **NADC dust calculator**.

It retrieves an `E(B-V)` value and uses it to calculate:

```text
Mean G-band extinction = E(B-V) × 2.74

BP-RP reddening = E(B-V) × 1.21
```

The corrected color is then:

```text
New BP-RP = Gaia BP-RP - BP-RP reddening
```

The dust query is performed remotely and can therefore fail if the external service is unavailable or its response format changes. 
---

## Absolute magnitude

The program calculates an extinction-corrected absolute magnitude using the object's G-band magnitude, distance, and estimated G-band extinction:

```text
M = G - 5 log10(d) + 5 - A_G
```

where:

- `M` = calculated absolute magnitude
- `G` = Gaia mean G magnitude
- `d` = distance in parsecs
- `A_G` = calculated G-band extinction



---

## Luminosity

The program estimates luminosity in solar units from absolute magnitude:

```text
L/L☉ = 10^[0.4 × (4.67 - M)]
```

The value `4.67` is the solar absolute magnitude used by this implementation.

---

## Effective temperature

The program estimates effective temperature primarily from the dereddened BP-RP color.

Different polynomial/empirical relations are selected depending on the color, metallicity availability, and whether the object falls into the program's red-dwarf condition.

The implementation contains separate relations for:

- Negative BP-RP values
- Red-dwarf candidates
- Objects without metallicity
- Objects with metallicity

The resulting temperature is reported in kelvin.

> **Important:** These are the relationships implemented in this project. Users should verify the scientific calibration and applicable validity ranges before using the results for research-grade work.

---

## Radius

Radius is estimated using the Stefan-Boltzmann relation.

The program first converts the calculated solar luminosity to watts and then calculates the radius from luminosity and effective temperature. The result is converted back into solar radii.

---

## Peak wavelength

The program uses Wien's displacement law:

```text
λmax = b / T
```

where `b` is the Wien displacement constant and `T` is the calculated effective temperature.

The result is displayed in nanometers.

---

## Stellar classification

Gaia Assist contains an internal set of HR-diagram rules covering spectral subclasses and luminosity classes.

The program uses:

1. Estimated effective temperature to determine a spectral subclass.
2. Visual absolute magnitude to determine possible evolutionary/luminosity classes.
3. The resulting combination to produce a classification.

Examples of possible classifications include forms such as:

```text
G2V
K5V
M3V
B1III
```

The program also has special handling for white dwarfs, subdwarfs, and Wolf-Rayet-related classifications. The classification rules are defined directly in `Main.py`.

Because these classifications are from the project's internal datas, they should be regarded as **estimates**, not authoritative Gaia catalog classifications.

---

# Measurement-quality checks

Gaia Assist includes several checks intended to help users interpret the retrieved measurements.

These include:

### Coordinate errors

RA and DEC errors are classified using thresholds ranging from `accurate` to `unreliable`.

### RUWE

RUWE is classified using the program's own thresholds, including:

- unreliable
- good
- perfect
- accurate
- questionable



### BP/RP excess flux

The program calculates a corrected BP/RP excess quantity and compares it with a calculated tolerance. The result can be classified as:

- accurate
- inaccurate
- unreliable



### Astrometric excess noise

The program also evaluates:

- Excess Noise Factor
- Excess Noise Significance

These can provide additional indications that an object's astrometric solution may require caution.

---

# Saving results

After successfully analyzing an object, click:

**Save**

Gaia Assist creates a `saved_objects` directory automatically and writes the object's results to a timestamped `.txt` file.

Example:

```text
saved_objects/
└── gaia_5853498713190525696_20260816_194500_123456.txt
```

The saved file contains:

- Save timestamp
- Input mode
- Input value
- Field names
- Values
- Units

Bulk query saves create a combined timestamped file containing all displayed result rows and the selected output columns.



---

# Logs

The program creates two useful log files next to `Main.py`.

### `gaia_assist_debug.log`

Contains diagnostic information about queries, retries, errors, and other program events.

### `gaia_missing_values_log.txt`

Records Gaia source fields that were unavailable for a queried object.

The missing-value logger records the timestamp, source ID, and fields that were missing.

If the application reports that a service failed, checking `gaia_assist_debug.log` is the first recommended troubleshooting step.

---

# External services

Gaia Assist communicates with several external astronomical services:

| Service | Purpose |
|---|---|
| **ESA Gaia Archive** | Gaia source data and Gaia crossmatching |
| **CDS Sesame** | Experimental common-name resolution |
| **NADC Dust Calculator** | E(B-V) dust/extinction values |

The program also uses `astroquery.gaia.Gaia` to submit Gaia archive queries.

Because these services are external, Gaia Assist requires an active internet connection while performing queries.

---

# Troubleshooting

## "Gaia source could not be completed"

Check:

1. Your internet connection.
2. That the Gaia source ID contains digits only.
3. That the source actually exists in the selected Gaia release.
4. `gaia_assist_debug.log` for additional information.

The program automatically retries several external requests before reporting a failure.

---

## Dust information is unavailable

If the Gaia data are successfully retrieved but the dust service cannot be reached, the program can still display the Gaia measurements.

However, calculations depending on extinction may be unavailable.

The application explicitly reports an `NADC dust data unavailable` warning when dust data were expected but could not be obtained.

---

## Some results show `-`

A `-` generally indicates that the required input data were unavailable or that a downstream calculation could not be performed.

For example, if a source has unusable parallax, the program stops the distance-dependent portion of the calculation pipeline rather than producing a distance from invalid data.

---

# Scientific limitations

Gaia Assist is intended as an **educational, exploratory, and analytical tool**.

Its output should not automatically be considered publication-quality astronomical measurements.

In particular:

- Several quantities are derived rather than directly measured by Gaia.
- Distance is calculated using inverse parallax.
- Extinction depends on an external dust-map service.
- Effective temperature is estimated from empirical relations implemented in the program.
- Luminosity and radius depend on those preceding estimates.
- Stellar classification is based on the project's internal HR-diagram rules.
- External services may change their APIs or web-page formats.
- Missing or uncertain Gaia measurements can propagate uncertainty into later calculations.

For scientific research, users should independently verify the underlying Gaia measurements, calibrations, extinction model, and classification methodology.

---

# Project structure

The current project is intentionally simple:

```text
GaiaAssist/
│
├── Main.py
├── WebMain.py
├── Requirement.txt
├── README.md
│
└── saved_objects/
    ├── gaia_<source_id>_<timestamp>.txt
    └── ...
```

`Main.py` contains the desktop GUI, Gaia queries, external-service communication, quality checks, calculations, classification rules, bulk-query logic, and result-saving logic.

`WebMain.py` provides a browser-accessible interface that reuses the calculation and query logic from `Main.py`.

---

# Contributing

Suggestions, bug reports, improvements to the calculations, and additional Gaia-related features are welcome.

---

# Disclaimer

Gaia Assist is an independent project and is not an official ESA Gaia application.

The software retrieves publicly available astronomical data from external services and performs additional calculations using formulas and classification rules implemented in this project.

Always verify important astronomical results against the original Gaia data and appropriate scientific literature.
