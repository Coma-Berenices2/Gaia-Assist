import logging
import scientist_network as network
import queue
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import copy_context
from datetime import datetime
from math import cos, isfinite, log10, pi, radians, sqrt
from pathlib import Path
#below requires pip installations
import astropy.units as u
import requests
from astropy.coordinates import SkyCoord
from temperature_model import VERSION, TemperatureOptions, bounds, evaluate_temperatures, number
from temperature_reference import magnitude_error
from scientist_distance import DISPLAY_ORDER as DISTANCE_DISPLAY_ORDER, evaluate_distance, baseline_diagnostics
from temperature_schema import (
    AP_FIELDS, PHOTOMETRY_FIELDS, GAIA_FIELDS, DERIVED_FIELDS,
    UNITS as TEMPERATURE_UNITS, EXPLANATIONS as TEMPERATURE_EXPLANATIONS,
    TEMPERATURE_DISPLAY_ORDER, TEMPERATURE_DETAIL_FIELDS, format_display_value, empty_historical, compact_text, format_export_value,
)
#above

tk = None
filedialog = None
messagebox = None
ttk = None


def load_desktop_gui():
    global tk, filedialog, messagebox, ttk
    if tk is not None:
        return

    import tkinter as tk_module
    from tkinter import filedialog as filedialog_module
    from tkinter import messagebox as messagebox_module
    from tkinter import ttk as ttk_module

    tk = tk_module
    filedialog = filedialog_module
    messagebox = messagebox_module
    ttk = ttk_module


GAIA_COLUMNS = {
    "source_id": "Source ID",
    "object_type": "Object Type",
    "metallicity": "Metallicity (M/H)",
    "ra": "Equatorial Coordinate RA",
    "dec": "Equatorial Coordinate DEC",
    "l": "Galactic Coordinate l",
    "b": "Galactic Coordinate b",
    "pmra": "RA Proper Motion",
    "pmdec": "DEC Proper Motion",
    "ra_error": "RA Error",
    "dec_error": "DEC Error",
    "parallax": "Parallax",
    "parallax_over_error": "Parallax Over Error",
    "astrometric_excess_noise": "Excess Noise",
    "astrometric_excess_noise_sig": "Excess Noise Sig",
    "ruwe": "RUWE",
    "phot_bp_rp_excess_factor": "BP+RP Excess Flux",
    "radial_velocity": "Radial Velocity",
    "radial_velocity_error": "Radial Velocity Error",
    "phot_g_mean_mag": "Mean G",
    "bp_rp": "Mean BP-RP",
}

DERIVED_COLUMNS = {
    "ra_hms_dec": "Hour, Minutes, Seconds, DEC",
    "constellation": "Constellation",
    "ra_correctness": "RA Correctness",
    "dec_correctness": "DEC Correctness",
    "parallax_data_status": "Parallax Data Status",
    "parallax_correctness": "Parallax Correctness",
    "ruwe_correctness": "RUWE Correctness",
    "bp_rp_excess_correctness": "BP+RP Excess Flux Correctness",
    "distance_parsecs": "Distance in Parsecs",
    "distance_lightyears": "Distance in Lightyears",
    "ebv": "E(B-V)",
    "mean_g_band_extinction": "Mean G Band Extinction",
    "bp_rp_reddening": "BP-RP Reddening Factor",
    "new_bp_rp": "New BP-RP",
    "corrected_excess_flux": "Corrected Excess Flux C*",
    "effective_temperature": "Effective Temperature",
    "absolute_magnitude": "Absolute Magnitude",
    "luminosity": "Luminosity (Solar Units)",
    "radius": "Radius",
    "peak_wavelength": "Peak Wavelength",
    "visual_absolute_magnitude": "Visual Absolute Magnitude",
    "visual_apparent_magnitude": "Visual Apparent Magnitude",
    "excess_noise_factor": "Excess Noise Factor",
    "excess_noise_significance": "Excess Noise Significance",
    "star_type": "Star Type",
}

GAIA_COLUMNS.update(GAIA_FIELDS)
DERIVED_COLUMNS.update(DERIVED_FIELDS)
DERIVED_COLUMNS.update(effective_temperature="Adopted Temperature", luminosity="G-band Solar Brightness Ratio", radius="Bolometric Radius", visual_absolute_magnitude="Estimated Visual Absolute Magnitude", visual_apparent_magnitude="Estimated Visual Apparent Magnitude", star_type="Estimated Star Type")
ALL_DISPLAY_COLUMNS = {**GAIA_COLUMNS, **DERIVED_COLUMNS}

PRIMARY_DISPLAY_ORDER = (
    "source_id", "object_type", *TEMPERATURE_DISPLAY_ORDER,
    *DISTANCE_DISPLAY_ORDER, "distance_parsecs", "distance_lightyears", "parallax", "parallax_error", "parallax_over_error",
    "parallax_correctness", "parallax_data_status",
    "phot_g_mean_mag", "phot_bp_mean_mag", "phot_rp_mean_mag", "bp_rp", "new_bp_rp",
    "absolute_magnitude", "visual_absolute_magnitude", "visual_apparent_magnitude", "luminosity", "peak_wavelength",
    "mean_g_band_extinction", "bp_rp_reddening", "ebv", "extinction_source", "extinction_status",
    "ruwe", "ruwe_correctness", "phot_bp_rp_excess_factor", "corrected_excess_flux", "bp_rp_excess_correctness", "photometry_status",
    "ra_hms_dec", "constellation", "ra", "ra_error", "ra_correctness", "dec", "dec_error", "dec_correctness", "l", "b",
    "pmra", "pmdec", "radial_velocity", "radial_velocity_error",
    "astrometric_excess_noise", "astrometric_excess_noise_sig", "excess_noise_factor", "excess_noise_significance",
    "carbon_star_badge", "carbon_star_status", "ordinary_star_equivalent", "carbon_review_reason",
    "carbon_identification_source", "carbon_reference",
)
DISPLAY_COLUMNS = {
    column_name: ALL_DISPLAY_COLUMNS[column_name]
    for column_name in PRIMARY_DISPLAY_ORDER
}
DISPLAY_COLUMNS.update(
    {
        column_name: label
        for column_name, label in ALL_DISPLAY_COLUMNS.items()
        if column_name not in PRIMARY_DISPLAY_ORDER
    }
)

SECONDARY_DISPLAY_COLUMNS = tuple(
    column_name
    for column_name in DISPLAY_COLUMNS
    if column_name not in PRIMARY_DISPLAY_ORDER
)

MISSING_VALUES_LOG = Path(__file__).with_name("temperature_missing_values_log.txt")
DEBUG_LOG = Path(__file__).with_name("temperature_debug.log")
SAVED_OBJECTS_DIR = Path(__file__).with_name("saved_objects_temperature")
DUST_CALCULATOR_URL = "https://nadc.china-vo.org/data/dustmaps/calculator"
ESASKY_IMAGE_URL = "https://sky.esa.int/esasky-tap/skyimage"
ESASKY_DSS2_HIPS_URL = "https://skies.esac.esa.int/DSSColor"
CDS_HIPS2FITS_URL = "https://alasky.cds.unistra.fr/hips-image-services/hips2fits"
SKY_IMAGE_FOV_ARCMIN = 5.0
SKY_IMAGE_SIZE = 600
COMMON_NAME_RELEASE = "Common Name (Testing)"
BULK_GAIA_BATCH_SIZE = 20
BULK_CALCULATION_WORKERS = 3
SESAME_URLS = (
    "https://cds.unistra.fr/cgi-bin/nph-sesame/-oxpI/SNV?{name}",
    "https://cdsweb.u-strasbg.fr/cgi-bin/nph-sesame/-oxpI/SNV?{name}",
)
STEFAN_BOLTZMANN_CONSTANT = 5.670374419e-8
SOLAR_LUMINOSITY_WATTS = 3.828e26
SOLAR_RADIUS_METERS = 6.957e8
WIEN_DISPLACEMENT_CONSTANT = 2.897771955e-3

LOGGER = logging.getLogger("gaia_assist_temperature")
if not LOGGER.handlers:
    LOGGER.setLevel(logging.INFO)
    debug_handler = logging.FileHandler(DEBUG_LOG, encoding="utf-8")
    debug_handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    )
    LOGGER.addHandler(debug_handler)


class QueryServiceError(RuntimeError):
    def __init__(self, service, message):
        self.service = service
        super().__init__(message)


def run_with_retries(operation, service, attempts=3):
    with network.timed(service):
        try:
            return operation()
        except (network.QueryCancelled, network.QueryTimeout):
            raise
        except Exception as error:
            raise QueryServiceError(service, str(error)) from error


def sky_image_coordinates(ra, dec):
    """Return finite ICRS coordinates in degrees, or reject missing/bad values."""
    try:
        ra, dec = float(ra), float(dec)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("Valid RA and DEC are required for a sky image.") from error
    if not (isfinite(ra) and isfinite(dec) and 0 <= ra < 360 and -90 <= dec <= 90):
        raise ValueError("Valid RA and DEC are required for a sky image.")
    return ra, dec


def fetch_esasky_image(ra, dec):
    """Fetch ESA's DSS2 color map, with CDS rendering if ESA cutouts are down."""
    ra, dec = sky_image_coordinates(ra, dec)
    # API: https://sky.esa.int/esasky/hipsCutout/help.html
    # FOV is in degrees; aspectratio must be explicit (the default is 16:9).
    try:
        return _fetch_sky_image_png(
            ESASKY_IMAGE_URL,
            {
                "target": f"{ra} {dec}",
                "fov": SKY_IMAGE_FOV_ARCMIN / 60,
                "aspectratio": 1,
                "hips": "DSS2 color",
                "size": SKY_IMAGE_SIZE,
                "fmt": "PNG",
                "proj": "ALADIN_ORTOGRAPHIC",
                "timeout": 30000,
            },
        )
    except (requests.RequestException, ValueError) as error:
        LOGGER.warning("ESA sky cutout unavailable; trying CDS rendering: %s", error)

    # CDS can render the same ESA-hosted color survey when the native service fails.
    # API: https://alasky.cds.unistra.fr/hips-image-services/hips2fits
    return _fetch_sky_image_png(
        CDS_HIPS2FITS_URL,
        {
            "hips": ESASKY_DSS2_HIPS_URL,
            "ra": ra,
            "dec": dec,
            "fov": SKY_IMAGE_FOV_ARCMIN / 60,
            "width": SKY_IMAGE_SIZE,
            "height": SKY_IMAGE_SIZE,
            "projection": "TAN",
            "coordsys": "icrs",
            "format": "png",
        },
    )


def _fetch_sky_image_png(url, params):
    with requests.get(url, params=params, timeout=(10, 45)) as response:
        response.raise_for_status()
        image_data = response.content
    if not image_data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("The sky image service did not return a PNG image. Please retry.")
    return image_data


FIELD_EXPLANATIONS = {
    "source_id": "Gaia's unique numeric identifier for this source in the selected data release, displayed again after lookup so cross-matches and name resolutions can be checked.",
    "object_type": "The most probable Gaia DSC class among star, galaxy, and quasar, reported from Gaia class probabilities. Low probabilities can occur for unusual, blended, binary, or poorly modeled sources.",
    "metallicity": "Gaia's M/H estimate, the logarithmic abundance of elements heavier than helium relative to the Sun. Missing values are common and are handled by fallback temperature formulas.",
    "ra": "Right ascension is the east-west equatorial sky coordinate of the source, measured in degrees on the ICRS celestial reference frame.",
    "dec": "Declination is the north-south equatorial sky coordinate of the source, measured in degrees relative to the celestial equator on the ICRS frame.",
    "l": "Galactic longitude is the source's angular position around the Milky Way plane, measured in degrees from the Galactic center direction.",
    "b": "Galactic latitude is the source's angular height above or below the Milky Way plane, measured in degrees.",
    "pmra": "Proper motion in right ascension is Gaia's measured angular motion of the source across the sky along the RA direction, including the cos(dec) factor, reported in milliarcseconds per year.",
    "pmdec": "Proper motion in declination is Gaia's measured angular motion of the source across the sky along the declination direction, reported in milliarcseconds per year.",
    "ra_error": "The standard uncertainty of Gaia's right ascension measurement, in milliarcseconds. Smaller values indicate a more precise astrometric position.",
    "dec_error": "The standard uncertainty of Gaia's declination measurement, in milliarcseconds. Smaller values indicate a more precise astrometric position.",
    "parallax": "Annual parallax is the apparent shift caused by Earth's orbit around the Sun, measured in milliarcseconds. Positive, reliable parallaxes can be converted into distance.",
    "parallax_over_error": "The parallax signal-to-noise ratio: parallax divided by its formal uncertainty. Higher values generally mean a more reliable distance estimate.",
    "astrometric_excess_noise": "Extra scatter Gaia needed to add to fit the source's astrometric solution. Elevated values can indicate unresolved companions, blending, variability, or modeling problems.",
    "astrometric_excess_noise_sig": "The statistical significance of the astrometric excess noise. High significance means the excess noise is unlikely to be a random fluctuation.",
    "ruwe": "Renormalised Unit Weight Error measures how well Gaia's single-source astrometric model fits the observations. Values near 1 are usually best.",
    "phot_bp_rp_excess_factor": "Gaia's raw BP/RP flux excess factor compares the summed blue and red photometer flux to the G-band flux. It is sensitive to crowding, color, and calibration effects.",
    "radial_velocity": "The line-of-sight velocity of the source, in kilometers per second. Positive values usually indicate motion away from the Solar System barycenter.",
    "radial_velocity_error": "The formal uncertainty of Gaia's radial-velocity measurement, in kilometers per second. Smaller values indicate a more precise line-of-sight velocity.",
    "phot_g_mean_mag": "The mean apparent magnitude in Gaia's broad G band. Lower magnitude means the object appears brighter from Earth.",
    "bp_rp": "The Gaia BP-RP color index, equal to blue magnitude minus red magnitude. Larger values usually indicate cooler or more reddened objects.",
    "ra_hms_dec": "The equatorial position formatted as RA in hours, minutes, and seconds, with declination in degrees for easier sky-location reading.",
    "constellation": "The official IAU constellation containing the source's equatorial position.",
    "ra_correctness": "A qualitative precision grade based on Gaia's RA uncertainty. It describes positional reliability, not whether the astrophysical object is normal.",
    "dec_correctness": "A qualitative precision grade based on Gaia's declination uncertainty. It describes positional reliability, not whether the astrophysical object is normal.",
    "parallax_data_status": "A guard row that flags negative parallaxes as insufficient or unreliable for distance-based calculations.",
    "parallax_correctness": "A qualitative reliability grade based on parallax_over_error. Higher signal-to-noise produces a stronger distance confidence grade.",
    "ruwe_correctness": "A qualitative astrometric-fit grade based on RUWE. Poor values can indicate blending, binarity, extended structure, or a bad single-star fit.",
    "bp_rp_excess_correctness": "A photometric quality grade based on corrected BP/RP excess flux C* compared with its color-dependent sigma tolerance.",
    "distance_parsecs": "Distance estimated from parallax as 1000 divided by parallax in milliarcseconds. This simple inversion is most reliable for high parallax signal-to-noise.",
    "distance_lightyears": "The parallax-based distance converted from parsecs to light-years using 1 pc = 3.26156 ly.",
    "ebv": "Color excess E(B-V), an estimate of interstellar reddening caused by dust along the line of sight.",
    "mean_g_band_extinction": "Estimated Gaia G-band extinction derived from E(B-V). It approximates how much dust dims the source in the G band.",
    "bp_rp_reddening": "Estimated reddening correction for Gaia BP-RP color derived from E(B-V). It is subtracted from the observed BP-RP color.",
    "new_bp_rp": "The dereddened Gaia BP-RP color after subtracting the BP-RP reddening factor. Later color-dependent calculations use this corrected value.",
    "corrected_excess_flux": "The corrected BP/RP excess flux C*, computed by subtracting the expected color-dependent excess from Gaia's raw BP/RP excess factor.",
    "effective_temperature": "The estimated stellar effective temperature: the blackbody temperature that would radiate the same total energy per surface area as the source.",
    "absolute_magnitude": "The estimated Gaia G-band absolute magnitude: how bright the object would appear at 10 parsecs after applying the G-band extinction correction.",
    "luminosity": "The luminosity relative to the Sun, estimated from absolute G-band magnitude using the adopted solar reference magnitude.",
    "radius": "The stellar radius in solar radii, derived from luminosity and effective temperature using the Stefan-Boltzmann law.",
    "peak_wavelength": "The blackbody peak wavelength from Wien's displacement law. Hotter sources peak at shorter, bluer wavelengths.",
    "visual_absolute_magnitude": "The estimated Johnson V absolute magnitude, converted from Gaia G absolute magnitude using the corrected BP-RP color polynomial.",
    "visual_apparent_magnitude": "The estimated Johnson V apparent magnitude, converted from extinction-corrected Gaia G apparent magnitude using the corrected BP-RP color polynomial.",
    "excess_noise_factor": "A qualitative grade based on astrometric excess noise. Non-accurate values may indicate physical wobble, blending, or an imperfect astrometric model.",
    "excess_noise_significance": "A qualitative grade based on the statistical significance of astrometric excess noise.",
    "star_type": "The estimated stellar classification. The code first locates the spectral type from effective temperature, then uses Johnson V absolute magnitude to infer luminosity class.",
}

HELP_TUTORIAL = """Using Gaia Assist

1. Enter a Gaia source ID
Enter the object's Gaia source ID into the input field.

For example:

5853498713190525696

Select the corresponding Gaia release:

DR3
DR2
DR1

The program expects numerical source IDs for these modes.

Then click:

Start Query

2. Using DR2 or DR1
If you select DR2 or DR1, Gaia Assist attempts to find the corresponding Gaia DR3 source.

For DR2, the program uses the Gaia DR3 dr2_neighbourhood crossmatch table.

For DR1, it performs a two-stage DR1 -> DR2 -> DR3 crossmatch.

The final analysis is performed using the corresponding Gaia DR3 source.

3. Using a common name
The interface also contains an experimental:

Common Name (Testing)

mode.

For example, a user can enter a recognized astronomical object name instead of a Gaia source ID.

The program first queries CDS Sesame. If Sesame returns a Gaia identifier, the program attempts to resolve it to Gaia DR3. If only coordinates are returned, Gaia Assist searches for the nearest Gaia DR3 source within 30 arcseconds.

Important
The common-name functionality is explicitly labeled testing in the program and should not be considered as reliable as directly entering a Gaia source ID."""

BULK_QUERY_GUIDE = """Using Bulk Query

1. Enter one object per row
Paste or type source IDs or common names into the large input box. Each line should contain exactly one object.

2. Choose one input type
All rows must use the same mode:

DR3
DR2
DR1
Common Name (Testing)

DR3, DR2, and DR1 require numeric Gaia source IDs. Common Name (Testing) accepts recognized astronomical names and uses CDS Sesame before matching to Gaia DR3.

3. Load a file instead
Use Load Text File to choose a .txt or .csv file. The file contents are pasted into the input box, still with one object per row.

4. Select output columns
After pressing Continue, choose the rows/data fields you want included in the final table. Drag compact field blocks to arrange the display order from top-left to bottom-right.

5. Wait for the query
Bulk queries can take a long time because Gaia, Sesame, and dust-map services may each be contacted many times. Gaia source-table lookups are processed in batches of 20, and several per-source calculations can run in parallel. The progress bar and status text show which batch or object is currently running.

6. View results
Results are shown as a sheet-like table with 10 objects per page. Use Previous Page and Next Page to move through the result pages."""

FIELD_UNITS = {
    "source_id": "unitless",
    "object_type": "% probability",
    "metallicity": "dex",
    "ra": "deg",
    "dec": "deg",
    "l": "deg",
    "b": "deg",
    "pmra": "mas/yr",
    "pmdec": "mas/yr",
    "ra_error": "mas",
    "dec_error": "mas",
    "parallax": "mas",
    "parallax_over_error": "unitless",
    "astrometric_excess_noise": "mas",
    "astrometric_excess_noise_sig": "unitless",
    "ruwe": "unitless",
    "phot_bp_rp_excess_factor": "unitless",
    "radial_velocity": "km/s",
    "radial_velocity_error": "km/s",
    "phot_g_mean_mag": "mag",
    "bp_rp": "mag",
    "ra_hms_dec": "h m s / deg",
    "constellation": "unitless",
    "ra_correctness": "unitless",
    "dec_correctness": "unitless",
    "parallax_data_status": "unitless",
    "parallax_correctness": "unitless",
    "ruwe_correctness": "unitless",
    "bp_rp_excess_correctness": "unitless",
    "distance_parsecs": "pc",
    "distance_lightyears": "ly",
    "ebv": "mag",
    "mean_g_band_extinction": "mag",
    "bp_rp_reddening": "mag",
    "new_bp_rp": "mag",
    "corrected_excess_flux": "unitless",
    "effective_temperature": "K",
    "absolute_magnitude": "mag",
    "luminosity": "L_sun",
    "radius": "R_sun",
    "peak_wavelength": "nm",
    "visual_absolute_magnitude": "mag",
    "visual_apparent_magnitude": "mag",
    "excess_noise_factor": "unitless",
    "excess_noise_significance": "unitless",
    "star_type": "unitless",
}


FIELD_UNITS.update(TEMPERATURE_UNITS)
FIELD_EXPLANATIONS.update(TEMPERATURE_EXPLANATIONS)
HELP_TUTORIAL = (
    "TEMPERATURE EXPERIMENT\n\n"
    "Both Gaia GSP-Phot and BP-RP temperatures remain visible. Adopted Temperature drives "
    "the estimated classification; read its source, reason and review status.\n\n"
    "Temperature Settings apply to subsequent single and bulk queries. Rerun a source "
    "after changing settings. Solar composition is assumed unless you explicitly provide "
    "trusted Fe/H or choose the uncalibrated Gaia override. Missing reddening is not zero.\n\n"
    "Save writes a text table and a matching JSON file containing full data, assumptions "
    "and flags in saved_objects_temperature. Keep the JSON for complete round trips. "
    "Load Saved Results reads new JSON or old text files without recalculating or changing originals. "
    "Old temperatures and radii are labelled legacy rather than silently adopted.\n\n"
    "Cluster charts count estimated, tentative, approximate and unclassified objects separately. "
    "These classifications and photometric screens do not establish cluster membership. "
    "Bolometric radius is unavailable without a suitable bolometric correction.\n\n"
    + HELP_TUTORIAL
)


class GaiaAssistApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Gaia Assist — Scientist")
        self.temperature_options = TemperatureOptions()
        self.current_record = None
        self.root.geometry("1050x720")
        self.root.minsize(900, 520)

        self.gaia_code = tk.StringVar()
        self.gaia_release = tk.StringVar(value="DR3")
        self.hide_gaia_data = tk.BooleanVar(value=False)
        self.hide_derived_data = tk.BooleanVar(value=False)
        self.show_temperature_details = tk.BooleanVar(value=False)
        self.field_name_mode = tk.StringVar(value="Explain")
        self.status = tk.StringVar(value="Enter a Gaia source_id to begin.")
        self.result_vars = {
            column_name: tk.StringVar(value="-") for column_name in DISPLAY_COLUMNS
        }
        self.result_value_widgets = {}
        self.unit_widgets = {}
        self.field_label_widgets = {}
        self.row_widgets = {}
        style = ttk.Style(self.root)
        self.result_background = style.lookup("TFrame", "background") or self.root.cget("background")
        self.result_foreground = style.lookup("TLabel", "foreground") or "black"
        self.query_in_progress = False
        self.query_generation = 0
        self.query_cancel = threading.Event()
        self.force_refresh = tk.BooleanVar(value=False)
        self.query_events = queue.Queue()
        self.sky_image_request_id = 0
        self.sky_image_coordinates = None
        self.sky_image_source_id = None
        self.sky_image_data = None
        self.sky_image_error = None
        self.sky_image_loading = False
        self.sky_image_window = None
        self.sky_image_photo = None
        self.sky_image_status = tk.StringVar(value="Sky image available after results.")
        self.last_saved_object_key = None
        self.field_preview_window = None
        self.normal_value_font = ("Segoe UI", 10)
        self.underline_value_font = ("Segoe UI", 10, "underline")

        self._build_interface()
        self.root.protocol("WM_DELETE_WINDOW", self.close_app)
        self.update_row_visibility()
        self.root.after(100, self.process_query_events)

    def _build_interface(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)

        header = ttk.Frame(self.root, padding=(24, 22, 24, 10))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        title = ttk.Label(header, text="Gaia Assist · Scientist", font=("Segoe UI", 17, "bold"))
        title.grid(row=0, column=0, sticky="w")
        ttk.Button(
            header,
            text="Bulk Query",
            command=self.open_bulk_query_window,
        ).grid(row=0, column=1, sticky="e")

        subtitle = ttk.Label(
            header,
            text="Temperature estimates with methods, uncertainties and review notes.",
            font=("Segoe UI", 10),
        )
        subtitle.grid(row=1, column=0, sticky="w", pady=(4, 0))

        input_frame = ttk.Frame(self.root, padding=(24, 8, 24, 14))
        input_frame.grid(row=1, column=0, sticky="ew")
        input_frame.columnconfigure(1, weight=1)

        self.input_label = ttk.Label(input_frame, text="Gaia Code")
        self.input_label.grid(row=0, column=0, sticky="w")

        code_entry = ttk.Entry(input_frame, textvariable=self.gaia_code, font=("Segoe UI", 11))
        code_entry.grid(row=0, column=1, sticky="ew", padx=(10, 10))
        code_entry.bind("<Return>", lambda _event: self.query_gaia_source())
        code_entry.focus()

        self.query_button = ttk.Button(
            input_frame,
            text="Start Query",
            command=self.query_gaia_source,
        )
        self.query_button.grid(row=0, column=2, sticky="e")

        ttk.Label(input_frame, text="Gaia ID Release").grid(
            row=1,
            column=0,
            sticky="w",
            pady=(10, 0),
        )
        self.release_selector = ttk.Combobox(
            input_frame,
            textvariable=self.gaia_release,
            values=("DR3", "DR2", "DR1", COMMON_NAME_RELEASE),
            state="readonly",
            width=24,
        )
        self.release_selector.grid(
            row=1,
            column=1,
            sticky="w",
            padx=(10, 0),
            pady=(10, 0),
        )
        self.release_selector.bind(
            "<<ComboboxSelected>>",
            self.update_input_mode,
        )

        field_mode_frame = ttk.Frame(input_frame)
        field_mode_frame.grid(row=1, column=2, sticky="e", pady=(10, 0))
        ttk.Label(field_mode_frame, text="Table mode:").pack(side="left", padx=(0, 4))
        for mode in ("Explain", "Copy"):
            ttk.Radiobutton(
                field_mode_frame, text=mode, value=mode,
                variable=self.field_name_mode, command=self.update_field_name_mode,
                style="Toolbutton",
            ).pack(side="left")

        ttk.Checkbutton(
            input_frame,
            text="Hide Gaia Data",
            variable=self.hide_gaia_data,
            command=self.update_row_visibility,
        ).grid(row=2, column=1, sticky="w", padx=(10, 0), pady=(8, 0))
        ttk.Checkbutton(
            input_frame,
            text="Hide Derived Data",
            variable=self.hide_derived_data,
            command=self.update_row_visibility,
        ).grid(row=2, column=1, sticky="w", padx=(145, 0), pady=(8, 0))

        ttk.Checkbutton(input_frame, text="Calculation details", style="Toolbutton",
                        variable=self.show_temperature_details,
                        command=self.update_row_visibility).grid(row=2, column=2, sticky="e", pady=(8, 0))

        self.status_label = ttk.Label(
            self.root,
            textvariable=self.status,
            padding=(24, 0, 24, 8),
            foreground="#555555",
        )
        self.status_label.grid(row=3, column=0, sticky="ew")

        action_frame = ttk.Frame(self.root, padding=(24, 0, 24, 14))
        action_frame.grid(row=4, column=0, sticky="ew")
        action_frame.columnconfigure(0, weight=1)
        ttk.Button(action_frame, text="Temperature Settings", command=self.open_temperature_settings).grid(row=2, column=0, sticky="w", pady=(8, 0))
        controls = ttk.Frame(action_frame)
        controls.grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 0))
        ttk.Checkbutton(controls, text="Force refresh (ignore cache)", variable=self.force_refresh).pack(side="left")
        ttk.Button(controls, text="Distance Settings", command=self.open_distance_settings).pack(side="left", padx=8)
        ttk.Button(controls, text="Network Settings", command=self.open_network_settings).pack(side="left", padx=8)
        ttk.Button(controls, text="Cancel Query", command=self.cancel_query).pack(side="left")
        ttk.Button(action_frame, text="Load Saved Results", command=self.load_saved_results).grid(row=2, column=1, columnspan=2, sticky="e", pady=(8, 0))
        self.sky_image_button = ttk.Button(
            action_frame,
            text="Show Sky Image",
            command=self.show_sky_image,
            state="disabled",
        )
        self.sky_image_button.grid(row=0, column=0, sticky="w")
        ttk.Label(
            action_frame,
            textvariable=self.sky_image_status,
            foreground="#555555",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(5, 0))
        ttk.Button(
            action_frame,
            text="Save",
            command=self.save_current_results,
        ).grid(row=0, column=1, sticky="e")
        ttk.Button(
            action_frame,
            text="Help",
            command=self.show_help_tutorial,
        ).grid(row=0, column=2, sticky="e", padx=(8, 0))

        result_frame = ttk.Frame(self.root, padding=(24, 0, 24, 12))
        result_frame.grid(row=2, column=0, sticky="nsew")
        result_frame.columnconfigure(0, weight=1)
        result_frame.rowconfigure(0, weight=1)

        table_container = ttk.Frame(result_frame)
        self.explain_table_container = table_container
        table_container.grid(row=0, column=0, sticky="nsew")
        table_container.columnconfigure(0, weight=1)
        table_container.rowconfigure(0, weight=1)

        self.result_canvas = tk.Canvas(table_container, highlightthickness=0)
        self.result_canvas.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(
            table_container,
            orient="vertical",
            command=self.result_canvas.yview,
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.result_canvas.configure(yscrollcommand=scrollbar.set)

        self.result_rows_frame = ttk.Frame(self.result_canvas)
        self.result_canvas_window = self.result_canvas.create_window(
            (0, 0),
            window=self.result_rows_frame,
            anchor="nw",
        )
        self.result_rows_frame.bind("<Configure>", self.update_result_scroll_region)
        self.result_canvas.bind("<Configure>", self.update_result_canvas_width)

        # A single Text widget allows one selection to span all three columns
        # and multiple rows; separate Entry/Text widgets cannot share a selection.
        self.copy_table_container = ttk.Frame(result_frame)
        self.copy_table_container.grid(row=0, column=0, sticky="nsew")
        self.copy_table_container.columnconfigure(0, weight=1)
        self.copy_table_container.rowconfigure(0, weight=1)
        self.copy_table = tk.Text(
            self.copy_table_container, width=1, height=1, wrap="none",
            borderwidth=0, highlightthickness=0, padx=8, pady=5,
            font=self.normal_value_font, background=self.result_background,
            foreground=self.result_foreground, cursor="xterm", state="disabled",
            exportselection=False, spacing1=4, spacing3=4, tabstyle="wordprocessor",
        )
        self.copy_table.grid(row=0, column=0, sticky="nsew")
        copy_y_scroll = ttk.Scrollbar(
            self.copy_table_container, orient="vertical", command=self.copy_table.yview,
        )
        copy_y_scroll.grid(row=0, column=1, sticky="ns")
        copy_x_scroll = ttk.Scrollbar(
            self.copy_table_container, orient="horizontal", command=self.copy_table.xview,
        )
        copy_x_scroll.grid(row=1, column=0, sticky="ew")
        self.copy_table.configure(yscrollcommand=copy_y_scroll.set, xscrollcommand=copy_x_scroll.set)
        self.copy_table.tag_configure("heading", font=("Segoe UI", 10, "bold"))
        for sequence in ("<Control-a>", "<Control-A>"):
            self.copy_table.bind(sequence, self.select_all_copy_table)
        ttk.Label(
            self.copy_table_container, text="Select across columns or rows, then press Ctrl+C.",
            foreground="#555555",
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.copy_table_container.grid_remove()

        ttk.Label(
            self.result_rows_frame,
            text="Field",
            font=("Segoe UI", 10, "bold"),
            padding=(8, 5),
        ).grid(row=0, column=0, sticky="ew")
        ttk.Label(
            self.result_rows_frame,
            text="Value",
            font=("Segoe UI", 10, "bold"),
            padding=(8, 5),
        ).grid(row=0, column=1, sticky="ew")
        ttk.Label(
            self.result_rows_frame,
            text="Unit",
            font=("Segoe UI", 10, "bold"),
            padding=(8, 5),
        ).grid(row=0, column=2, sticky="ew")

        self.result_rows_frame.columnconfigure(0, minsize=225)
        self.result_rows_frame.columnconfigure(1, weight=1, minsize=240)
        self.result_rows_frame.columnconfigure(2, minsize=135)

        for row_number, (column_name, label) in enumerate(DISPLAY_COLUMNS.items(), start=1):
            field_frame = ttk.Frame(self.result_rows_frame, padding=(8, 4))
            field_frame.grid(row=row_number, column=0, sticky="ew")
            field_frame.columnconfigure(0, weight=1)
            field_label = ttk.Label(
                field_frame,
                text=label,
                wraplength=310,
                font=self.normal_value_font,
                cursor="hand2",
            )
            field_label.grid(row=0, column=0, sticky="ew")
            field_label.bind(
                "<Enter>",
                lambda _event, field_name=column_name: self.set_field_hover(
                    field_name, True
                ),
            )
            field_label.bind(
                "<Leave>",
                lambda _event, field_name=column_name: self.set_field_hover(
                    field_name, False
                ),
            )
            field_label.bind(
                "<ButtonRelease-1>",
                lambda _event, field_name=column_name: self.show_field_explanation(
                    field_name
                ),
            )
            self.field_label_widgets[column_name] = field_label

            value_frame = ttk.Frame(self.result_rows_frame, padding=(8, 4))
            value_frame.grid(row=row_number, column=1, sticky="ew")
            value_frame.columnconfigure(0, weight=0)

            value_label = ttk.Label(
                value_frame,
                text=self.result_vars[column_name].get(),
                font=self.normal_value_font,
            )
            value_label.grid(row=0, column=0, sticky="w")
            self.result_value_widgets[column_name] = {
                "frame": value_frame,
                "label": value_label,
            }
            self.update_result_value(column_name, self.result_vars[column_name].get())

            unit_frame = ttk.Frame(self.result_rows_frame, padding=(8, 4))
            unit_frame.grid(row=row_number, column=2, sticky="ew")
            unit_widget = self.create_copyable_value_widget(unit_frame, width=15)
            self.set_copyable_value_text(
                unit_widget,
                FIELD_UNITS.get(column_name, ""),
            )
            self.unit_widgets[column_name] = unit_widget
            self.row_widgets[column_name] = (
                field_frame,
                value_frame,
                unit_frame,
            )

    def update_field_name_mode(self):
        self.hide_field_preview()
        for label in self.field_label_widgets.values():
            label.configure(font=self.normal_value_font)
        if self.field_name_mode.get() == "Copy":
            self.refresh_copy_table()
            self.explain_table_container.grid_remove()
            self.copy_table_container.grid()
            self.copy_table.focus_set()
        else:
            self.copy_table.tag_remove("sel", "1.0", "end")
            if self.root.focus_get() == self.copy_table:
                self.root.focus_set()
            self.copy_table_container.grid_remove()
            self.explain_table_container.grid()

    def open_temperature_settings(self):
        from temperature_ui import open_settings
        open_settings(self)

    def open_distance_settings(self):
        from temperature_ui import open_distance_settings
        open_distance_settings(self)

    def open_network_settings(self):
        from temperature_ui import open_network_settings
        open_network_settings(self)

    def cancel_query(self):
        self.query_cancel.set()
        self.status.set("Cancelling query; displayed results retained.")

    def close_app(self):
        self.query_cancel.set()
        self.query_generation += 1
        network.cancel_all()
        deadline = time.monotonic()+4
        def finish_close():
            if network.active_queries() and time.monotonic() < deadline:
                self.root.after(50, finish_close)
            else:
                self.root.destroy()
        finish_close()

    def load_saved_results(self):
        from temperature_ui import load_saved_results
        load_saved_results(self)

    def refresh_copy_table(self):
        if not hasattr(self, "copy_table") or self.field_name_mode.get() != "Copy":
            return
        from tkinter import font as tkfont

        rows = [
            (label, self.result_vars[key].get(), FIELD_UNITS.get(key, ""))
            for key, label in DISPLAY_COLUMNS.items()
            if not (
                (self.hide_gaia_data.get() and key in GAIA_COLUMNS)
                or (self.hide_derived_data.get() and key in DERIVED_COLUMNS)
                or (self.is_detail_field(key) and not self.show_temperature_details.get())
                or empty_historical(key, self.result_vars[key].get())
            )
        ]
        font = tkfont.Font(root=self.root, font=self.normal_value_font)
        heading_font = tkfont.Font(root=self.root, font=("Segoe UI", 10, "bold"))
        field_width = max([heading_font.measure("Field")] + [font.measure(row[0]) for row in rows]) + 24
        value_width = max([heading_font.measure("Value")] + [font.measure(compact_text(row[1])) for row in rows]) + 24
        self.copy_table.configure(state="normal", tabs=(field_width, field_width + value_width))
        self.copy_table.delete("1.0", "end")
        self.copy_table.insert("end", "Field\tValue\tUnit\n", "heading")
        self.copy_full_values = {}
        self.copy_hover_line = None
        self.copy_table.tag_configure("hidden_tail", elide=True)
        for label, value, unit in rows:
            line = int(self.copy_table.index("end-1c").split(".")[0])
            self.copy_full_values[line] = value
            self.copy_table.insert("end", label + "\t")
            short = compact_text(value)
            if short != value:
                self.copy_table.insert("end", value[:61])
                self.copy_table.insert("end", "...", "ellipsis")
                self.copy_table.insert("end", value[61:], "hidden_tail")
            else:
                self.copy_table.insert("end", value)
            self.copy_table.insert("end", "\t" + unit + "\n")
        self.copy_table.bind("<Motion>", self.preview_copy_value)
        self.copy_table.bind("<Leave>", lambda _e: (self.hide_field_preview(), setattr(self, "copy_hover_line", None)))
        self.copy_table.bind("<<Copy>>", self.copy_selected_table)
        self.copy_table.bind("<Control-c>", self.copy_selected_table)
        self.copy_table.configure(state="disabled")

    def select_all_copy_table(self, _event=None):
        self.copy_table.tag_add("sel", "1.0", "end-1c")
        return "break"

    def is_detail_field(self, key):
        record = self.current_record or {}
        if key in ("distance_parsecs", "distance_lightyears") and record.get("adopted_distance_pc") is None and record.get(key) is not None:
            return False  # Keep historical distance visible without relabelling it.
        return key in TEMPERATURE_DETAIL_FIELDS

    def update_row_visibility(self):
        hide_gaia_rows = self.hide_gaia_data.get()
        hide_derived_rows = self.hide_derived_data.get()

        for column_name in DISPLAY_COLUMNS:
            should_hide = (
                (column_name in GAIA_COLUMNS and hide_gaia_rows)
                or (column_name in DERIVED_COLUMNS and hide_derived_rows)
                or (self.is_detail_field(column_name) and not self.show_temperature_details.get())
                or empty_historical(column_name, self.result_vars[column_name].get())
            )
            for widget in self.row_widgets[column_name]:
                if should_hide:
                    widget.grid_remove()
                else:
                    widget.grid()
        self.refresh_copy_table()

    def open_bulk_query_window(self):
        BulkQueryWindow(self)

    def update_input_mode(self, _event=None):
        if self.gaia_release.get() == COMMON_NAME_RELEASE:
            self.input_label.configure(text="Common Name")
        else:
            self.input_label.configure(text="Gaia Code")

    def set_field_hover(self, field_name, is_hovered):
        if self.field_name_mode.get() != "Explain":
            return
        font = self.underline_value_font if is_hovered else self.normal_value_font
        self.field_label_widgets[field_name].configure(font=font)
        if is_hovered:
            self.show_field_preview(field_name)
        else:
            self.hide_field_preview()

    def show_field_explanation(self, field_name):
        if self.field_name_mode.get() != "Explain":
            return
        self.hide_field_preview()
        title = DISPLAY_COLUMNS[field_name]
        explanation = FIELD_EXPLANATIONS.get(field_name, "")
        if not explanation:
            explanation = "Explanation not added yet."

        self.show_centered_message_window(title, explanation)

    def show_field_preview(self, field_name):
        self.hide_field_preview()
        explanation = FIELD_EXPLANATIONS.get(field_name, "")
        if not explanation:
            explanation = "Explanation not added yet."

        anchor = self.field_label_widgets[field_name]
        preview = tk.Toplevel(self.root)
        preview.wm_overrideredirect(True)
        preview.attributes("-topmost", True)

        frame = tk.Frame(
            preview,
            background="#172033",
            borderwidth=1,
            relief="solid",
        )
        frame.pack(fill="both", expand=True)
        tk.Label(
            frame,
            text=explanation,
            justify="left",
            wraplength=360,
            background="#172033",
            foreground="#ffffff",
            padx=10,
            pady=8,
            font=("Segoe UI", 9),
        ).pack(fill="both", expand=True)

        preview.update_idletasks()
        preview_width = preview.winfo_reqwidth()
        preview_height = preview.winfo_reqheight()
        screen_width = preview.winfo_screenwidth()

        position_x = anchor.winfo_rootx()
        position_y = anchor.winfo_rooty() - preview_height - 8
        if position_y < 0:
            position_y = anchor.winfo_rooty() + anchor.winfo_height() + 8
        position_x = max(0, min(position_x, screen_width - preview_width - 4))

        preview.geometry(f"+{position_x}+{position_y}")
        self.field_preview_window = preview

    def hide_field_preview(self):
        if self.field_preview_window is not None:
            self.field_preview_window.destroy()
            self.field_preview_window = None

    def update_result_scroll_region(self, _event):
        self.result_canvas.configure(scrollregion=self.result_canvas.bbox("all"))

    def update_result_canvas_width(self, event):
        self.result_canvas.itemconfigure(self.result_canvas_window, width=event.width)

    def update_result_value(self, column_name, display_value):
        if column_name == "excess_noise_factor":
            self.update_excess_noise_factor_value(display_value)
            return
        if column_name == "bp_rp_excess_correctness":
            self.update_bp_rp_excess_correctness_value(display_value)
            return
        if column_name == "star_type":
            self.update_star_type_value(display_value)
            return

        widget_info = self.result_value_widgets[column_name]
        value_widget = widget_info["label"]

        if not isinstance(value_widget, tk.Text):
            value_widget.destroy()
            value_widget = self.create_copyable_value_widget(widget_info["frame"])
            widget_info["label"] = value_widget

        self.set_copyable_value_text(value_widget, display_value)

    def create_copyable_value_widget(self, parent, cursor="xterm", width=46):
        value_widget = tk.Text(
            parent,
            height=1,
            width=width,
            wrap="none",
            borderwidth=0,
            highlightthickness=0,
            padx=0,
            pady=0,
            font=self.normal_value_font,
            background=self.result_background,
            foreground=self.result_foreground,
            cursor=cursor,
        )
        value_widget.grid(row=0, column=0, sticky="w")
        return value_widget

    def set_copyable_value_text(self, value_widget, display_value):
        full_text = str(display_value)
        short = compact_text(full_text, int(value_widget.cget("width")))
        value_widget.configure(state="normal", wrap="none", height=1)
        value_widget.delete("1.0", "end")
        value_widget.insert("1.0", short)
        value_widget.configure(state="disabled")
        value_widget.bind("<ButtonRelease-1>", lambda _e: self.show_full_value(full_text) if short != full_text else None)
        value_widget.configure(cursor="hand2" if short != full_text else "xterm")

    def show_full_value(self, text):
        self.show_centered_message_window("Full result value", text, 720, 440)

    def show_value_preview(self, event, text):
        self.hide_field_preview()
        preview = tk.Toplevel(self.root)
        preview.wm_overrideredirect(True)
        preview.attributes("-topmost", True)
        label = tk.Label(preview, text=text, wraplength=620, justify="left",
                         background="#172033", foreground="white", padx=10, pady=8)
        label.pack()
        preview.update_idletasks()
        x = min(event.x_root, preview.winfo_screenwidth()-preview.winfo_reqwidth()-8)
        y = min(event.y_root+22, preview.winfo_screenheight()-preview.winfo_reqheight()-8)
        preview.geometry(f"+{max(0, x)}+{max(0, y)}")
        self.field_preview_window = preview

    def preview_copy_value(self, event):
        line = int(self.copy_table.index(f"@{event.x},{event.y}").split(".")[0])
        text = getattr(self, "copy_full_values", {}).get(line)
        if getattr(self, "copy_hover_line", None) == line:
            return
        self.copy_hover_line = line
        self.hide_field_preview()
        if text and compact_text(text) != text:
            self.show_value_preview(event, text)

    def copy_selected_table(self, _event=None):
        try:
            start, end = self.copy_table.index("sel.first"), self.copy_table.index("sel.last")
        except tk.TclError:
            return "break"
        # Elided tails remain selected and copy in full; omit display-only dots.
        pieces = []
        for kind, value, index in self.copy_table.dump(start, end, text=True):
            if kind == "text" and "ellipsis" not in self.copy_table.tag_names(index):
                pieces.append(value)
        self.root.clipboard_clear()
        self.root.clipboard_append("".join(pieces))
        return "break"

    def update_excess_noise_factor_value(self, display_value):
        widget_info = self.result_value_widgets["excess_noise_factor"]
        value_frame = widget_info["frame"]

        for child in value_frame.winfo_children():
            child.destroy()

        warning_active = display_value not in ("-", "accurate")

        value_widget = self.create_copyable_value_widget(
            value_frame,
            cursor="hand2" if warning_active else "xterm",
        )
        widget_info["label"] = value_widget
        widget_info.pop("star_label", None)

        if not warning_active:
            self.set_copyable_value_text(value_widget, display_value)
            widget_info.pop("star_label", None)
            return

        text_without_marker = display_value.replace(" *", "")
        value_widget.configure(state="normal")
        value_widget.insert("1.0", text_without_marker)
        value_widget.insert("end", " *", ("warning_star",))
        value_widget.tag_add("warning_text", "1.0", "end-1c")
        value_widget.tag_configure("warning_star", foreground="#0b63ce")
        value_widget.tag_bind(
            "warning_text",
            "<Enter>",
            lambda _event: self.set_excess_noise_hover(True),
        )
        value_widget.tag_bind(
            "warning_text",
            "<Leave>",
            lambda _event: self.set_excess_noise_hover(False),
        )
        value_widget.tag_bind(
            "warning_text",
            "<ButtonRelease-1>",
            lambda _event: self.show_excess_noise_factor_warning(),
        )
        value_widget.configure(state="disabled")

    def set_excess_noise_hover(self, is_hovered):
        widget_info = self.result_value_widgets["excess_noise_factor"]
        font = self.underline_value_font if is_hovered else self.normal_value_font

        widget_info["label"].configure(font=font)

    def show_excess_noise_factor_warning(self):
        message = (
            "The Excess Noise Factor observed of this celestial object might be "
            "abnormal. This can be caused by a hidden binary or companion stars, "
            "an exoplanet, or an unexplained \"wobble\"."
        )
        self.show_centered_message_window("Excess Noise Factor", message)

    def update_bp_rp_excess_correctness_value(self, display_value):
        widget_info = self.result_value_widgets["bp_rp_excess_correctness"]
        value_frame = widget_info["frame"]

        for child in value_frame.winfo_children():
            child.destroy()

        warning_active = display_value == "unreliable *"
        value_widget = self.create_copyable_value_widget(
            value_frame,
            cursor="hand2" if warning_active else "xterm",
        )
        widget_info["label"] = value_widget

        if not warning_active:
            self.set_copyable_value_text(value_widget, display_value)
            return

        value_widget.configure(state="normal")
        value_widget.insert("1.0", "unreliable")
        value_widget.insert("end", " *", ("warning_star",))
        value_widget.tag_add("warning_text", "1.0", "end-1c")
        value_widget.tag_configure("warning_star", foreground="#0b63ce")
        value_widget.tag_bind(
            "warning_text",
            "<Enter>",
            lambda _event: self.set_bp_rp_excess_hover(True),
        )
        value_widget.tag_bind(
            "warning_text",
            "<Leave>",
            lambda _event: self.set_bp_rp_excess_hover(False),
        )
        value_widget.tag_bind(
            "warning_text",
            "<ButtonRelease-1>",
            lambda _event: self.show_bp_rp_excess_warning(),
        )
        value_widget.configure(state="disabled")

    def set_bp_rp_excess_hover(self, is_hovered):
        font = self.underline_value_font if is_hovered else self.normal_value_font
        self.result_value_widgets["bp_rp_excess_correctness"]["label"].configure(
            font=font
        )

    def show_bp_rp_excess_warning(self):
        message = (
            "Often seen in heavily obscured or red objects where the blue photons "
            "are entirely swallowed by dust/extinction, preventing an accurate "
            "BP measurement."
        )
        self.show_centered_message_window(
            "BP+RP Excess Flux Correctness",
            message,
        )

    def update_star_type_value(self, display_value):
        widget_info = self.result_value_widgets["star_type"]
        value_frame = widget_info["frame"]

        for child in value_frame.winfo_children():
            child.destroy()

        warning_active = "*" in display_value
        value_widget = self.create_copyable_value_widget(
            value_frame,
            cursor="hand2" if warning_active else "xterm",
        )
        widget_info["label"] = value_widget

        if not warning_active:
            self.set_copyable_value_text(value_widget, display_value)
            return

        value_widget.configure(state="normal")
        pieces = display_value.split("*")
        for index, piece in enumerate(pieces):
            value_widget.insert("end", piece)
            if index < len(pieces) - 1:
                value_widget.insert("end", "*", ("warning_star",))
        value_widget.tag_add("warning_text", "1.0", "end-1c")
        value_widget.tag_configure("warning_star", foreground="#0b63ce")
        value_widget.tag_bind(
            "warning_text",
            "<Enter>",
            lambda _event: self.set_star_type_hover(True),
        )
        value_widget.tag_bind(
            "warning_text",
            "<Leave>",
            lambda _event: self.set_star_type_hover(False),
        )
        value_widget.tag_bind(
            "warning_text",
            "<ButtonRelease-1>",
            lambda _event: self.show_star_type_warning(),
        )
        value_widget.configure(state="disabled")

    def set_star_type_hover(self, is_hovered):
        font = self.underline_value_font if is_hovered else self.normal_value_font
        self.result_value_widgets["star_type"]["label"].configure(font=font)

    def show_star_type_warning(self):
        message = (
            "A luminosity class VI result indicates that the object may be either "
            "a poor main-sequence star (subdwarf) or a white dwarf."
        )
        self.show_centered_message_window("Star Type", message)

    def show_help_tutorial(self):
        self.show_centered_message_window(
            "Using Gaia Assist",
            HELP_TUTORIAL,
            window_width=560,
            window_height=560,
        )

    def show_centered_message_window(
        self,
        title,
        message,
        window_width=420,
        window_height=190,
    ):
        message_window = tk.Toplevel(self.root)
        message_window.title(title)
        screen_width = message_window.winfo_screenwidth()
        screen_height = message_window.winfo_screenheight()
        position_x = (screen_width - window_width) // 2
        position_y = (screen_height - window_height) // 2
        message_window.geometry(
            f"{window_width}x{window_height}+{position_x}+{position_y}"
        )
        message_window.resizable(True, True)
        message_window.transient(self.root)
        message_window.grab_set()

        message_text = tk.Text(
            message_window,
            wrap="word",
            height=max(5, window_height // 28),
            borderwidth=0,
            highlightthickness=0,
            padx=22,
            pady=18,
            font=("Segoe UI", 10),
        )
        message_text.insert("1.0", message)
        message_text.configure(state="disabled")
        scroll = ttk.Scrollbar(message_window, command=message_text.yview)
        scroll.pack(side="right", fill="y")
        message_text.configure(yscrollcommand=scroll.set)
        message_text.pack(fill="both", expand=True)

        ttk.Button(
            message_window,
            text="OK",
            command=message_window.destroy,
        ).pack(pady=(0, 18))

    def save_current_results(self):
        if all(self.result_vars[column_name].get() == "-" for column_name in DISPLAY_COLUMNS):
            messagebox.showwarning(
                "Nothing to save",
                "Please query an object before saving.",
            )
            return

        object_key = self.result_vars["source_id"].get().strip()
        if not object_key or object_key == "-":
            object_key = self.gaia_code.get().strip() or "unknown_object"

        if object_key == self.last_saved_object_key:
            should_save_again = messagebox.askyesno(
                "Save the same object again?",
                (
                    "This object was just saved. Do you still want to "
                    "create another saved file for it?"
                ),
            )
            if not should_save_again:
                return

        try:
            saved_file = self.write_results_file(object_key)
        except OSError as error:
            LOGGER.exception("Saving results failed for object=%s", object_key)
            messagebox.showerror(
                "Save failed",
                f"The data could not be saved.\n\n{error}",
            )
            return

        self.last_saved_object_key = object_key
        messagebox.showinfo(
            "Successfully saved",
            f"Data saved successfully to:\n{saved_file}",
        )

    def write_results_file(self, object_key):
        SAVED_OBJECTS_DIR.mkdir(exist_ok=True)
        timestamp = datetime.now()
        safe_object_key = re.sub(r"[^A-Za-z0-9_-]+", "_", object_key).strip("_")
        if not safe_object_key:
            safe_object_key = "unknown_object"

        saved_file = SAVED_OBJECTS_DIR / (
            f"gaia_{safe_object_key}_{timestamp:%Y%m%d_%H%M%S_%f}.txt"
        )

        with saved_file.open("w", encoding="utf-8") as output_file:
            output_file.write("Gaia Assist Saved Object Data\n")
            output_file.write(
                f"Saved At: {timestamp.isoformat(timespec='seconds')}\n"
            )
            output_file.write(f"Input Mode: {self.gaia_release.get()}\n")
            output_file.write(f"Input Value: {self.gaia_code.get().strip()}\n")
            output_file.write("\n")
            output_file.write("Field\tValue\tUnit\n")

            for column_name, label in DISPLAY_COLUMNS.items():
                value = format_export_value(self.current_record.get(column_name)) if self.current_record else self.result_vars[column_name].get()
                unit = FIELD_UNITS.get(column_name, "")
                if not value:
                    value = "-"
                if not unit:
                    unit = "-"
                output_file.write(f"{label}\t{value}\t{unit}\n")

        from temperature_storage import save_records, save_csv
        save_csv(saved_file.with_suffix(".csv"), [self.current_record or {
            key: variable.get() for key, variable in self.result_vars.items()
        }], DISPLAY_COLUMNS)
        save_records(saved_file.with_suffix(".json"), [self.current_record or {
            key: variable.get() for key, variable in self.result_vars.items()
        }])
        return saved_file

    def query_gaia_source(self):
        if self.query_in_progress:
            return

        source_id = self.gaia_code.get().strip()
        if not source_id:
            messagebox.showwarning("Gaia Code required", "Please enter a Gaia source_id.")
            return

        release = self.gaia_release.get()
        if release != COMMON_NAME_RELEASE and not source_id.isdigit():
            messagebox.showwarning(
                "Check Gaia Code",
                "Gaia source_id values contain digits only.",
            )
            return
        self.reset_sky_image()
        self.query_generation += 1
        self.query_cancel = threading.Event()
        self.query_in_progress = True
        self.query_button.configure(state="disabled")
        self.release_selector.configure(state="disabled")
        self.status.set(f"Resolving {release} source and querying Gaia DR3...")
        LOGGER.info(
            "Starting query pipeline for release=%s source_id=%s",
            release,
            source_id,
        )

        worker = threading.Thread(
            target=self.run_query_pipeline,
            args=(source_id, release, self.temperature_options, self.query_generation, self.query_cancel, self.force_refresh.get()),
            daemon=True,
        )
        worker.start()

    def run_query_pipeline(self, source_id, release, options=None, generation=None, cancel=None, force_refresh=False):
        generation = self.query_generation if generation is None else generation
        def send(event):
            self.query_events.put(("query", generation, event))
        def preview(data):
            # No optional dust request before the basic data/colour estimate is visible.
            derived = calculate_derived_data(data, options, skip_dust=True)
            send(("preview", self.build_display_data(data, derived)))
        try:
            with network.query_context(cancel=cancel, force_refresh=force_refresh, progress=lambda msg: send(("status", msg))) as context:
                source_data = fetch_gaia_source_data(source_id, release, on_basic=preview)
                preview(source_data)
                log_missing_values(source_id, source_data)
                derived_data = calculate_derived_data(source_data, options or self.temperature_options)
                display_data = self.build_display_data(source_data, derived_data)
                warnings = collect_pipeline_warnings(source_data, derived_data)
                if context.cancel.is_set():
                    raise network.QueryCancelled("Query cancelled")
        except network.QueryCancelled:
            send(("cancelled",))
            return
        except Exception as error:
            LOGGER.exception(
                "Query pipeline failed for release=%s source_id=%s",
                release,
                source_id,
            )
            send(("error", source_id, release, error))
            return

        LOGGER.info(
            "Query pipeline completed for release=%s source_id=%s",
            release,
            source_id,
        )
        send(("success", source_id, release, display_data, warnings))

    def process_query_events(self):
        try:
            while True:
                event = self.query_events.get_nowait()
                if event[0] == "query":
                    if event[1] != self.query_generation:
                        continue
                    event = event[2]
                event_type = event[0]

                if event_type == "preview":
                    self.current_record = dict(event[1])
                    for key, value in event[1].items():
                        if key in self.result_vars:
                            display = format_display_value(key, value)
                            self.result_vars[key].set(display)
                            self.update_result_value(key, display)
                    self.update_row_visibility()
                    self.status.set("Basic results available; finishing optional data.")
                elif event_type == "cancelled":
                    self.finish_query()
                    self.status.set("Query cancelled; displayed results retained.")
                elif event_type == "status":
                    self.status.set(event[1])
                elif event_type == "success":
                    self.handle_query_success(
                        event[1], event[2], event[3], event[4]
                    )
                elif event_type == "error":
                    self.handle_query_error(event[1], event[2], event[3])
                elif event_type in ("sky_image_success", "sky_image_error"):
                    self.handle_sky_image_event(event)
        except queue.Empty:
            pass

        self.root.after(100, self.process_query_events)

    @staticmethod
    def build_display_data(source_data, derived_data):
        display_data = {
            column_name: None for column_name in DISPLAY_COLUMNS
        }
        display_data.update(source_data)
        display_data.update(derived_data)
        return display_data

    def handle_query_success(self, source_id, release, display_data, warnings):
        self.current_record = dict(display_data)
        for column_name, value in display_data.items():
            if column_name not in self.result_vars:
                continue
            display_value = format_display_value(column_name, value)
            self.result_vars[column_name].set(display_value)
            self.update_result_value(column_name, display_value)

        self.update_row_visibility()
        self.finish_query()
        matched_source_id = display_data["source_id"]
        if release == "DR3":
            loaded_text = f"Loaded Gaia DR3 source {matched_source_id}"
        elif release == COMMON_NAME_RELEASE:
            loaded_text = (
                f"Loaded DR3 source {matched_source_id} resolved from "
                f'common name "{source_id}"'
            )
        else:
            loaded_text = (
                f"Loaded DR3 counterpart {matched_source_id} for "
                f"{release} source {source_id}"
            )

        if warnings:
            warning_text = "; ".join(warnings)
            self.status.set(
                f"{loaded_text}; {warning_text}. See debug log."
            )
        else:
            self.status.set(f"{loaded_text}.")

        self.prepare_sky_image(display_data)

    def reset_sky_image(self):
        # A previous object's network request may still finish; ignore its events.
        self.sky_image_request_id += 1
        self.close_sky_image()
        self.sky_image_coordinates = None
        self.sky_image_source_id = None
        self.sky_image_data = None
        self.sky_image_error = None
        self.sky_image_loading = False
        self.sky_image_button.configure(state="disabled")
        self.sky_image_status.set("Sky image available after results.")

    def prepare_sky_image(self, display_data):
        try:
            self.sky_image_coordinates = sky_image_coordinates(
                display_data.get("ra"), display_data.get("dec")
            )
        except ValueError:
            self.sky_image_status.set("Sky image unavailable: missing or invalid RA/DEC.")
            return
        self.sky_image_source_id = display_data["source_id"]
        self.sky_image_loading = True
        self.sky_image_button.configure(state="normal")
        self.sky_image_status.set("Sky image loading in background...")
        # Flush result layout/paint before even scheduling the image request.
        self.root.update_idletasks()
        self.root.after_idle(self.start_sky_image_query, self.sky_image_request_id)

    def start_sky_image_query(self, request_id):
        if request_id != self.sky_image_request_id or self.sky_image_coordinates is None:
            return
        self.sky_image_error = None
        self.sky_image_loading = True
        self.sky_image_status.set("Sky image loading in background...")
        self.update_sky_image_window()
        threading.Thread(
            target=self.run_sky_image_query,
            args=(request_id, self.sky_image_coordinates),
            daemon=True,
        ).start()

    def run_sky_image_query(self, request_id, coordinates):
        # Workers exchange bytes through the queue; all Tk work stays on the UI thread.
        try:
            image_data = fetch_esasky_image(*coordinates)
        except Exception as error:
            LOGGER.exception("ESA ESASky image failed for coordinates=%s", coordinates)
            self.query_events.put(("sky_image_error", request_id, str(error)))
        else:
            self.query_events.put(("sky_image_success", request_id, image_data))

    def handle_sky_image_event(self, event):
        if event[1] != self.sky_image_request_id:
            return
        self.sky_image_loading = False
        if event[0] == "sky_image_success":
            self.sky_image_data = event[2]
            self.sky_image_error = None
            self.sky_image_status.set("Sky image ready: DSS2 color (Optical).")
        else:
            self.sky_image_data = None
            self.sky_image_error = event[2]
            self.sky_image_status.set("Sky image unavailable. Open Show Sky Image to retry.")
        self.update_sky_image_window()

    def show_sky_image(self):
        if self.sky_image_coordinates is None:
            return
        if self.sky_image_window is not None and self.sky_image_window.winfo_exists():
            self.sky_image_window.deiconify()
            self.sky_image_window.lift()
            return

        window = tk.Toplevel(self.root)
        self.sky_image_window = window
        window.title(f"ESA Sky Image - Gaia DR3 {self.sky_image_source_id}")
        window.transient(self.root)
        window.resizable(False, False)
        window.protocol("WM_DELETE_WINDOW", self.close_sky_image)
        frame = ttk.Frame(window, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(
            frame,
            text=f"DSS2 color (Optical) | {SKY_IMAGE_FOV_ARCMIN:.1f}' x {SKY_IMAGE_FOV_ARCMIN:.1f}'",
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w")
        ra, dec = self.sky_image_coordinates
        ttk.Label(
            frame,
            text=f"Centered on Gaia DR3 {self.sky_image_source_id}\n"
            f"ICRS RA {ra:.8f} deg, DEC {dec:+.8f} deg",
        ).pack(anchor="w", pady=(4, 10))
        self.sky_image_canvas = tk.Canvas(
            frame,
            width=SKY_IMAGE_SIZE,
            height=SKY_IMAGE_SIZE,
            background="black",
            highlightthickness=0,
        )
        self.sky_image_canvas.pack()
        footer = ttk.Frame(frame)
        footer.pack(fill="x", pady=(10, 0))
        ttk.Label(footer, text="DSS2: STScI/NASA, CDS | ESA ESASky").pack(side="left")
        ttk.Button(footer, text="Close", command=self.close_sky_image).pack(side="right")
        self.sky_image_retry_button = ttk.Button(
            footer, text="Retry", command=self.retry_sky_image
        )
        self.sky_image_retry_button.pack(side="right", padx=(0, 8))
        self.update_sky_image_window()

    def update_sky_image_window(self):
        if self.sky_image_window is None or not self.sky_image_window.winfo_exists():
            return
        self.sky_image_canvas.delete("all")
        if self.sky_image_data is not None:
            try:
                # Tk 8.6+ reads PNG directly, so no extra image package is needed.
                self.sky_image_photo = tk.PhotoImage(
                    master=self.sky_image_window, data=self.sky_image_data, format="png"
                )
                self.sky_image_canvas.create_image(
                    SKY_IMAGE_SIZE // 2,
                    SKY_IMAGE_SIZE // 2,
                    image=self.sky_image_photo,
                    anchor="center",
                )
            except tk.TclError as error:
                LOGGER.exception("Displaying ESA ESASky image failed")
                self.sky_image_data = None
                self.sky_image_error = f"The sky image could not be displayed: {error}"
                self.sky_image_status.set("Sky image unavailable. Open Show Sky Image to retry.")
        if self.sky_image_data is None:
            text = "Loading DSS2 color image from ESA ESASky..."
            if self.sky_image_error:
                text = f"Sky image unavailable.\n\n{self.sky_image_error}\n\nClick Retry to try again."
            self.sky_image_canvas.create_text(
                SKY_IMAGE_SIZE // 2,
                SKY_IMAGE_SIZE // 2,
                text=text,
                fill="white",
                width=SKY_IMAGE_SIZE - 60,
                justify="center",
                font=("Segoe UI", 11),
            )
        self.sky_image_retry_button.configure(
            state="normal" if self.sky_image_error and not self.sky_image_loading else "disabled"
        )

    def retry_sky_image(self):
        if self.sky_image_loading or self.sky_image_coordinates is None:
            return
        self.sky_image_request_id += 1
        self.start_sky_image_query(self.sky_image_request_id)

    def close_sky_image(self):
        if self.sky_image_window is not None and self.sky_image_window.winfo_exists():
            self.sky_image_window.destroy()
        self.sky_image_window = None
        self.sky_image_photo = None

    def handle_query_error(self, source_id, release, error):
        self.finish_query()
        if isinstance(error, QueryServiceError):
            service = error.service
        else:
            service = "calculation pipeline"

        self.status.set("Query timed out; displayed basic results retained." if isinstance(error, network.QueryTimeout)
                        else f"{service} failed; displayed results retained. See temperature_debug.log.")
        messagebox.showerror(
            f"{service} failed",
            f"{release} source {source_id} could not be completed.\n\n"
            f"{error}\n\nDetails were written to:\n{DEBUG_LOG}",
        )

    def finish_query(self):
        self.query_in_progress = False
        self.query_button.configure(state="normal")
        self.release_selector.configure(state="readonly")


def cluster_analysis_warning_reasons(display_data):
    """Assess the full result before the user-selected columns are extracted."""
    reasons = []
    for key, label in (
        ("ruwe_correctness", "RUWE"),
        ("parallax_correctness", "Parallax over error"),
        ("bp_rp_excess_correctness", "Corrected excess flux"),
    ):
        if str(display_data.get(key, "")).strip().casefold() == "unreliable":
            reasons.append(f"{label} is rated Unreliable.")
    parallax = display_data.get("parallax")
    if parallax is None:
        reasons.append("Parallax is missing.")
    elif parallax < 0:
        reasons.append("Parallax is negative.")
    return reasons


class BulkQueryWindow:
    COLUMN_BLOCKS_PER_ROW = 5

    def __init__(self, app):
        self.app = app
        self.window = tk.Toplevel(app.root)
        self.window.title("Bulk Query")
        self.window.geometry("1120x720")
        self.window.minsize(980, 620)
        self.window.transient(app.root)

        self.release = tk.StringVar(value="DR3")
        self.status = tk.StringVar(
            value="Paste one object per row, or load a text file."
        )
        self.selected_columns = {
            column_name: tk.BooleanVar(value=column_name in PRIMARY_DISPLAY_ORDER)
            for column_name in DISPLAY_COLUMNS
        }
        self.column_order = list(DISPLAY_COLUMNS)
        self.column_block_frames = []
        self.dragged_column = None
        self.object_inputs = []
        self.input_buffer = ""
        self.result_rows = []
        self.current_page = 0
        self.rows_per_page = tk.IntVar(value=10)
        self.query_events = queue.Queue()
        self.query_in_progress = False
        self.bulk_completed = False
        self.cancel_event = threading.Event()
        self.carbon_only = tk.BooleanVar(value=False)
        self.force_refresh_snapshot = False
        self.cluster_analysis_window = None
        self.is_closed = False

        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(0, weight=1)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.show_input_page()

    def close(self):
        self.cancel_event.set()
        self.is_closed = True
        self.query_in_progress = False
        self.clear_window()
        self.window.destroy()

    def clear_window(self):
        analysis = getattr(self, "cluster_analysis_window", None)
        if analysis is not None and analysis.window.winfo_exists():
            analysis.close()
        self.cluster_analysis_window = None
        if getattr(self, "cluster_marker_after_id", None) is not None:
            self.results_table.after_cancel(self.cluster_marker_after_id)
            self.cluster_marker_after_id = None
            self.cluster_marker_refresh_pending = False
        for child in self.window.winfo_children():
            child.destroy()

    def show_input_page(self):
        self.clear_window()
        self.window.rowconfigure(0, weight=1)

        frame = ttk.Frame(self.window, padding=18)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)

        top_bar = ttk.Frame(frame)
        top_bar.grid(row=0, column=0, sticky="ew")
        top_bar.columnconfigure(1, weight=1)

        ttk.Label(
            top_bar,
            text="Bulk Query",
            font=("Segoe UI", 17, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(
            top_bar,
            text="Guide",
            command=self.show_guide,
        ).grid(row=0, column=2, sticky="e")

        controls = ttk.Frame(frame)
        controls.grid(row=1, column=0, sticky="ew", pady=(14, 10))
        controls.columnconfigure(2, weight=1)

        ttk.Label(controls, text="Input Type").grid(row=0, column=0, sticky="w")
        ttk.Combobox(
            controls,
            textvariable=self.release,
            values=("DR3", "DR2", "DR1", COMMON_NAME_RELEASE),
            state="readonly",
            width=24,
        ).grid(row=0, column=1, sticky="w", padx=(8, 18))
        ttk.Button(
            controls,
            text="Load Text File",
            command=self.load_text_file,
        ).grid(row=0, column=3, sticky="e")

        text_frame = ttk.Frame(frame)
        text_frame.grid(row=2, column=0, sticky="nsew")
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)

        self.input_text = tk.Text(
            text_frame,
            wrap="none",
            font=("Consolas", 10),
            undo=True,
        )
        self.input_text.grid(row=0, column=0, sticky="nsew")
        if self.input_buffer:
            self.input_text.insert("1.0", self.input_buffer)
        y_scroll = ttk.Scrollbar(
            text_frame,
            orient="vertical",
            command=self.input_text.yview,
        )
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll = ttk.Scrollbar(
            text_frame,
            orient="horizontal",
            command=self.input_text.xview,
        )
        x_scroll.grid(row=1, column=0, sticky="ew")
        self.input_text.configure(
            yscrollcommand=y_scroll.set,
            xscrollcommand=x_scroll.set,
        )

        bottom_bar = ttk.Frame(frame)
        bottom_bar.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        bottom_bar.columnconfigure(0, weight=1)
        ttk.Label(
            bottom_bar,
            textvariable=self.status,
            foreground="#555555",
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(
            bottom_bar,
            text="Continue",
            command=self.show_column_selection_page,
        ).grid(row=0, column=1, sticky="e")

    def load_text_file(self):
        file_path = filedialog.askopenfilename(
            parent=self.window,
            title="Choose an object list",
            filetypes=(
                ("Text files", "*.txt"),
                ("CSV files", "*.csv"),
                ("All files", "*.*"),
            ),
        )
        if not file_path:
            return

        try:
            text = Path(file_path).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = Path(file_path).read_text(encoding="utf-8-sig")
        except OSError as error:
            messagebox.showerror(
                "File could not be loaded",
                str(error),
                parent=self.window,
            )
            return

        self.input_text.delete("1.0", "end")
        self.input_text.insert("1.0", text)
        self.input_buffer = text
        self.status.set(f"Loaded {Path(file_path).name}.")

    def parse_object_inputs(self):
        raw_text = self.input_text.get("1.0", "end")
        self.input_buffer = raw_text.rstrip("\n")
        objects = [
            line.strip()
            for line in raw_text.splitlines()
            if line.strip()
        ]
        release = self.release.get()

        if not objects:
            raise ValueError("Please enter at least one object.")
        if release != COMMON_NAME_RELEASE:
            invalid_values = [value for value in objects if not value.isdigit()]
            if invalid_values:
                raise ValueError(
                    f"{release} mode requires numeric source IDs. "
                    f"First invalid row: {invalid_values[0]}"
                )

        return objects

    def show_column_selection_page(self):
        try:
            self.object_inputs = self.parse_object_inputs()
        except ValueError as error:
            messagebox.showwarning(
                "Check bulk input",
                str(error),
                parent=self.window,
            )
            return

        self.clear_window()
        self.window.rowconfigure(0, weight=1)

        frame = ttk.Frame(self.window, padding=18)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        top_bar = ttk.Frame(frame)
        top_bar.grid(row=0, column=0, sticky="ew")
        top_bar.columnconfigure(0, weight=1)
        ttk.Label(
            top_bar,
            text=f"Choose Data Columns ({len(self.object_inputs)} objects)",
            font=("Segoe UI", 15, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(
            top_bar,
            text="Guide",
            command=self.show_guide,
        ).grid(row=0, column=2, sticky="e")

        selection_container = ttk.Frame(frame)
        selection_container.grid(row=1, column=0, sticky="nsew", pady=(14, 10))
        selection_container.columnconfigure(0, weight=1)
        selection_container.rowconfigure(0, weight=1)

        canvas = tk.Canvas(selection_container, highlightthickness=0)
        canvas.grid(row=0, column=0, sticky="nsew")

        hint = ttk.Label(
            selection_container,
            text="Check fields to include. Drag compact blocks; final order reads left to right, top to bottom.",
            foreground="#555555",
        )
        hint.grid(row=1, column=0, sticky="w", pady=(8, 0))

        self.columns_frame = ttk.Frame(canvas)
        canvas_window = canvas.create_window(
            (0, 0),
            window=self.columns_frame,
            anchor="nw",
        )
        self.columns_frame.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda event: canvas.itemconfigure(canvas_window, width=event.width),
        )
        self.render_column_blocks()

        bottom_bar = ttk.Frame(frame)
        bottom_bar.grid(row=2, column=0, sticky="ew")
        bottom_bar.columnconfigure(0, weight=1)
        ttk.Button(
            bottom_bar,
            text="Back",
            command=self.show_input_page,
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(
            bottom_bar,
            text="Select Primary Rows",
            command=self.select_primary_columns,
        ).grid(row=0, column=1, sticky="e", padx=(0, 8))
        ttk.Button(
            bottom_bar,
            text="Select All",
            command=lambda: self.set_all_columns(True),
        ).grid(row=0, column=2, sticky="e", padx=(0, 8))
        ttk.Button(
            bottom_bar,
            text="Start Bulk Query",
            command=self.start_bulk_query,
        ).grid(row=0, column=3, sticky="e")

    def set_all_columns(self, is_selected):
        for variable in self.selected_columns.values():
            variable.set(is_selected)

    def select_primary_columns(self):
        for column_name, variable in self.selected_columns.items():
            variable.set(column_name in PRIMARY_DISPLAY_ORDER)
        primary_columns = [
            column_name for column_name in PRIMARY_DISPLAY_ORDER
            if column_name in self.column_order
        ]
        secondary_columns = [
            column_name for column_name in self.column_order
            if column_name not in PRIMARY_DISPLAY_ORDER
        ]
        self.column_order = primary_columns + secondary_columns
        self.render_column_blocks()

    def render_column_blocks(self):
        for child in self.columns_frame.winfo_children():
            child.destroy()

        self.column_block_frames = []
        for column_index in range(self.COLUMN_BLOCKS_PER_ROW):
            self.columns_frame.columnconfigure(
                column_index,
                weight=1,
                minsize=190,
            )

        for index, column_name in enumerate(self.column_order):
            row_index = index // self.COLUMN_BLOCKS_PER_ROW
            grid_column = index % self.COLUMN_BLOCKS_PER_ROW
            block = tk.Frame(
                self.columns_frame,
                borderwidth=1,
                relief="solid",
                background="#f7f7f7",
                cursor="hand2",
                height=34,
            )
            block.grid(row=row_index, column=grid_column, sticky="ew", padx=3, pady=3)
            block.grid_propagate(False)
            block.columnconfigure(2, weight=1)

            handle = tk.Label(
                block,
                text="::",
                width=2,
                background="#f7f7f7",
                foreground="#666666",
                cursor="hand2",
            )
            handle.grid(row=0, column=0, sticky="nsw", padx=(5, 1), pady=4)

            ttk.Checkbutton(
                block,
                variable=self.selected_columns[column_name],
                width=0,
            ).grid(row=0, column=1, sticky="w", padx=(0, 2), pady=4)

            label = tk.Label(
                block,
                text=self.get_compact_column_label(column_name),
                anchor="w",
                background="#f7f7f7",
                cursor="hand2",
                font=("Segoe UI", 8),
            )
            label.grid(row=0, column=2, sticky="ew", padx=(0, 4), pady=4)

            for widget in (block, handle, label):
                widget.bind(
                    "<ButtonPress-1>",
                    lambda event, name=column_name: self.start_column_drag(
                        event,
                        name,
                    ),
                )
                widget.bind("<ButtonRelease-1>", self.finish_column_drag)

            self.column_block_frames.append((column_name, block))

    def get_compact_column_label(self, column_name):
        label = DISPLAY_COLUMNS[column_name]
        if len(label) <= 23:
            return label
        return f"{label[:20]}..."

    def start_column_drag(self, _event, column_name):
        self.dragged_column = column_name
        self.window.bind("<ButtonRelease-1>", self.finish_column_drag)

    def finish_column_drag(self, event):
        if not self.dragged_column:
            return

        target_index = self.get_column_drop_index(event.x_root, event.y_root)
        dragged_column = self.dragged_column
        self.dragged_column = None
        self.window.unbind("<ButtonRelease-1>")

        if dragged_column not in self.column_order:
            return

        original_index = self.column_order.index(dragged_column)
        self.column_order.remove(dragged_column)
        if target_index > original_index:
            target_index -= 1
        target_index = min(target_index, len(self.column_order))
        self.column_order.insert(target_index, dragged_column)
        self.render_column_blocks()

    def get_column_drop_index(self, pointer_x, pointer_y):
        rows = {}
        for index, (_column_name, block) in enumerate(self.column_block_frames):
            row_index = index // self.COLUMN_BLOCKS_PER_ROW
            rows.setdefault(row_index, []).append((index, block))

        for row_index in sorted(rows):
            blocks = rows[row_index]
            row_top = min(block.winfo_rooty() for _index, block in blocks)
            row_bottom = max(
                block.winfo_rooty() + block.winfo_height()
                for _index, block in blocks
            )

            if pointer_y < row_top:
                return blocks[0][0]
            if pointer_y <= row_bottom:
                for index, block in blocks:
                    midpoint = block.winfo_rootx() + (block.winfo_width() / 2)
                    if pointer_x < midpoint:
                        return index
                return blocks[-1][0] + 1

        return len(self.column_block_frames)

    def start_bulk_query(self):
        if self.query_in_progress:
            return
        self.cancel_event = threading.Event()
        self.force_refresh_snapshot = self.app.force_refresh.get()
        self.temperature_options = self.app.temperature_options
        selected = self.get_selected_columns()
        if not selected:
            messagebox.showwarning(
                "Choose data columns",
                "Please select at least one data field.",
                parent=self.window,
            )
            return

        self.result_rows = []
        self.current_page = 0
        self.query_in_progress = True
        self.bulk_completed = False
        self.show_results_page()

        worker = threading.Thread(
            target=self.run_bulk_query,
            args=(self.object_inputs, self.release.get(), selected),
            daemon=True,
        )
        worker.start()
        self.window.after(100, self.process_bulk_events)

    def show_results_page(self):
        self.clear_window()
        self.window.rowconfigure(1, weight=1)

        top_frame = ttk.Frame(self.window, padding=(18, 18, 18, 8))
        top_frame.grid(row=0, column=0, sticky="ew")
        top_frame.columnconfigure(0, weight=1)
        ttk.Label(
            top_frame,
            text="Bulk Query Results",
            font=("Segoe UI", 15, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(
            top_frame,
            text="Guide",
            command=self.show_guide,
        ).grid(row=0, column=2, sticky="e")

        progress_frame = ttk.Frame(top_frame)
        progress_frame.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        progress_frame.columnconfigure(0, weight=1)
        self.bulk_status = tk.StringVar(
            value="Preparing bulk query. This can take a long time for large lists."
        )
        ttk.Label(
            progress_frame,
            textvariable=self.bulk_status,
            foreground="#555555",
        ).grid(row=0, column=0, sticky="w")
        self.progress = ttk.Progressbar(
            progress_frame,
            maximum=max(len(self.object_inputs), 1),
            mode="determinate",
        )
        self.progress.grid(row=1, column=0, sticky="ew", pady=(6, 0))

        action_frame = ttk.Frame(top_frame)
        action_frame.grid(row=0, column=1, sticky="e", padx=(12, 8))
        ttk.Button(
            action_frame,
            text="Show Input Rows",
            command=self.show_entered_rows_window,
        ).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(
            action_frame,
            text="Save Bulk Results",
            command=self.save_bulk_results,
        ).grid(row=0, column=1)

        analysis_frame = ttk.Frame(top_frame)
        analysis_frame.grid(row=2, column=0, columnspan=3, sticky="w", pady=(10, 0))
        self.cluster_analysis_button = ttk.Button(
            analysis_frame, text="Advanced Cluster Analysis",
            command=self.open_cluster_analysis, state="disabled",
        )
        self.cluster_analysis_button.pack(side="left")
        ttk.Checkbutton(analysis_frame, text="Carbon-star candidates", variable=self.carbon_only,
                        command=self.change_rows_per_page).pack(side="left", padx=8)
        ttk.Button(analysis_frame, text="Cancel", command=self.cancel_event.set).pack(side="left")
        ttk.Label(
            analysis_frame, text="Available after a completed bulk query of at least 10 objects.",
            foreground="#555555",
        ).pack(side="left", padx=(10, 0))
        self.update_cluster_analysis_button()

        table_frame = ttk.Frame(self.window, padding=(18, 0, 18, 8))
        table_frame.grid(row=1, column=0, sticky="nsew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        self.results_table = ttk.Treeview(table_frame, show="headings", height=10)
        self.results_table.grid(row=0, column=0, sticky="nsew")
        self.results_table.bind("<Double-1>", self.copy_bulk_cell)
        self.results_table.bind("<ButtonRelease-1>", self.show_bulk_full_value)
        self.results_table.bind("<Motion>", self.preview_bulk_value)
        self.results_table.bind("<Leave>", lambda _e: self.app.hide_field_preview())
        self.results_table.bind("<Control-c>", self.copy_selected_bulk_row)
        self.results_table.bind("<Control-C>", self.copy_selected_bulk_row)
        self.cluster_warning_rows = {}
        self.cluster_warning_markers = []
        self.cluster_marker_refresh_pending = False
        for sequence in ("<Configure>", "<ButtonRelease-1>", "<<TreeviewSelect>>"):
            self.results_table.bind(sequence, self.schedule_cluster_warning_markers, add="+")
        y_scroll = ttk.Scrollbar(
            table_frame,
            orient="vertical",
            command=self.results_table.yview,
        )
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll = ttk.Scrollbar(
            table_frame,
            orient="horizontal",
            command=self.results_table.xview,
        )
        x_scroll.grid(row=1, column=0, sticky="ew")
        self.results_table.configure(
            yscrollcommand=lambda *args: self.update_bulk_scrollbar(y_scroll, *args),
            xscrollcommand=lambda *args: self.update_bulk_scrollbar(x_scroll, *args),
        )

        nav_frame = ttk.Frame(self.window, padding=(18, 0, 18, 18))
        nav_frame.grid(row=2, column=0, sticky="ew")
        nav_frame.columnconfigure(1, weight=1)
        self.prev_button = ttk.Button(
            nav_frame,
            text="Previous Page",
            command=self.previous_page,
        )
        self.prev_button.grid(row=0, column=0, sticky="w")

        page_size_frame = ttk.Frame(nav_frame)
        page_size_frame.grid(row=0, column=1)
        ttk.Label(page_size_frame, text="Rows per page").grid(
            row=0,
            column=0,
            padx=(0, 8),
        )
        for index, row_count in enumerate((10, 20, 30), start=1):
            ttk.Radiobutton(
                page_size_frame,
                text=str(row_count),
                value=row_count,
                variable=self.rows_per_page,
                command=self.change_rows_per_page,
            ).grid(row=0, column=index, padx=(0, 6))

        self.page_status = tk.StringVar(value="Page 1 of 1")
        ttk.Label(nav_frame, textvariable=self.page_status).grid(row=0, column=2)
        self.next_button = ttk.Button(
            nav_frame,
            text="Next Page",
            command=self.next_page,
        )
        self.next_button.grid(row=0, column=3, sticky="e")

        self.render_results_page()

    def get_selected_columns(self):
        return [
            column_name
            for column_name in self.column_order
            if self.selected_columns[column_name].get()
        ]

    def run_bulk_query(self, objects, release, selected_columns):
        total = len(objects)
        processed = 0
        options = network.settings()
        for batch in chunk_sequence(objects, options.batch_size):
            if self.cancel_event.is_set():
                break
            self.query_events.put(("batch", processed, total, batch[0]))
            try:
                with network.query_context(options=options, cancel=self.cancel_event,
                        force_refresh=self.force_refresh_snapshot,
                        progress=lambda msg: self.query_events.put(("status", msg))):
                    start = processed
                    for identifier in batch:
                        self.query_events.put(("row", {**dict.fromkeys(selected_columns, "-"), "_input_value": identifier}))
                    def preview(data):
                        raw = GaiaAssistApp.build_display_data(data, calculate_derived_data(data, self.temperature_options, skip_dust=True))
                        row = {key: format_display_value(key, raw.get(key)) for key in selected_columns}
                        row.update(_analysis_data=raw, _input_value=data["_requested_id"], _cluster_warning_reasons=cluster_analysis_warning_reasons(raw))
                        for offset, identifier in enumerate(batch):
                            if identifier == data["_requested_id"]:
                                self.query_events.put(("row_update", start+offset, row))
                    batch_data, batch_errors = fetch_gaia_source_data_batch(batch, release, on_basic=preview)
                    # Publish basic rows before any dust enrichment.
                    for index, object_id in enumerate(batch, start):
                        if object_id in batch_data:
                            data = batch_data[object_id]
                            raw = GaiaAssistApp.build_display_data(data, calculate_derived_data(data, self.temperature_options, skip_dust=True))
                            row = {key: format_display_value(key, raw.get(key)) for key in selected_columns}
                            row.update(_analysis_data=raw, _input_value=object_id, _cluster_warning_reasons=cluster_analysis_warning_reasons(raw))
                        else:
                            row = {key: "-" for key in selected_columns}
                            row.update(_query_failed=True, _input_value=object_id)
                            row[selected_columns[0]] = "ERROR: " + object_id
                        self.query_events.put(("row_update", index, row))
                    with ThreadPoolExecutor(max_workers=BULK_CALCULATION_WORKERS) as executor:
                        futures = {executor.submit(copy_context().run, self.build_bulk_result_row,
                            object_id, release, selected_columns, batch_data, batch_errors): (index, object_id)
                            for index, object_id in enumerate(batch, start)}
                        for future in as_completed(futures):
                            index, object_id = futures[future]
                            row, error = future.result()
                            row["_input_value"] = object_id
                            if not isinstance(error, (network.QueryCancelled, network.QueryTimeout)):
                                self.query_events.put(("row_update", index, row))
                            processed += 1
                            self.query_events.put(("progress", processed, total, object_id))
            except network.QueryCancelled:
                break
            except Exception as error:
                # The transport already retried transient errors. Do not turn one
                # failed batch into N more remote jobs.
                for offset, object_id in enumerate(batch):
                    row = {key: "-" for key in selected_columns}
                    row.update(_query_failed=True, _input_value=object_id)
                    row[selected_columns[0]] = "ERROR: " + object_id
                    self.query_events.put(("row_update", start+offset, row))
                    processed += 1
                self.query_events.put(("status", str(error)))
        self.query_events.put(("cancelled" if self.cancel_event.is_set() else "done", processed))

    def build_bulk_result_row(
        self,
        object_id,
        release,
        selected_columns,
        batch_data,
        batch_errors,
    ):
        try:
            if object_id in batch_errors:
                raise batch_errors[object_id]
            source_data = batch_data[object_id]
            log_missing_values(object_id, source_data)
            derived_data = calculate_derived_data(source_data, getattr(self, "temperature_options", None))
            display_data = GaiaAssistApp.build_display_data(
                source_data,
                derived_data,
            )
            row = {
                column_name: format_display_value(column_name, display_data.get(column_name))
                for column_name in selected_columns
            }
            # Metadata stays separate from the ID and exported/copied column values.
            row["_cluster_warning_reasons"] = cluster_analysis_warning_reasons(display_data)
            # Keep chart inputs even when these columns are not shown in the table.
            row["_analysis_data"] = dict(display_data)
            return row, None
        except Exception as error:
            LOGGER.exception(
                "Bulk query failed for release=%s object=%s",
                release,
                object_id,
            )
            row = {column_name: "-" for column_name in selected_columns}
            first_column = selected_columns[0]
            row[first_column] = f"ERROR: {object_id}"
            row["_query_failed"] = True
            return row, error

    def fetch_batch_sequentially(self, batch, release, batch_error):
        batch_data = {}
        batch_errors = {}
        for object_id in batch:
            try:
                batch_data[object_id] = fetch_gaia_source_data(object_id, release)
            except Exception as error:
                batch_errors[object_id] = error

        if not batch_data and not batch_errors:
            for object_id in batch:
                batch_errors[object_id] = batch_error

        return batch_data, batch_errors

    def process_bulk_events(self):
        if self.is_closed:
            return

        try:
            while True:
                event = self.query_events.get_nowait()
                event_type = event[0]

                if event_type == "status":
                    self.bulk_status.set(event[1])
                elif event_type == "cancelled":
                    self.query_in_progress = False
                    self.bulk_status.set("Cancelled; completed and basic rows retained.")
                elif event_type == "row_update":
                    self.result_rows[event[1]] = event[2]
                    self.render_results_page()
                elif event_type == "progress":
                    completed, total, object_id = event[1], event[2], event[3]
                    self.progress["value"] = completed
                    self.bulk_status.set(
                        f"Queried {completed} of {total}. Current object: {object_id}. "
                        "Large lists can take a long time."
                    )
                elif event_type == "batch":
                    completed, total, batch_label = event[1], event[2], event[3]
                    self.progress["value"] = completed
                    self.bulk_status.set(
                        f"Loading Gaia batch of up to {BULK_GAIA_BATCH_SIZE}: "
                        f"{batch_label}. Completed {completed} of {total}."
                    )
                elif event_type == "row":
                    self.result_rows.append(event[1])
                    self.render_results_page()
                elif event_type == "row_error":
                    self.bulk_status.set(
                        f"Problem with {event[1]}. Continuing with the next object."
                    )
                elif event_type == "done":
                    total = event[1]
                    self.query_in_progress = False
                    self.bulk_completed = True
                    self.update_cluster_analysis_button()
                    self.progress["value"] = total
                    self.bulk_status.set(
                        f"Bulk query finished. Loaded {len(self.result_rows)} rows."
                    )
        except queue.Empty:
            pass

        try:
            window_exists = self.window.winfo_exists()
        except tk.TclError:
            return

        if self.query_in_progress and window_exists:
            self.window.after(100, self.process_bulk_events)

    def update_cluster_analysis_button(self):
        enabled = self.bulk_completed and not self.query_in_progress and len(self.result_rows) >= 10
        self.cluster_analysis_button.configure(state="normal" if enabled else "disabled")

    def open_cluster_analysis(self):
        if not self.bulk_completed or self.query_in_progress or len(self.result_rows) < 10:
            return
        if self.cluster_analysis_window is not None and self.cluster_analysis_window.window.winfo_exists():
            self.cluster_analysis_window.window.deiconify()
            self.cluster_analysis_window.window.lift()
            return
        try:
            # Plotting is loaded only after the user explicitly requests analysis.
            from temperature_cluster_window import ClusterAnalysisWindow
        except ImportError as error:
            LOGGER.exception("Cluster plotting could not be loaded")
            messagebox.showerror(
                "Cluster analysis unavailable",
                "The plotting dependencies could not be loaded. Install the packages in "
                f"requirements.txt and try again.\n\n{error}",
                parent=self.window,
            )
            return
        self.cluster_analysis_window = ClusterAnalysisWindow(self.window, self.result_rows)

    def visible_result_rows(self):
        from temperature_carbon import is_carbon
        return [row for row in self.result_rows if not self.carbon_only.get() or is_carbon(row)]

    def render_results_page(self):
        visible_rows = self.visible_result_rows()
        selected_columns = self.get_selected_columns()
        self.results_table["columns"] = selected_columns
        for column_name in selected_columns:
            label = DISPLAY_COLUMNS[column_name]
            unit = FIELD_UNITS.get(column_name, "")
            heading = f"{label} ({unit})" if unit and unit != "unitless" else label
            self.results_table.heading(column_name, text=heading)
            width = self.calculate_column_width(column_name, heading)
            self.results_table.column(
                column_name,
                width=width,
                minwidth=width,
                stretch=False,
            )

        for item in self.results_table.get_children():
            self.results_table.delete(item)

        rows_per_page = self.rows_per_page.get()
        total_pages = max(
            1,
            (len(self.visible_result_rows()) + rows_per_page - 1) // rows_per_page,
        )
        self.current_page = min(self.current_page, total_pages - 1)
        start = self.current_page * rows_per_page
        end = start + rows_per_page
        self.cluster_warning_rows = {}
        self.full_bulk_rows = {}
        for row in visible_rows[start:end]:
            item = self.results_table.insert(
                "",
                "end",
                values=[compact_text(row.get(column_name, "-"), 58) for column_name in selected_columns],
            )
            self.full_bulk_rows[item] = row
            if "source_id" in selected_columns and row.get("_cluster_warning_reasons"):
                self.cluster_warning_rows[item] = row

        self.schedule_cluster_warning_markers()

        self.page_status.set(f"Page {self.current_page + 1} of {total_pages}")
        self.prev_button.configure(
            state="normal" if self.current_page > 0 else "disabled"
        )
        self.next_button.configure(
            state="normal" if self.current_page < total_pages - 1 else "disabled"
        )

    def update_bulk_scrollbar(self, scrollbar, *args):
        scrollbar.set(*args)
        self.schedule_cluster_warning_markers()

    def schedule_cluster_warning_markers(self, _event=None):
        if not self.cluster_marker_refresh_pending:
            self.cluster_marker_refresh_pending = True
            self.cluster_marker_after_id = self.results_table.after_idle(self.refresh_cluster_warning_markers)

    def refresh_cluster_warning_markers(self):
        # Treeview cannot color a substring. Overlay only the clickable asterisk,
        # retaining normal table selection, scrolling, and unmodified ID values.
        from tkinter import font as tkfont

        self.cluster_marker_refresh_pending = False
        self.cluster_marker_after_id = None
        for marker in self.cluster_warning_markers:
            marker.destroy()
        self.cluster_warning_markers = []
        if "source_id" not in self.results_table["columns"]:
            return
        style = ttk.Style(self.results_table)
        font = tkfont.Font(
            root=self.results_table,
            font=style.lookup("Treeview", "font") or "TkDefaultFont",
        )
        self.cluster_marker_font = font
        for item, row in self.cluster_warning_rows.items():
            box = self.results_table.bbox(item, "source_id")
            if not box:
                continue
            x, y, width, height = box
            marker_x = x + font.measure(str(row["source_id"])) + 6
            marker_width = font.measure("*") + 6
            if marker_x < 0 or marker_x + marker_width > min(x + width, self.results_table.winfo_width() - 2):
                continue
            selected = item in self.results_table.selection()
            background = style.lookup("Treeview", "background", ("selected",) if selected else ())
            marker = tk.Label(
                self.results_table, text="*", foreground="#0066ff",
                background=background or "white", font=font, cursor="hand2",
                padx=0, pady=0, borderwidth=0, takefocus=True,
            )
            marker.place(x=marker_x, y=y, width=marker_width, height=height)
            for sequence in ("<Button-1>", "<Return>", "<space>"):
                marker.bind(sequence, lambda _event, result=row: self.show_cluster_analysis_warning(result))
            self.cluster_warning_markers.append(marker)

    def show_cluster_analysis_warning(self, row):
        messagebox.showwarning(
            "Star cluster analysis warning",
            f"Gaia source {row['source_id']} has potentially unreliable measurements:\n\n"
            + "\n".join(row["_cluster_warning_reasons"])
            + "\n\nIf you are conducting a star cluster analysis, consider excluding "
            "this star from your sample after reviewing these measurements.",
            parent=self.window,
        )
        return "break"

    def calculate_column_width(self, column_name, heading):
        values = [heading]
        values.extend(row.get(column_name, "-") for row in self.result_rows)
        longest_value = max(values, key=lambda value: len(str(value)))
        return min(max(len(str(longest_value)) * 8 + 36, 150), 520)

    def change_rows_per_page(self):
        self.current_page = 0
        self.render_results_page()

    def previous_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self.render_results_page()

    def next_page(self):
        rows_per_page = self.rows_per_page.get()
        total_pages = max(
            1,
            (len(self.visible_result_rows()) + rows_per_page - 1) // rows_per_page,
        )
        if self.current_page < total_pages - 1:
            self.current_page += 1
            self.render_results_page()

    def show_bulk_full_value(self, event):
        if self.app.field_name_mode.get() != "Explain":
            return
        row_id = self.results_table.identify_row(event.y)
        col = self.results_table.identify_column(event.x)
        columns = self.get_selected_columns()
        if not row_id or not col:
            return
        index = int(col[1:])-1
        if 0 <= index < len(columns):
            value = str(self.full_bulk_rows.get(row_id, {}).get(columns[index], "-"))
            if compact_text(value, 58) != value:
                self.app.show_full_value(value)

    def preview_bulk_value(self, event):
        if self.app.field_name_mode.get() != "Copy":
            return
        row_id = self.results_table.identify_row(event.y)
        col = self.results_table.identify_column(event.x)
        columns = self.get_selected_columns()
        if not row_id or not col:
            self.app.hide_field_preview()
            return
        index = int(col[1:])-1
        if 0 <= index < len(columns):
            value = str(self.full_bulk_rows.get(row_id, {}).get(columns[index], "-"))
            if compact_text(value, 58) != value:
                self.app.show_value_preview(event, value)
            else:
                self.app.hide_field_preview()

    def copy_bulk_cell(self, event):
        row_id = self.results_table.identify_row(event.y)
        column_id = self.results_table.identify_column(event.x)
        if not row_id or not column_id:
            return

        column_index = int(column_id.lstrip("#")) - 1
        values = self.results_table.item(row_id, "values")
        if column_index < 0 or column_index >= len(values):
            return

        key = self.get_selected_columns()[column_index]
        value = str(self.full_bulk_rows.get(row_id, {}).get(key, values[column_index]))
        self.window.clipboard_clear()
        self.window.clipboard_append(value)
        self.bulk_status.set(f"Copied: {value}")

    def copy_selected_bulk_row(self, _event=None):
        selected_items = self.results_table.selection()
        if not selected_items:
            return

        selected_columns = self.get_selected_columns()
        copied_rows = []
        for item in selected_items:
            values = [str(self.full_bulk_rows[item].get(key, "-")) for key in selected_columns]
            copied_rows.append(
                "\t".join(
                    str(values[index])
                    for index in range(min(len(values), len(selected_columns)))
                )
            )

        copied_text = "\n".join(copied_rows)
        self.window.clipboard_clear()
        self.window.clipboard_append(copied_text)
        self.bulk_status.set("Copied selected row data.")
        return "break"

    def show_entered_rows_window(self):
        rows_window = tk.Toplevel(self.window)
        rows_window.title("Bulk Query Input Rows")
        rows_window.geometry("560x460")
        rows_window.transient(self.window)

        rows_window.columnconfigure(0, weight=1)
        rows_window.rowconfigure(0, weight=1)

        text = tk.Text(
            rows_window,
            wrap="none",
            font=("Consolas", 10),
            padx=10,
            pady=10,
        )
        text.grid(row=0, column=0, sticky="nsew")
        y_scroll = ttk.Scrollbar(rows_window, orient="vertical", command=text.yview)
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll = ttk.Scrollbar(rows_window, orient="horizontal", command=text.xview)
        x_scroll.grid(row=1, column=0, sticky="ew")
        text.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        text.insert("1.0", "\n".join(self.object_inputs))

    def save_bulk_results(self):
        if not self.result_rows:
            messagebox.showwarning(
                "Nothing to save",
                "Please run a bulk query before saving.",
                parent=self.window,
            )
            return

        try:
            saved_file = self.write_bulk_results_file()
        except OSError as error:
            LOGGER.exception("Saving bulk results failed")
            messagebox.showerror(
                "Save failed",
                f"The bulk data could not be saved.\n\n{error}",
                parent=self.window,
            )
            return

        messagebox.showinfo(
            "Successfully saved",
            f"Bulk data saved successfully to:\n{saved_file}",
            parent=self.window,
        )

    def write_bulk_results_file(self):
        SAVED_OBJECTS_DIR.mkdir(exist_ok=True)
        timestamp = datetime.now()
        saved_file = SAVED_OBJECTS_DIR / (
            f"gaia_bulk_{timestamp:%Y%m%d_%H%M%S_%f}.txt"
        )
        from temperature_storage import REQUIRED_EXPORT_FIELDS, save_csv
        selected_columns = list(dict.fromkeys([*self.get_selected_columns(), *REQUIRED_EXPORT_FIELDS]))

        with saved_file.open("w", encoding="utf-8") as output_file:
            output_file.write("Gaia Assist Bulk Query Data\n")
            output_file.write(
                f"Saved At: {timestamp.isoformat(timespec='seconds')}\n"
            )
            output_file.write(f"Input Mode: {self.release.get()}\n")
            output_file.write(f"Input Count: {len(self.object_inputs)}\n")
            output_file.write(f"Result Count: {len(self.result_rows)}\n")
            output_file.write("\n")
            headers = ["Input Row"] + [
                DISPLAY_COLUMNS[column_name] for column_name in selected_columns
            ]
            units = ["-"] + [
                FIELD_UNITS.get(column_name, "-") or "-"
                for column_name in selected_columns
            ]
            output_file.write("\t".join(headers) + "\n")
            output_file.write("\t".join(units) + "\n")

            for index, row in enumerate(self.result_rows):
                input_value = (
                    self.object_inputs[index]
                    if index < len(self.object_inputs)
                    else "-"
                )
                values = [input_value]
                values.extend(format_export_value(row.get("_analysis_data", row).get(column_name)) for column_name in selected_columns)
                output_file.write("\t".join(values) + "\n")

        from temperature_storage import save_records
        save_records(saved_file.with_suffix(".json"), self.result_rows)
        save_csv(saved_file.with_suffix(".csv"), self.result_rows, DISPLAY_COLUMNS)
        return saved_file

    def show_guide(self):
        self.app.show_centered_message_window(
            "Bulk Query Guide",
            BULK_QUERY_GUIDE,
            window_width=600,
            window_height=560,
        )


def fetch_sesame_response(common_name):
    with network.timed("name resolution"):
        return network.bounded("aux", ("scientist_aux", "sesame", (common_name,)),
            limit=network.settings().optional_timeout)


def parse_sesame_response(response_text):
    for release in ("DR3", "DR2", "DR1"):
        identifier_match = re.search(
            rf"Gaia\s+{release}\s+(\d+)",
            response_text,
            re.IGNORECASE,
        )
        if identifier_match is not None:
            return {
                "release": release,
                "source_id": identifier_match.group(1),
            }

    ra_match = re.search(
        r"<jradeg>\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*</jradeg>",
        response_text,
        re.IGNORECASE,
    )
    dec_match = re.search(
        r"<jdedeg>\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*</jdedeg>",
        response_text,
        re.IGNORECASE,
    )
    if ra_match is None or dec_match is None:
        return None

    return {
        "ra": float(ra_match.group(1)),
        "dec": float(dec_match.group(1)),
    }


def resolve_nearest_dr3_source_id(ra, dec):
    search_radius_degrees = 30 / 3600
    dec_lower = max(-90, dec - search_radius_degrees)
    dec_upper = min(90, dec + search_radius_degrees)
    ra_window = search_radius_degrees / max(cos(radians(dec)), 0.01)
    ra_lower = (ra - ra_window) % 360
    ra_upper = (ra + ra_window) % 360
    if ra_lower <= ra_upper:
        ra_filter = f"ra BETWEEN {ra_lower} AND {ra_upper}"
    else:
        ra_filter = f"(ra >= {ra_lower} OR ra <= {ra_upper})"

    query = f"""
        SELECT TOP 1
            source_id,
            DISTANCE(
                POINT('ICRS', ra, dec),
                POINT('ICRS', {ra}, {dec})
            ) AS match_distance
        FROM gaiadr3.gaia_source
        WHERE 1 = CONTAINS(
            POINT('ICRS', ra, dec),
            CIRCLE('ICRS', {ra}, {dec}, {search_radius_degrees})
        )
        AND dec BETWEEN {dec_lower} AND {dec_upper}
        AND {ra_filter}
        ORDER BY match_distance ASC
    """

    def launch_position_query():
        return network.tap_query(query)

    service = "ESA Gaia common-name position match"
    results = run_with_retries(launch_position_query, service, attempts=2)
    if len(results) == 0:
        raise QueryServiceError(
            service,
            "No Gaia DR3 source was found within 30 arcseconds of the resolved name.",
        )

    return str(_clean_value(results[0]["source_id"]))


def resolve_common_name_to_dr3_source_id(common_name):
    service = "CDS Sesame name resolver"
    response_text = run_with_retries(
        lambda: fetch_sesame_response(common_name),
        service,
        attempts=2,
    )
    resolved = parse_sesame_response(response_text)
    if resolved is None:
        raise QueryServiceError(
            service,
            f'No SIMBAD/Sesame object was found for common name "{common_name}".',
        )

    if "source_id" in resolved:
        LOGGER.info(
            "Sesame resolved %s to Gaia %s source %s",
            common_name,
            resolved["release"],
            resolved["source_id"],
        )
        return resolve_dr3_source_id(
            resolved["source_id"],
            resolved["release"],
        )

    LOGGER.info(
        "Sesame resolved %s to coordinates ra=%s dec=%s",
        common_name,
        resolved["ra"],
        resolved["dec"],
    )
    return resolve_nearest_dr3_source_id(resolved["ra"], resolved["dec"])

def resolve_dr3_source_id(source_id, release):
    if release == COMMON_NAME_RELEASE:
        return resolve_common_name_to_dr3_source_id(source_id)

    release = release.upper()
    if release == "DR3":
        return source_id

    if release == "DR2":
        query = f"""
            SELECT TOP 1
                dr3_source_id
            FROM gaiadr3.dr2_neighbourhood
            WHERE dr2_source_id = {source_id}
            ORDER BY angular_distance ASC
        """
    elif release == "DR1":
        query = f"""
            SELECT TOP 1
                d3.dr3_source_id
            FROM gaiadr2.dr1_neighbourhood AS d1
            INNER JOIN gaiadr3.dr2_neighbourhood AS d3
                ON d1.dr2_source_id = d3.dr2_source_id
            WHERE d1.dr1_source_id = {source_id}
            ORDER BY d1.rank ASC, d3.angular_distance ASC
        """
    else:
        raise ValueError(f"Unsupported Gaia release: {release}")

    def launch_crossmatch_query():
        return network.tap_query(query)

    service = f"ESA Gaia {release}-to-DR3 crossmatch"
    results = run_with_retries(launch_crossmatch_query, service, attempts=2)
    if len(results) == 0:
        raise QueryServiceError(
            service,
            f"No Gaia DR3 counterpart found for {release} source {source_id}.",
        )

    dr3_source_id = _clean_value(results[0]["dr3_source_id"])
    if dr3_source_id is None:
        raise QueryServiceError(
            service,
            f"The Gaia DR3 counterpart for {release} source {source_id} is null.",
        )

    LOGGER.info(
        "Resolved %s source %s to DR3 source %s",
        release,
        source_id,
        dr3_source_id,
    )
    return str(dr3_source_id)


def chunk_sequence(values, size):
    for start in range(0, len(values), size):
        yield values[start:start + size]


def default_astrophysical_row():
    return {
        "classprob_dsc_combmod_quasar": None,
        "classprob_dsc_combmod_galaxy": None,
        "classprob_dsc_combmod_star": None,
        "mh_gspphot": None,
        **dict.fromkeys(AP_FIELDS),
    }


def astrophysical_query_status(has_row, error=None):
    if error is not None:
        return {"gaia_ap_status": "query_failed", "gaia_ap_message": "Gaia parameter request failed; retry the query. " + error}
    if not has_row:
        return {"gaia_ap_status": "no_row", "gaia_ap_message": "Query succeeded; no astrophysical-parameter row for this Gaia source."}
    return {"gaia_ap_status": "retrieved", "gaia_ap_message": "Query succeeded; blank catalogue fields were returned as missing values."}


def fetch_gaia_source_data_batch(source_ids, release="DR3", on_basic=None):
    import scientist_catalogue
    if network.CURRENT.get() is None:
        with network.query_context():
            return fetch_gaia_source_data_batch(source_ids, release, on_basic)
    pairs, errors = [], {}
    for identifier in dict.fromkeys(source_ids):
        try:
            with network.timed("name / release resolution"):
                resolved = network.cached("resolution", [release, identifier],
                    lambda: resolve_dr3_source_id(identifier, release))
            pairs.append((identifier, str(resolved)))
        except network.QueryCancelled:
            raise
        except Exception as error:
            errors[identifier] = error
    if not pairs:
        return {}, errors
    def preview(record):
        if on_basic:
            for original, resolved in pairs:
                if resolved == record["source_id"]:
                    on_basic({**record, "_requested_id": original})
    records, failures = scientist_catalogue.fetch([r for _, r in pairs], release, preview if on_basic else None)
    # Publish the baseline before bounded optional distance enrichment, even
    # when Gaia source and AP data were both satisfied from cache.
    import scientist_distance
    context = network.CURRENT.get()
    for record in records.values():
        if context and context.cancel.is_set():
            raise network.QueryCancelled("Query cancelled")
        preview(record)
    distance_records = scientist_distance.fetch(records.keys())
    if context and context.cancel.is_set():
        raise network.QueryCancelled("Query cancelled")
    for identifier, record in records.items():
        record.update(distance_records[identifier])
    results = {}
    for original, resolved in pairs:
        if resolved in records:
            results[original] = records[resolved]
        else:
            errors[original] = failures[resolved]
    return results, errors


def fetch_gaia_source_data(source_id, release="DR3", on_basic=None):
    records, errors = fetch_gaia_source_data_batch([source_id], release, on_basic)
    if source_id in errors:
        raise errors[source_id]
    return records[source_id]


def build_source_data_from_gaia_rows(row, astrophysical_row):
    def optional(record, key):
        try:
            return _clean_value(record[key])
        except (KeyError, IndexError):
            return None
    queried_source_id = _clean_value(row["source_id"])
    if isinstance(queried_source_id, float):
        raise ValueError("Gaia source_id must be an integer or exact digit string, never float")
    queried_source_id = None if queried_source_id is None else str(queried_source_id)
    object_type = format_object_type_probability(astrophysical_row)
    metallicity = _clean_value(astrophysical_row["mh_gspphot"])
    equatorial_coordinate_ra = _clean_value(row["ra"])
    equatorial_coordinate_dec = _clean_value(row["dec"])
    galactic_coordinate_l = _clean_value(row["l"])
    galactic_coordinate_b = _clean_value(row["b"])
    ra_proper_motion = _clean_value(row["pmra"])
    dec_proper_motion = _clean_value(row["pmdec"])
    ra_error = _clean_value(row["ra_error"])
    dec_error = _clean_value(row["dec_error"])
    parallax = _clean_value(row["parallax"])
    parallax_over_error = _clean_value(row["parallax_over_error"])
    excess_noise = _clean_value(row["astrometric_excess_noise"])
    excess_noise_sig = _clean_value(row["astrometric_excess_noise_sig"])
    ruwe = _clean_value(row["ruwe"])
    bp_rp_excess_flux = _clean_value(row["phot_bp_rp_excess_factor"])
    radial_velocity = _clean_value(row["radial_velocity"])
    radial_velocity_error = _clean_value(row["radial_velocity_error"])
    mean_g = _clean_value(row["phot_g_mean_mag"])
    mean_bp_rp = _clean_value(row["bp_rp"])

    return {
        "source_id": queried_source_id,
        "object_type": object_type,
        "metallicity": metallicity,
        "ra": equatorial_coordinate_ra,
        "dec": equatorial_coordinate_dec,
        "l": galactic_coordinate_l,
        "b": galactic_coordinate_b,
        "pmra": ra_proper_motion,
        "pmdec": dec_proper_motion,
        "ra_error": ra_error,
        "dec_error": dec_error,
        "parallax": parallax,
        "parallax_over_error": parallax_over_error,
        "astrometric_excess_noise": excess_noise,
        "astrometric_excess_noise_sig": excess_noise_sig,
        "ruwe": ruwe,
        "phot_bp_rp_excess_factor": bp_rp_excess_flux,
        "radial_velocity": radial_velocity,
        "radial_velocity_error": radial_velocity_error,
        "phot_g_mean_mag": mean_g,
        "bp_rp": mean_bp_rp,
        **{key: optional(row, key) for key in PHOTOMETRY_FIELDS},
        **{key: optional(astrophysical_row, key) for key in AP_FIELDS},
    }


def format_object_type_probability(row):
    probabilities = {
        "Quasar": _clean_value(row["classprob_dsc_combmod_quasar"]),
        "Galaxy": _clean_value(row["classprob_dsc_combmod_galaxy"]),
        "Star": _clean_value(row["classprob_dsc_combmod_star"]),
    }
    available_probabilities = {
        object_type: probability
        for object_type, probability in probabilities.items()
        if probability is not None
    }

    if not available_probabilities:
        return None

    best_object_type, best_probability = max(
        available_probabilities.items(),
        key=lambda item: item[1],
    )
    return f"{best_object_type} with {best_probability * 100:.2f}% probability"


def log_missing_values(source_id, source_data):
    missing_labels = [
        GAIA_COLUMNS[column_name]
        for column_name, value in source_data.items()
        if value is None
    ]

    timestamp = datetime.now().isoformat(timespec="seconds")
    if missing_labels:
        missing_text = ", ".join(missing_labels)
    else:
        missing_text = "None"

    with MISSING_VALUES_LOG.open("a", encoding="utf-8") as log_file:
        log_file.write(
            f"{timestamp} | source_id={source_id} | missing_values={missing_text}\n"
        )


def collect_pipeline_warnings(source_data, derived_data):
    warnings = []
    adopted_distance = number(derived_data.get("adopted_distance_pc"))
    dust_query_expected = (
        adopted_distance is not None
        and adopted_distance > 0
        and source_data.get("l") is not None
        and source_data.get("b") is not None
    )

    if dust_query_expected and derived_data.get("extinction_source") == "unavailable":
        warnings.append("Extinction unavailable")
    if derived_data.get("temperature_status") in ("needs_review", "unavailable"):
        warnings.append("Temperature " + derived_data["temperature_status"])

    return warnings


def calculate_first_step(source_data):
    equatorial_coordinate_ra = source_data["ra"]
    equatorial_coordinate_dec = source_data["dec"]

    if equatorial_coordinate_ra is None or equatorial_coordinate_dec is None:
        return {
            "ra_hms_dec": None,
            "constellation": None,
        }

    hour_variable, minutes_variable, seconds_variable = convert_ra_to_hms(
        equatorial_coordinate_ra
    )
    constellation = find_constellation(
        equatorial_coordinate_ra,
        equatorial_coordinate_dec,
    )

    return {
        "ra_hms_dec": (
            f"{hour_variable}h {minutes_variable}m "
            f"{seconds_variable:.2f}s, DEC {equatorial_coordinate_dec:.2f}"
        ),
        "constellation": constellation,
    }


def calculate_derived_data(source_data, options=None, *, skip_dust=False):
    options = options or TemperatureOptions()
    # Old saved records and sources lacking AP data remain usable.
    source_data = {**dict.fromkeys(GAIA_COLUMNS), **source_data}
    derived_data = {**dict.fromkeys(DERIVED_COLUMNS),
        **calculate_first_step(source_data),
        **calculate_error_check(source_data),
        **calculate_ruwe_check(source_data),
    }

    parallax_check = calculate_parallax_check(source_data)
    derived_data.update(parallax_check)

    distance_result = evaluate_distance(source_data, options)
    derived_data.update(distance_result)
    # Compatibility aliases are written only on explicit new calculations.
    # Every downstream calculation reads the explicit adopted distance.
    distance_data = {"adopted_distance_pc": distance_result["adopted_distance_pc"],
                     "distance_parsecs": distance_result["adopted_distance_pc"],
                     "distance_lightyears": distance_result["adopted_distance_ly"]}
    derived_data.update(distance_data)
    # Choose one reddening solution. Never silently substitute zero or correct twice.
    reddening = number(source_data.get("ebpminrp_gspphot"))
    ag = number(source_data.get("ag_gspphot"))
    e_errors = None
    if options.zero_reddening:
        dust_data = {"ebv": None, "mean_g_band_extinction": 0., "bp_rp_reddening": 0.,
                     "extinction_source": "Explicit zero-reddening assumption", "extinction_status": "provisional"}
    elif reddening is not None and reddening >= 0:
        e_errors = bounds(reddening, source_data.get("ebpminrp_gspphot_lower"), source_data.get("ebpminrp_gspphot_upper"))
        ag_errors = bounds(ag, source_data.get("ag_gspphot_lower"), source_data.get("ag_gspphot_upper"))
        valid_e = e_errors is not None and source_data["ebpminrp_gspphot_lower"] >= 0
        dust_data = {"ebv": None, "mean_g_band_extinction": ag if ag is not None and ag >= 0 else None,
                     "bp_rp_reddening": reddening, "extinction_source": "Gaia GSP-Phot",
                     "extinction_status": "usable" if valid_e else "uncertain bounds"}
    else:
        dust_data = ({"ebv": None, "mean_g_band_extinction": None, "bp_rp_reddening": None}
                     if skip_dust else calculate_dust_extinction(source_data, distance_data))
        dust_data.update(extinction_source="NADC dust map (fixed coefficients)" if dust_data["ebv"] is not None else "unavailable",
                         extinction_status="uncertain (map errors unavailable)" if dust_data["ebv"] is not None else "unavailable")
    derived_data.update(dust_data)
    new_bp_rp_data = calculate_new_bp_rp(source_data, dust_data)
    derived_data.update(new_bp_rp_data)
    absolute_magnitude_data = calculate_absolute_magnitude(
        source_data, distance_data, dust_data
    )
    derived_data.update(absolute_magnitude_data)
    visual_absolute_magnitude_data = calculate_visual_absolute_magnitude(
        new_bp_rp_data,
        absolute_magnitude_data,
    )
    derived_data.update(visual_absolute_magnitude_data)
    c = number(new_bp_rp_data["new_bp_rp"])
    # ESA DR3 Table 5.9 gives estimated V. A conservative application subset
    # avoids treating far-red transformations as strong population evidence.
    v_usable = c is not None and .2 <= c <= 2.5
    derived_data["visual_magnitude_status"] = "estimated Johnson V; ESA DR3 Table 5.9 (~0.030 mag fit scatter)" if v_usable else "uncertain V transformation outside conservative 0.2–2.5 colour interval"
    bp_err = magnitude_error(source_data.get("phot_bp_mean_flux_over_error"))
    rp_err = magnitude_error(source_data.get("phot_rp_mean_flux_over_error"))
    colour_errors = None
    if bp_err is not None and rp_err is not None and e_errors is not None:
        # C = observed colour - E: reddening's upper error gives C's lower error.
        colour_errors = tuple(sqrt(bp_err**2 + rp_err**2 + error**2) for error in reversed(e_errors))
    cmd_reliable = bool(distance_result["_distance_cmd_usable"] and v_usable and dust_data["extinction_status"] == "usable"
                        and ag is not None and ag >= 0 and bounds(ag, source_data.get("ag_gspphot_lower"), source_data.get("ag_gspphot_upper")))
    with network.timed("temperature calculation"):
        temperature_data = evaluate_temperatures(source_data, {
            **derived_data, "colour_errors": colour_errors, "cmd_reliable": cmd_reliable,
        }, options)
    derived_data.update(temperature_data)
    luminosity_data = calculate_luminosity(absolute_magnitude_data)
    derived_data.update(luminosity_data)
    from temperature_comparison import calculate_local_comparisons
    import sys
    derived_data.update(calculate_local_comparisons(source_data, derived_data, sys.modules[__name__]))
    derived_data.update(calculate_peak_wavelength(temperature_data))
    derived_data.update(
        calculate_star_type(
            source_data,
            temperature_data,
            visual_absolute_magnitude_data,
        )
    )
    if derived_data["star_type"] is None or derived_data["star_type"] == "N/A":
        derived_data["classification_status"] = "unclassified"
    elif temperature_data["bp_rp_temperature_approximate"] and temperature_data["adopted_temperature_source"] == "BP-RP":
        derived_data["classification_status"] = "approximate; tentative, not a secure subtype census"
    elif temperature_data["temperature_status"] in ("needs_review", "conditional") or not cmd_reliable:
        derived_data["classification_status"] = "tentative; needs_review"
    else:
        derived_data["classification_status"] = "estimated (not spectroscopic)"
    derived_data.update(
        calculate_visual_apparent_magnitude(
            source_data,
            new_bp_rp_data,
            dust_data,
        )
    )
    derived_data.update(calculate_excess_noise_check(source_data))

    from temperature_carbon import annotate_classification
    annotate_classification(source_data, derived_data)
    derived_data.update(baseline_diagnostics(source_data, derived_data))
    derived_data.pop("_distance_cmd_usable", None)
    return derived_data


HR_DIAGRAM_RULES = (
    ("WR", "50000+", {"VI": "-4 - 8", "I": "-4-", "WD": "8+"}),
    ("O2", "48000 - 51000", {"VI": "0 - 5", "V": "-6 - -1", "IV": "-6.5 - -5.5", "III": "-7 - -5.5", "II": "-7.5 - -6.5", "I": "-7-", "WD": "9.5+", "N/A": "5 - 9.5 & -1 - 1"}),
    ("O3", "44000 - 48000", {"VI": "0 - 5", "V": "-5.5 - -0.5", "IV": "-6.5 - -5", "III": "-7 - -5.5", "II": "-7.5 - -6.5", "I": "-7-", "WD": "9.5+", "N/A": "5 - 9.5 & -1 - 1"}),
    ("O4", "40000 - 44000", {"VI": "0 - 5.5", "V": "-5.5 - -0.5", "IV": "-6.5 - -5", "III": "-7 - -5.5", "II": "-7.5 - -6.5", "I": "-7-", "WD": "9.5+", "N/A": "5 - 9.5 & -1 - 1"}),
    ("O5", "38500 - 40000", {"VI": "0.5", "V": "-5 - 0", "IV": "-6 - -4.5", "III": "-7 - -5.5", "II": "-7.5 - -6.5", "I": "-7-", "WD": "9.5+", "N/A": "5 - 9.5 & -1 - 1"}),
    ("O6", "37000 - 39000", {"VI": "0.5 - 5.5", "V": "-5 - 0", "IV": "-6 - -4.5", "III": "-6.5 - -5.5", "II": "-7 - -6", "I": "-6.9-", "WD": "9.5+", "N/A": "5 - 9.5 & -1 - 1"}),
    ("O7", "34000 - 37000", {"VI": "0.5 - 6", "V": "-4.5 - 0", "IV": "-5.5 - -4", "III": "-6.5 - -5", "II": "-7 - -6", "I": "-6.9-", "WD": "9.5+", "N/A": "5 - 9.5 & -1 - 1"}),
    ("O8", "32000 - 34000", {"VI": "0.5 - 6", "V": "-4.5 - 0", "IV": "-5.5 - -4", "III": "-6.5 - -5", "II": "-7 - -6", "I": "-6.9-", "WD": "9.5+", "N/A": "5 - 9.5 & -1 - 1"}),
    ("O9", "30000 - 33000", {"VI": "0.5. - 6", "V": "-4.5 - 0", "IV": "-5.5 - -4", "III": "-6 - -4.5", "II": "-7 - -5.5", "I": "-6.5-", "WD": "9.5+", "N/A": "5 - 9.5 & -1 - 1"}),
    ("B0", "26000 - 31000", {"VI": "1 - 6.5", "V": "-4 - 0.5", "IV": "-5 - -3", "III": "-6 - -4", "II": "-7 - -5.5", "I": "-6-", "WD": "10+", "N/A": "6.5 - 10 & -1 - 1"}),
    ("B1", "21000 - 26000", {"VI": "1 - 6.5", "V": "-3.5 - 1", "IV": "-4 - -3", "III": "-5.5 - -3.5", "II": "-6.5 - -5", "I": "-6-", "WD": "10+", "N/A": "6.5 - 10"}),
    ("B2", "19000 - 21000", {"VI": "1 - 6.5", "V": "-3 - 1", "IV": "-3.5 - -2.5", "III": "-5 - -3", "II": "-6 - -4.5", "I": "-6-", "WD": "10+", "N/A": "6.5 - 10"}),
    ("B3", "17200 - 19000", {"VI": "1.5 - 6.5", "V": "-2.5 - 1.5", "IV": "-3 - -2", "III": "-4.5 - -2.5", "II": "-6 - -4", "I": "-6-", "WD": "10+", "N/A": "6.5 - 10"}),
    ("B4", "16000 - 17300", {"VI": "1.5 - 6.5", "V": "-2 - 1.5", "IV": "-2.5 - -1.5", "III": "-4 - -2", "II": "-6 - -3.5", "I": "-6-", "WD": "10+", "N/A": "6.5 - 10"}),
    ("B5", "14800 - 16000", {"VI": "2 - 6.5", "V": "-1.5 - 2", "IV": "-2.5 - -1", "III": "-4 - -2", "II": "-6 - -3", "I": "-6-", "WD": "10+", "N/A": "6.5 - 10"}),
    ("B6", "13800 - 15000", {"VI": "2 - 6.5", "V": "-1 - 2", "IV": "-2 - -0.5", "III": "-3.5 - -1.5", "II": "-5.5 - -3", "I": "-5.5-", "WD": "10+", "N/A": "6.5 - 10"}),
    ("B7", "12100 - 14000", {"VI": "2 - 6.5", "V": "-0.5 - 2", "IV": "-1.5 - 0", "III": "-3 - -1", "II": "-5.5 - -2.5", "I": "-5.5-", "WD": "10+", "N/A": "6.5 - 10"}),
    ("B8", "11000 - 12300", {"VI": "2 - 6.5", "V": "-0.5 - 2.5", "IV": "-1.5 - 0", "III": "-3 - -1", "II": "-5.5 - -2.5", "I": "-5.5-", "WD": "10+", "N/A": "6.5 - 10"}),
    ("B9", "10600 - 11300", {"VI": "2 - 6.5", "V": "0 - 2.5", "IV": "-1 - 0", "III": "-3 - -0.5", "II": "-5 - -2.5", "I": "-5-", "WD": "10+", "N/A": "6.5 - 10"}),
    ("A0", "9250 - 10800", {"VI": "3 - 11", "V": "0.4 - 3", "IV": "-0.5 - 0.5", "III": "-2.5 - -0.5", "II": "-5 - -2.5", "I": "-5-", "WD": "10+"}),
    ("A1", "8900 - 9400", {"VI": "3 - 11", "V": "0.5 - 3", "IV": "-0.5 - 0.5", "III": "-2.5 - -0.5", "II": "-5 - -2.5", "I": "-5-", "WD": "10+"}),
    ("A2", "8500 - 9000", {"VI": "3.5 - 11", "V": "0.5 - 3.5", "IV": "-0.5 - 1", "III": "-2 - -0.5", "II": "-5 - -2", "I": "-5-", "WD": "10+"}),
    ("A3", "8300 - 8600", {"VI": "3.5 - 11", "V": "0.5 - 3.5", "IV": "-0.5 - 1", "III": "-2 - -0.5", "II": "-5 - -2", "I": "-5-", "WD": "10+"}),
    ("A4", "8100 - 8350", {"VI": "3.5 - 11", "V": "1 - 3.5", "IV": "0 - 1.5", "III": "-1.5 - 0", "II": "-4.5 - -1.5", "I": "-4.5-", "WD": "10+"}),
    ("A5", "8000 - 8200", {"VI": "3.5 - 11", "V": "1 - 3.5", "IV": "0 - 1.5", "III": "-1.5 - 0", "II": "-4.5 - -1.5", "I": "-4.5-", "WD": "10+"}),
    ("A6", "7900 - 8050", {"VI": "3.5 - 11", "V": "1.5 - 3.5", "IV": "0 - 2", "III": "-1.5 - 0", "II": "-4.5 - -1.5", "I": "-4.5-", "WD": "10+"}),
    ("A7", "7700 - 8000", {"VI": "3.5 - 11", "V": "1.5 - 3.5", "IV": "0 - 2", "III": "-1.5 - 0", "II": "-4.5 - -1.5", "I": "-4.5-", "WD": "10+"}),
    ("A8", "7500 - 7750", {"VI": "3.5 - 11", "V": "1.5 - 4", "IV": "0 - 2", "III": "-1.5 - 0.5", "II": "-4.5 - -1.5", "I": "-4-", "WD": "10+"}),
    ("A9", "7400 - 7600", {"VI": "3.5 - 11", "V": "1.5 - 4", "IV": "0 - 2.5", "III": "-1.5 - -0.5", "II": "-4.5 - -1.5", "I": "-4-", "WD": "10+"}),
    ("F0", "7200 - 7500", {"VI": "5.5 - 13", "V": "2 - 6", "IV": "0 - 2.5", "III": "-1.5 - 1", "II": "-4 - -1.5", "I": "-3.5-", "WD": "10+"}),
    ("F1", "7000 - 7200", {"VI": "5.5 - 13", "V": "2 - 6", "IV": "0 - 2.5", "III": "-1.5 - 1", "II": "-4 - -1.5", "I": "-3.5-", "WD": "10+"}),
    ("F2", "6850 - 7000", {"VI": "5.5 - 13", "V": "2.5 - 6", "IV": "0.5 - 3", "III": "-1 - 1", "II": "-4 - -1", "I": "-3.5-", "WD": "10+"}),
    ("F3", "6650 - 6900", {"VI": "5.5 - 13", "V": "2.8 - 6", "IV": "0.5 - 3", "III": "-1 - 1", "II": "-4 - -1", "I": "-3.5-", "WD": "10+"}),
    ("F4", "6500 - 6700", {"VI": "5.5 - 13", "V": "2.8 - 6", "IV": "0.5 - 3", "III": "-1 - 1", "II": "-4 - -1", "I": "-3.5-", "WD": "10+"}),
    ("F5", "6300 - 6550", {"VI": "5.5 - 13", "V": "2.8 - 6", "IV": "1 - 3", "III": "-1 - 1.3", "II": "-4 - -1", "I": "-3.5-", "WD": "10+"}),
    ("F6", "6200 - 6400", {"VI": "6 - 13", "V": "3 - 6", "IV": "1 - 3.5", "III": "-1 - 1.3", "II": "-4 - -1", "I": "-3.5-", "WD": "10+"}),
    ("F7", "6100 - 6300", {"VI": "6 - 13", "V": "3 - 6", "IV": "1 - 3.5", "III": "-1 - 1.3", "II": "-4 - -1", "I": "-3.5-", "WD": "10+"}),
    ("F8", "6000 - 6250", {"VI": "6 - 13", "V": "3 - 6", "IV": "1 -3.5", "III": "-1 - 1.3", "II": "-4 - -1", "I": "-3.5-", "WD": "10+"}),
    ("F9", "5950 - 6150", {"VI": "6.5 - 13", "V": "3.5 - 6.5", "IV": "1.5 - 3.8", "III": "-1 - 1.5", "II": "-4 - -1", "I": "-3.5-", "WD": "10+"}),
    ("G0", "5900 - 6100", {"VI": "6.5 - 13", "V": "3.5 - 6.7", "IV": "1.5 - 3.8", "III": "-2 - 1.5", "II": "-4 - -2", "I": "-3.5-", "WD": "10+"}),
    ("G1", "5800 - 6000", {"VI": "6.6 - 13.5", "V": "3.8 - 7", "IV": "1.5 - 4", "III": "-2 - 1.5", "II": "-4 - -2", "I": "-3.5-", "WD": "10+"}),
    ("G2", "5700 - 5900", {"VI": "6.7 - 13.5", "V": "4 - 7", "IV": "1.5 - 4", "III": "-2 - 1.5", "II": "-4 - -2", "I": "-3.5-", "WD": "10+"}),
    ("G3", "5600 - 5800", {"VI": "6.8 - 13.5", "V": "4 - 7", "IV": "1.5 - 4.5", "III": "-2 - 1.5", "II": "-4 - -2", "I": "-3.5-", "WD": "10+"}),
    ("G4", "5550 - 5750", {"VI": "7 - 13.5", "V": "4 - 7.5", "IV": "1.5 - 5", "III": "-2 - 2", "II": "-4 - -2", "I": "-3-", "WD": "10+"}),
    ("G5", "5500 - 5700", {"VI": "7.5 - 13.5", "V": "4.5 - 7.5", "IV": "1.5 - 5", "III": "-2 - 2", "II": "-4 - -2", "I": "-3-", "WD": "10+"}),
    ("G6", "5450 - 5650", {"VI": "7.5 - 14", "V": "4.5 - 7.5", "IV": "1.5 - 5", "III": "-2 - 2", "II": "-3.5 - -2", "I": "-3-", "WD": "10+"}),
    ("G7", "5400 - 5600", {"VI": "7.5 - 14", "V": "5 - 7.5", "IV": "1.5 - 5", "III": "-2 - 2", "II": "-3.5 - -2", "I": "-3-", "WD": "10+"}),
    ("G8", "5300 - 5500", {"VI": "7.5 - 14.5", "V": "5 - 7.5", "IV": "2 - 5.3", "III": "-2 - 2.5", "II": "-3.5 - -2", "I": "-3-", "WD": "10+"}),
    ("G9", "5200 - 5400", {"VI": "7.5 - 15", "V": "5 - 7.5", "IV": "2 - 5.3", "III": "-2 - 2.5", "II": "-3.5 - -1.5", "I": "-3-", "WD": "10+"}),
    ("K0", "5000 - 5300", {"VI": "8 - 13.5", "V": "5.3 - 8", "IV": "2 - 5.3", "III": "-2 - 2.5", "II": "-3.5 - -1.5", "I": "-3-", "WD": "10+"}),
    ("K1", "4900 - 5100", {"VI": "8 - 13.5", "V": "5.4 - 8", "IV": "2 - 5.5", "III": "-2 - 2.5", "II": "-3.5 - -1.5", "I": "-3-", "WD": "10+"}),
    ("K2", "4800 - 5000", {"VI": "8 - 13.5", "V": "5.4 - 8", "IV": "2 - 5.5", "III": "-2 - 2.5", "II": "-3.5 - -1.5", "I": "-3-", "WD": "10+"}),
    ("K3", "4600 - 4800", {"VI": "8 - 13.5", "V": "5.5 - 8", "IV": "2 - 5.5", "III": "-2 - 2.5", "II": "-3.5 - -1.5", "I": "-3-", "WD": "10+"}),
    ("K4", "4400 - 4600", {"VI": "8 - 13.8", "V": "5.4 - 9", "IV": "2 - 5.4", "III": "-2 - 2.5", "II": "-3.5 - -1.5", "I": "-3-", "WD": "10.5+"}),
    ("K5", "4200 - 4400", {"VI": "8 - 13.8", "V": "5.4 - 9", "IV": "2.5 - 5.4", "III": "-2 - 3", "II": "-3.5 - -1.5", "I": "-3-", "WD": "10.5+"}),
    ("K6", "4000 - 4300", {"VI": "8.5 - 14", "V": "5.5 - 9", "IV": "2.5 - 5.5", "III": "-2 - 3", "II": "-3.3 - -1.5", "I": "-3-", "WD": "11+"}),
    ("K7", "3800 - 4000", {"VI": "9 - 14", "V": "5.5 - 9", "IV": "3 - 5.5", "III": "-2 - 3.2", "II": "-3.3 - -1.5", "I": "-3-", "WD": "11+"}),
    ("K8", "3750 - 3900", {"VI": "9 - 14", "V": "5.5 - 9", "IV": "3 - 5.5", "III": "-2 - 3.5", "II": "-3.3 - -1.5", "I": "-3-", "WD": "11.5+"}),
    ("K9", "3700 - 3850", {"VI": "9 - 14", "V": "5.5 - 9", "IV": "3 - 5.5", "III": "-2 - 3.5", "II": "-3.3 - -1.5", "I": "-3-", "WD": "12+"}),
    ("M0", "3650 - 3850", {"VI": "15 - 20", "V": "8.5 - 18", "III": "-2 - 3", "II": "-3.3 - -1", "I": "-3-", "WD": "16+", "N/A": "3 - 8.5"}),
    ("M1", "3600 - 3700", {"VI": "15 - 20", "V": "8.5 - 18", "III": "-2 - 3", "II": "-3.3 - -1", "I": "-3-", "WD": "16+", "N/A": "3 - 8.5"}),
    ("M2", "3400 - 3600", {"VI": "15 - 21", "V": "8.5 - 18", "III": "-1.8 - 3", "II": "-3.3 - -1", "I": "-3-", "WD": "16+", "N/A": "3 - 8.5"}),
    ("M3", "3250 - 3500", {"VI": "16 - 21", "V": "8.8 - 19", "III": "-1.5 - 3", "II": "-3.3 - -1", "I": "-3-", "WD": "17+", "N/A": "3 - 8.5"}),
    ("M4", "3000 - 3300", {"VI": "17 - 21", "V": "9 - 19", "III": "-1.5 - 3", "II": "-3.3 - -1", "I": "-3-", "WD": "17+", "N/A": "3 - 8.5"}),
    ("M5", "2800 - 3200", {"VI": "17 - 21", "V": "9 -19", "III": "-1.5 - 3", "II": "-3.3 - -1", "I": "-3-", "WD": "17+", "N/A": "3 - 8.5"}),
    ("M6", "2600 - 2900", {"VI": "18+", "V": "9 - 19", "III": "-1.2 - 3", "II": "-3.3 - -1", "I": "-3-", "WD": "18+", "N/A": "3 - 8.5"}),
    ("M7", "2500 - 2700", {"VI": "19+", "V": "9 - 20", "III": "-1.2 - 3", "II": "-3 - -1", "I": "-2.5-", "WD": "18+", "N/A": "3 - 8.5"}),
    ("M8", "2400 - 2550", {"VI": "19+", "V": "9 - 20", "III": "-1.2 - 3", "II": "-3 - -1", "I": "-2.5-", "WD": "18+", "N/A": "3 - 8.5"}),
    ("M9", "2200 - 2450", {"VI": "20+", "V": "9 - 21", "III": "-1.2 - 3", "II": "-3 - -0.5", "I": "-2.5-", "WD": "18+", "N/A": "3 - 8.5"}),
    ("L", "1300 - 2300", {"VI": "14+", "N/A": "14-"}),
    ("T", "800 - 1300", {"VI": "14+", "N/A": "14-"}),
    ("Y", "800-", {"VI": "14+", "N/A": "14-"}),
)


def normalize_rule_number(number_text):
    number_text = number_text.strip().rstrip(".")
    return float(number_text)


def parse_rule_range(range_text):
    range_text = str(range_text).strip().replace("−", "-")
    range_text = re.sub(r"(?<=\d)\.(?=\s*-)", "", range_text)
    interval_match = re.fullmatch(
        r"([+-]?\d+(?:\.\d+)?)\s*-\s*([+-]?\d+(?:\.\d+)?)",
        range_text,
    )
    if interval_match:
        lower = normalize_rule_number(interval_match.group(1))
        upper = normalize_rule_number(interval_match.group(2))
        return min(lower, upper), max(lower, upper)

    if range_text.endswith("+"):
        return normalize_rule_number(range_text[:-1]), None

    if range_text.endswith("-"):
        return None, normalize_rule_number(range_text[:-1])

    value = normalize_rule_number(range_text)
    return value, value


def value_matches_rule(value, rule_text):
    if value is None or not rule_text:
        return False

    for range_text in str(rule_text).split("&"):
        try:
            lower, upper = parse_rule_range(range_text)
        except ValueError:
            LOGGER.warning("Ignoring invalid HR diagram rule range: %s", range_text)
            continue

        if lower is not None and value < lower:
            continue
        if upper is not None and value > upper:
            continue
        return True

    return False


def find_spectral_rules(effective_temperature):
    if effective_temperature is None:
        return []

    return [
        {
            "subclass": subclass,
            "classes": luminosity_rules,
        }
        for subclass, temperature_rule, luminosity_rules in HR_DIAGRAM_RULES
        if value_matches_rule(effective_temperature, temperature_rule)
    ]


def find_evolutionary_classes(spectral_rule, visual_absolute_magnitude):
    if visual_absolute_magnitude is None:
        return []

    return [
        luminosity_class
        for luminosity_class, magnitude_rule in spectral_rule["classes"].items()
        if value_matches_rule(visual_absolute_magnitude, magnitude_rule)
    ]


def format_star_classification(spectral_subclass, luminosity_class):
    if luminosity_class == "N/A":
        return "N/A"
    if spectral_subclass in ("L", "T", "Y") and luminosity_class == "VI":
        return f"{spectral_subclass} dwarf"
    if spectral_subclass == "WR" and luminosity_class == "I":
        return "WR"
    if spectral_subclass == "WR" and luminosity_class == "VI":
        return "O2VI *"
    if luminosity_class == "WD":
        return f"{spectral_subclass}WD"

    classification = f"{spectral_subclass}{luminosity_class}"
    if luminosity_class == "VI":
        classification += " *"
    return classification


def calculate_star_type(source_data, temperature_data, visual_magnitude_data):
    object_type = source_data.get("object_type")
    if object_type is not None and object_type.lower().startswith(
        ("quasar", "galaxy")
    ):
        return {"star_type": None}

    spectral_rules = find_spectral_rules(temperature_data["effective_temperature"])
    visual_absolute_magnitude = visual_magnitude_data[
        "visual_absolute_magnitude"
    ]
    classifications = []
    na_matched = False

    for spectral_rule in spectral_rules:
        spectral_subclass = spectral_rule["subclass"]
        for luminosity_class in find_evolutionary_classes(
            spectral_rule,
            visual_absolute_magnitude,
        ):
            classification = format_star_classification(
                spectral_subclass,
                luminosity_class,
            )
            if classification == "N/A":
                na_matched = True
            else:
                classifications.append(classification)

    unique_classifications = list(dict.fromkeys(classifications))
    if unique_classifications:
        return {"star_type": ", ".join(unique_classifications)}
    if na_matched:
        return {"star_type": "N/A"}

    return {"star_type": None}

def calculate_error_check(source_data):
    ra_error = source_data["ra_error"]
    dec_error = source_data["dec_error"]

    ra_correctness = classify_coordinate_error(ra_error)
    dec_correctness = classify_coordinate_error(dec_error)

    return {
        "ra_correctness": ra_correctness,
        "dec_correctness": dec_correctness,
    }


def calculate_ruwe_check(source_data):
    ruwe_correctness = classify_ruwe(source_data["ruwe"])

    return {
        "ruwe_correctness": ruwe_correctness,
    }


def classify_ruwe(ruwe):
    if ruwe is None:
        return None
    if ruwe < 0.8:
        return "unreliable"
    if ruwe < 1:
        return "good"
    if ruwe == 1:
        return "perfect"
    if ruwe <= 1.2:
        return "accurate"
    if ruwe <= 1.4:
        return "good"
    if ruwe <= 2:
        return "questionable"
    return "unreliable"


def calculate_bp_rp_excess_check(source_data, new_bp_rp_data):
    excess_flux = source_data["phot_bp_rp_excess_factor"]
    x = new_bp_rp_data["new_bp_rp"]

    if excess_flux is None or x is None:
        return {
            "corrected_excess_flux": None,
            "bp_rp_excess_correctness": None,
        }

    correction = calculate_bp_rp_excess_correction(x)
    corrected_excess_flux = excess_flux - correction
    sigma = 0.005 + 0.03 * (x ** 2)

    return {
        "corrected_excess_flux": round(corrected_excess_flux, 6),
        "bp_rp_excess_correctness": classify_corrected_bp_rp_excess_flux(
            corrected_excess_flux,
            sigma,
        ),
    }


def calculate_bp_rp_excess_correction(x):
    if x < 0.5:
        return 1.154360 + 0.033772 * x + 0.032277 * (x ** 2)
    if x <= 4:
        return (
            1.162004
            + 0.011464 * x
            + 0.049255 * (x ** 2)
            - 0.005879 * (x ** 3)
        )
    return 1.057572 + 0.140537 * x


def classify_corrected_bp_rp_excess_flux(corrected_excess_flux, sigma):
    if corrected_excess_flux < -3 * sigma:
        return "Inaccurate"
    if corrected_excess_flux <= 3 * sigma:
        return "accurate"
    if corrected_excess_flux <= 5 * sigma:
        return "Inaccurate"
    return "Unreliable"


def classify_coordinate_error(error_mas):
    if error_mas is None:
        return None
    if error_mas <= 0.03:
        return "accurate"
    if error_mas <= 0.05:
        return "moderate"
    if error_mas <= 1:
        return "susceptible"
    if error_mas <= 2:
        return "inaccurate"
    return "unreliable"


def calculate_parallax_check(source_data):
    parallax = source_data["parallax"]
    parallax_over_error = source_data["parallax_over_error"]

    if parallax is None:
        return {
            "parallax_data_status": None,
            "parallax_correctness": None,
        }

    if parallax < 0:
        return {
            "parallax_data_status": "insufficient or unreliable data",
            "parallax_correctness": None,
        }

    return {
        "parallax_data_status": None,
        "parallax_correctness": classify_parallax_over_error(parallax_over_error),
    }


def classify_parallax_over_error(parallax_over_error):
    if parallax_over_error is None:
        return None
    if parallax_over_error >= 20:
        return "accurate"
    if parallax_over_error >= 10:
        return "acceptable"
    if parallax_over_error >= 5:
        return "moderate"
    if parallax_over_error >= 2:
        return "Inaccurate"
    return "unreliable"


def calculate_distance(source_data):
    parallax = source_data["parallax"]

    if number(parallax) is None or parallax <= 0:
        return {
            "distance_parsecs": None,
            "distance_lightyears": None,
        }

    distance_parsecs = 1000 / parallax
    distance_lightyears = distance_parsecs * 3.26156

    return {
        "distance_parsecs": distance_parsecs,
        "distance_lightyears": distance_lightyears,
    }


def calculate_dust_extinction(source_data, distance_data):
    galactic_l = source_data["l"]
    galactic_b = source_data["b"]
    distance_parsecs = distance_data.get("adopted_distance_pc", distance_data.get("distance_parsecs"))

    if (
        galactic_l is None
        or galactic_b is None
        or distance_parsecs is None
        or distance_parsecs <= 0
    ):
        return {
            "ebv": None,
            "mean_g_band_extinction": None,
            "bp_rp_reddening": None,
        }

    distance_kpc = distance_parsecs / 1000

    try:
        ebv = fetch_dust_ebv(galactic_l, galactic_b, distance_kpc)
    except network.QueryCancelled:
        raise
    except (QueryServiceError, network.NetworkFailure) as error:
        LOGGER.error("Dust data unavailable: %s", error)
        ebv = None

    if ebv is None:
        return {
            "ebv": None,
            "mean_g_band_extinction": None,
            "bp_rp_reddening": None,
        }

    mean_g_band_extinction = round(ebv * 2.74, 6)
    bp_rp_reddening = round(ebv * 1.21, 6)

    return {
        "ebv": ebv,
        "mean_g_band_extinction": mean_g_band_extinction,
        "bp_rp_reddening": bp_rp_reddening,
    }


def fetch_dust_ebv(galactic_l, galactic_b, distance_kpc):
    context = network.CURRENT.get()
    if context:
        context.report("Looking up dust reddening")
    with network.timed("dust lookup"):
        return network.cached("dust", [DUST_CALCULATOR_URL, "galactic", galactic_l, galactic_b, distance_kpc],
            lambda: network.bounded("aux", ("scientist_aux", "dust", (galactic_l, galactic_b, distance_kpc)),
                limit=(context.options if context else network.settings()).optional_timeout), cache_none=False)


def calculate_absolute_magnitude(source_data, distance_data, dust_data):
    mean_g = source_data["phot_g_mean_mag"]
    distance_parsecs = distance_data.get("adopted_distance_pc", distance_data.get("distance_parsecs"))
    mean_g_band_extinction = dust_data["mean_g_band_extinction"]

    if (
        mean_g is None
        or distance_parsecs is None
        or distance_parsecs <= 0
        or mean_g_band_extinction is None
    ):
        return {"absolute_magnitude": None}

    absolute_magnitude = (
        mean_g
        - 5 * log10(distance_parsecs)
        + 5
        - mean_g_band_extinction
    )
    return {"absolute_magnitude": round(absolute_magnitude, 6)}


def calculate_luminosity(absolute_magnitude_data):
    absolute_magnitude = absolute_magnitude_data["absolute_magnitude"]

    if absolute_magnitude is None:
        return {"luminosity": None}

    luminosity = 10 ** (0.4 * (4.67 - absolute_magnitude))
    return {"luminosity": round(luminosity, 6)}


def calculate_radius(luminosity_data, temperature_data):
    """A G-band ratio cannot supply a bolometric radius."""
    return {"radius": None}


def calculate_legacy_radius(luminosity_data, temperature_data):
    luminosity_solar = luminosity_data["luminosity"]
    effective_temperature = temperature_data["effective_temperature"]

    if (
        luminosity_solar is None
        or luminosity_solar < 0
        or effective_temperature is None
        or effective_temperature <= 0
    ):
        return {"radius": None}

    luminosity_watts = luminosity_solar * SOLAR_LUMINOSITY_WATTS
    radius_meters = sqrt(
        luminosity_watts
        / (
            4
            * pi
            * STEFAN_BOLTZMANN_CONSTANT
            * (effective_temperature ** 4)
        )
    )
    radius_solar = radius_meters / SOLAR_RADIUS_METERS

    return {"radius": round(radius_solar, 6)}


def calculate_peak_wavelength(temperature_data):
    effective_temperature = temperature_data["effective_temperature"]

    if effective_temperature is None or effective_temperature <= 0:
        return {"peak_wavelength": None}

    peak_wavelength_meters = WIEN_DISPLACEMENT_CONSTANT / effective_temperature
    peak_wavelength_nanometers = peak_wavelength_meters * 1_000_000_000

    return {"peak_wavelength": round(peak_wavelength_nanometers, 6)}


def calculate_new_bp_rp(source_data, dust_data):
    bp_rp = source_data["bp_rp"]
    bp_rp_reddening = dust_data["bp_rp_reddening"]

    if bp_rp is None or bp_rp_reddening is None:
        return {"new_bp_rp": None}

    new_bp_rp = bp_rp - bp_rp_reddening
    return {"new_bp_rp": round(new_bp_rp, 6)}


def calculate_legacy_effective_temperature(
    source_data,
    new_bp_rp_data,
    visual_magnitude_data,
):
    x = new_bp_rp_data["new_bp_rp"]
    metallicity = source_data["metallicity"]
    visual_absolute_magnitude = visual_magnitude_data[
        "visual_absolute_magnitude"
    ]

    if x is None:
        return {"effective_temperature": None}

    use_red_dwarf_formula = (
        x > 1.8
        and visual_absolute_magnitude is not None
        and visual_absolute_magnitude > 8.69
    )

    if x < 0:
        log_teff = (
            3.978
            - 1.258 * x
            + 0.812 * (x ** 2)
            - 0.505 * (x ** 3)
        )
        effective_temperature = 10 ** log_teff
    elif use_red_dwarf_formula and metallicity is None:
        effective_temperature = (
            4370
            - 715 * x
            + 107 * (x ** 2)
            - 7.5 * (x ** 3)
        )
    elif use_red_dwarf_formula:
        effective_temperature = (
            4430
            - 740 * x
            + 112 * (x ** 2)
            - 8 * (x ** 3)
            + 115 * metallicity
            - 25 * metallicity * x
        )
    elif metallicity is None:
        effective_temperature = (
            9345
            - 6125 * x
            + 3381 * (x ** 2)
            - 1282 * (x ** 3)
            + 276 * (x ** 4)
            - 24.3 * (x ** 5)
        )
    else:
        theta = (
            0.4929
            + 0.5092 * x
            - 0.0353 * (x ** 2)
            + 0.0192 * metallicity
            - 0.0020 * (metallicity ** 2)
            - 0.0395 * metallicity * x
        )
        if theta == 0:
            return {"effective_temperature": None}
        effective_temperature = 5040 / theta

    return {"effective_temperature": round(effective_temperature, 6)}


def calculate_visual_absolute_magnitude(
    new_bp_rp_data,
    absolute_magnitude_data,
):
    bp_rp = new_bp_rp_data["new_bp_rp"]
    absolute_magnitude = absolute_magnitude_data["absolute_magnitude"]

    if bp_rp is None or not -.5 < bp_rp < 5 or absolute_magnitude is None:
        return {"visual_absolute_magnitude": None}

    visual_absolute_magnitude = (
        absolute_magnitude
        + 0.02704
        - 0.01424 * bp_rp
        + 0.2156 * (bp_rp ** 2)
        - 0.01426 * (bp_rp ** 3)
    )
    return {
        "visual_absolute_magnitude": round(visual_absolute_magnitude, 6)
    }


def calculate_visual_apparent_magnitude(
    source_data,
    new_bp_rp_data,
    dust_data,
):
    mean_g = source_data["phot_g_mean_mag"]
    bp_rp = new_bp_rp_data["new_bp_rp"]
    mean_g_band_extinction = dust_data["mean_g_band_extinction"]

    if mean_g is None or bp_rp is None or not -.5 < bp_rp < 5 or mean_g_band_extinction is None:
        return {"visual_apparent_magnitude": None}

    corrected_mean_g = mean_g - mean_g_band_extinction
    visual_apparent_magnitude = (
        corrected_mean_g
        + 0.02704
        - 0.01424 * bp_rp
        + 0.2156 * (bp_rp ** 2)
        - 0.01426 * (bp_rp ** 3)
    )
    return {
        "visual_apparent_magnitude": round(visual_apparent_magnitude, 6)
    }


def calculate_excess_noise_check(source_data):
    excess_noise = source_data["astrometric_excess_noise"]
    excess_noise_sig = source_data["astrometric_excess_noise_sig"]

    excess_noise_factor = classify_excess_noise_factor(excess_noise)
    if excess_noise_factor not in (None, "accurate"):
        excess_noise_factor = f"{excess_noise_factor} *"

    return {
        "excess_noise_factor": excess_noise_factor,
        "excess_noise_significance": classify_excess_noise_significance(
            excess_noise_sig
        ),
    }


def classify_excess_noise_factor(excess_noise):
    if excess_noise is None:
        return None
    if excess_noise <= 0.1:
        return "accurate"
    if excess_noise <= 0.5:
        return "good"
    if excess_noise <= 1:
        return "moderate"
    return "questionable"


def classify_excess_noise_significance(excess_noise_sig):
    if excess_noise_sig is None:
        return None
    if excess_noise_sig <= 2:
        return "inaccurate"
    if excess_noise_sig <= 5:
        return "questionable"
    if excess_noise_sig <= 20:
        return "moderate"
    return "reliable"


def convert_ra_to_hms(equatorial_coordinate_ra):
    ra_hours = equatorial_coordinate_ra / 15
    hour_variable = int(ra_hours)

    minute_source = (ra_hours - hour_variable) * 60
    minutes_variable = int(minute_source)

    seconds_variable = (minute_source - minutes_variable) * 60

    return hour_variable, minutes_variable, round(seconds_variable, 2)


def find_constellation(equatorial_coordinate_ra, equatorial_coordinate_dec):
    coordinate = SkyCoord(
        ra=equatorial_coordinate_ra * u.degree,
        dec=equatorial_coordinate_dec * u.degree,
        frame="icrs",
    )
    return coordinate.get_constellation(short_name=False)


def _clean_value(value):
    if value is None:
        return None

    try:
        if value.mask:
            return None
    except AttributeError:
        pass

    try:
        value = value.item()
    except AttributeError:
        pass
    if isinstance(value, float) and not isfinite(value):
        return None
    return value


def main():
    load_desktop_gui()
    root = tk.Tk()
    GaiaAssistApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
