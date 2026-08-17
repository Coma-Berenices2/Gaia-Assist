import logging
import queue
import re
import threading
import time
import tkinter as tk
from datetime import datetime
from math import cos, log10, pi, radians, sqrt
from pathlib import Path
from tkinter import messagebox, ttk

import astropy.units as u
import requests
from astropy.coordinates import SkyCoord
from astroquery.gaia import Gaia


GAIA_COLUMNS = {
    "source_id": "Source ID",
    "object_type": "Object Type",
    "metallicity": "Metallicity (M/H)",
    "ra": "Equatorial Coordinate RA",
    "dec": "Equatorial Coordinate DEC",
    "l": "Galactic Coordinate l",
    "b": "Galactic Coordinate b",
    "ra_error": "RA Error",
    "dec_error": "DEC Error",
    "parallax": "Parallax",
    "parallax_over_error": "Parallax Over Error",
    "astrometric_excess_noise": "Excess Noise",
    "astrometric_excess_noise_sig": "Excess Noise Sig",
    "ruwe": "RUWE",
    "phot_bp_rp_excess_factor": "BP+RP Excess Flux",
    "radial_velocity": "Radial Velocity",
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

ALL_DISPLAY_COLUMNS = {**GAIA_COLUMNS, **DERIVED_COLUMNS}

PRIMARY_DISPLAY_ORDER = (
    "source_id",
    "object_type",
    "ra_hms_dec",
    "constellation",
    "distance_lightyears",
    "distance_parsecs",
    "absolute_magnitude",
    "visual_absolute_magnitude",
    "visual_apparent_magnitude",
    "luminosity",
    "effective_temperature",
    "radius",
    "peak_wavelength",
    "ra_correctness",
    "dec_correctness",
    "parallax_data_status",
    "ruwe_correctness",
    "bp_rp_excess_correctness",
    "parallax_correctness",
    "excess_noise_factor",
    "excess_noise_significance",
    "star_type",
    "corrected_excess_flux",
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

MISSING_VALUES_LOG = Path(__file__).with_name("gaia_missing_values_log.txt")
DEBUG_LOG = Path(__file__).with_name("gaia_assist_debug.log")
SAVED_OBJECTS_DIR = Path(__file__).with_name("saved_objects")
DUST_CALCULATOR_URL = "https://nadc.china-vo.org/data/dustmaps/calculator"
COMMON_NAME_RELEASE = "Common Name (Testing)"
SESAME_URLS = (
    "https://cds.unistra.fr/cgi-bin/nph-sesame/-oxpI/SNV?{name}",
    "https://cdsweb.u-strasbg.fr/cgi-bin/nph-sesame/-oxpI/SNV?{name}",
)
STEFAN_BOLTZMANN_CONSTANT = 5.670374419e-8
SOLAR_LUMINOSITY_WATTS = 3.828e26
SOLAR_RADIUS_METERS = 6.957e8
WIEN_DISPLACEMENT_CONSTANT = 2.897771955e-3

LOGGER = logging.getLogger("gaia_assist")
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
    for attempt in range(1, attempts + 1):
        try:
            LOGGER.info("%s request attempt %d/%d", service, attempt, attempts)
            result = operation()
            LOGGER.info("%s request succeeded", service)
            return result
        except Exception as error:
            LOGGER.warning(
                "%s request attempt %d/%d failed: %s",
                service,
                attempt,
                attempts,
                error,
                exc_info=True,
            )
            if attempt == attempts:
                raise QueryServiceError(
                    service,
                    f"{service} failed after {attempts} attempts: {error}",
                ) from error
            time.sleep(2 ** (attempt - 1))

# Fill these strings manually to explain each clickable field row.
FIELD_EXPLANATIONS = {
    "source_id": "The ID of this object.",
    "object_type": "The type of object it should be. Binary stars or white dwarfs sometimes display an objects with near 0 probability.",
    "metallicity": "All 'metals' heavier than helium in this object.",
    "ra": "The RA (Right Ascension) of a star is its east-west coordinate in the night sky.",
    "dec": "DEC (abbreviation for Declination) is the celestial equivalent of latitude, measuring a star is north or south of the celestial equator.",
    "l": "From 0 to 360, it measures an object's angular position relative to the galactic center in the perpestive of our Sun.",
    "b": "From -90 to 90, it measures an object's angular position, from the perspective of our Sun, is ascending or descending, and which -90 is galactic South Pole, 90 is galactic North Pole. ",
    "ra_error": "RA Error",
    "dec_error": "DEC Error",
    "parallax": "The angular measurement of an object's movement as the Earth orbits. It is used to measure the distance of an object.",
    "parallax_over_error": "Parallax uncentainty.",
    "astrometric_excess_noise": "The object's unexpected noise in it's position.",
    "astrometric_excess_noise_sig": "How significant is the excess noise.",
    "ruwe": "Renormalizing due to a star's mismatch of a single star model.",
    "bp_rp": "The difference between blue and red color of a star.",
    "phot_bp_rp_excess_factor": "BP+RP Excess Flux",
    "ra_hms_dec": "The Equatorial Coordinate.",
    "constellation": "The constellation it belongs to.",
    "ra_correctness": "RA Correctness",
    "dec_correctness": "DEC Correctness",
    "parallax_data_status": "Can the parallax be used?",
    "parallax_correctness": "Is the Parallax considered correct?",
    "ruwe_correctness": "Correctness of Renormalised unit weight.",
    "bp_rp_excess_correctness": "Correctness of excess photon factos. Note red dwarf inherently has a higher bp+rp excess flux, which can reach up to 1.3-1.5, exceeding what's normal for other stars.",
    "distance_parsecs": "The distance measured in Parsecs.",
    "distance_lightyears": "The distance measured in Lightyears.",
    "ebv": "The dust extinction factor.",
    "mean_g_band_extinction": "Dust factor for Gaia G band.",
    "bp_rp_reddening": "Dust reddening factor for bp-rp.",
    "new_bp_rp": "The new, dereddened bp-rp.",
    "corrected_excess_flux": "",
    "effective_temperature": "The temperature.",
    "absolute_magnitude": "The absolute magnitude of the object(10 parsecs)",
    "luminosity": "The brightness of this object.",
    "radius": "The size of this object.",
    "peak_wavelength": "",
    "visual_absolute_magnitude": "The absolute magnitude in Johnson's V band.",
    "visual_apparent_magnitude": "The apparent magnitude in Johnson's V band.",
    "excess_noise_factor": "Noise Factor",
    "excess_noise_significance": "Noise Factor's Significance.",
    "star_type": "The exact type of the star. This uses effective temperature to locate the spectral type first, then visual absolute magnitude to locate the evolutionary stage.",
}

FIELD_UNITS = {
    "source_id": "unitless",
    "object_type": "% probability",
    "metallicity": "dex",
    "ra": "deg",
    "dec": "deg",
    "l": "deg",
    "b": "deg",
    "ra_error": "mas",
    "dec_error": "mas",
    "parallax": "mas",
    "parallax_over_error": "unitless",
    "astrometric_excess_noise": "mas",
    "astrometric_excess_noise_sig": "unitless",
    "ruwe": "unitless",
    "phot_bp_rp_excess_factor": "unitless",
    "radial_velocity": "km/s",
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


class GaiaAssistApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Gaia Assist")
        self.root.geometry("720x520")
        self.root.minsize(680, 460)

        self.gaia_code = tk.StringVar()
        self.gaia_release = tk.StringVar(value="DR3")
        self.hide_prior_data = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Enter a Gaia source_id to begin.")
        self.result_vars = {
            column_name: tk.StringVar(value="-") for column_name in DISPLAY_COLUMNS
        }
        self.result_value_widgets = {}
        self.unit_widgets = {}
        self.field_label_widgets = {}
        self.row_widgets = {}
        self.query_in_progress = False
        self.query_events = queue.Queue()
        self.last_saved_object_key = None
        self.normal_value_font = ("Segoe UI", 10)
        self.underline_value_font = ("Segoe UI", 10, "underline")

        self._build_interface()
        self.root.after(100, self.process_query_events)

    def _build_interface(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)

        header = ttk.Frame(self.root, padding=(24, 22, 24, 10))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        title = ttk.Label(header, text="Gaia Assist", font=("Segoe UI", 20, "bold"))
        title.grid(row=0, column=0, sticky="w")

        subtitle = ttk.Label(
            header,
            text="Fetch core astrometric and photometric values from ESA Gaia DR3.",
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

        ttk.Checkbutton(
            input_frame,
            text="Hide Prior Data",
            variable=self.hide_prior_data,
            command=self.toggle_prior_data,
        ).grid(row=2, column=1, sticky="w", padx=(10, 0), pady=(8, 0))

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
        ttk.Button(
            action_frame,
            text="Save",
            command=self.save_current_results,
        ).grid(row=0, column=1, sticky="e")

        result_frame = ttk.Frame(self.root, padding=(24, 0, 24, 12))
        result_frame.grid(row=2, column=0, sticky="nsew")
        result_frame.columnconfigure(0, weight=1)
        result_frame.rowconfigure(0, weight=1)

        table_container = ttk.Frame(result_frame)
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
            field_label = ttk.Label(
                self.result_rows_frame,
                text=label,
                padding=(8, 4),
                font=self.normal_value_font,
                cursor="hand2",
            )
            field_label.grid(row=row_number, column=0, sticky="ew")
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
                field_label,
                value_frame,
                unit_frame,
            )

    def toggle_prior_data(self):
        hide_secondary_rows = self.hide_prior_data.get()

        for column_name in SECONDARY_DISPLAY_COLUMNS:
            for widget in self.row_widgets[column_name]:
                if hide_secondary_rows:
                    widget.grid_remove()
                else:
                    widget.grid()

    def update_input_mode(self, _event=None):
        if self.gaia_release.get() == COMMON_NAME_RELEASE:
            self.input_label.configure(text="Common Name")
        else:
            self.input_label.configure(text="Gaia Code")

    def set_field_hover(self, field_name, is_hovered):
        font = self.underline_value_font if is_hovered else self.normal_value_font
        self.field_label_widgets[field_name].configure(font=font)

    def show_field_explanation(self, field_name):
        title = DISPLAY_COLUMNS[field_name]
        explanation = FIELD_EXPLANATIONS.get(field_name, "")
        if not explanation:
            explanation = "Explanation not added yet."

        self.show_centered_message_window(title, explanation)

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

    def create_copyable_value_widget(self, parent, cursor="xterm", width=34):
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
            cursor=cursor,
        )
        value_widget.grid(row=0, column=0, sticky="w")
        return value_widget

    def set_copyable_value_text(self, value_widget, display_value):
        value_widget.configure(state="normal")
        value_widget.delete("1.0", "end")
        value_widget.insert("1.0", display_value)
        value_widget.configure(state="disabled")

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

    def show_centered_message_window(self, title, message):
        message_window = tk.Toplevel(self.root)
        message_window.title(title)
        window_width = 420
        window_height = 190
        screen_width = message_window.winfo_screenwidth()
        screen_height = message_window.winfo_screenheight()
        position_x = (screen_width - window_width) // 2
        position_y = (screen_height - window_height) // 2
        message_window.geometry(
            f"{window_width}x{window_height}+{position_x}+{position_y}"
        )
        message_window.resizable(False, False)
        message_window.transient(self.root)
        message_window.grab_set()

        message_text = tk.Text(
            message_window,
            wrap="word",
            height=5,
            borderwidth=0,
            highlightthickness=0,
            padx=22,
            pady=18,
            font=("Segoe UI", 10),
        )
        message_text.insert("1.0", message)
        message_text.configure(state="disabled")
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
                value = self.result_vars[column_name].get()
                unit = FIELD_UNITS.get(column_name, "")
                if not value:
                    value = "-"
                if not unit:
                    unit = "-"
                output_file.write(f"{label}\t{value}\t{unit}\n")

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
            args=(source_id, release),
            daemon=True,
        )
        worker.start()

    def run_query_pipeline(self, source_id, release):
        try:
            source_data = fetch_gaia_source_data(source_id, release)
            log_missing_values(source_id, source_data)
            self.query_events.put(
                (
                    "status",
                    "Gaia data loaded; querying NADC dust map and calculating...",
                )
            )
            derived_data = calculate_derived_data(source_data)
            display_data = self.build_display_data(source_data, derived_data)
            warnings = collect_pipeline_warnings(source_data, derived_data)
        except Exception as error:
            LOGGER.exception(
                "Query pipeline failed for release=%s source_id=%s",
                release,
                source_id,
            )
            self.query_events.put(("error", source_id, release, error))
            return

        LOGGER.info(
            "Query pipeline completed for release=%s source_id=%s",
            release,
            source_id,
        )
        self.query_events.put(
            ("success", source_id, release, display_data, warnings)
        )

    def process_query_events(self):
        try:
            while True:
                event = self.query_events.get_nowait()
                event_type = event[0]

                if event_type == "status":
                    self.status.set(event[1])
                elif event_type == "success":
                    self.handle_query_success(
                        event[1], event[2], event[3], event[4]
                    )
                elif event_type == "error":
                    self.handle_query_error(event[1], event[2], event[3])
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
        for column_name, value in display_data.items():
            display_value = "-" if value is None else str(value)
            self.result_vars[column_name].set(display_value)
            self.update_result_value(column_name, display_value)

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

    def handle_query_error(self, source_id, release, error):
        self.finish_query()
        if isinstance(error, QueryServiceError):
            service = error.service
        else:
            service = "calculation pipeline"

        self.status.set(f"{service} failed. See gaia_assist_debug.log.")
        messagebox.showerror(
            f"{service} failed",
            f"{release} source {source_id} could not be completed.\n\n"
            f"{error}\n\nDetails were written to:\n{DEBUG_LOG}",
        )

    def finish_query(self):
        self.query_in_progress = False
        self.query_button.configure(state="normal")
        self.release_selector.configure(state="readonly")


def fetch_sesame_response(common_name):
    encoded_name = requests.utils.quote(common_name.strip(), safe="")
    errors = []

    for url_template in SESAME_URLS:
        url = url_template.format(name=encoded_name)
        try:
            response = requests.get(
                url,
                headers={"User-Agent": "GaiaAssist/1.0"},
                timeout=20,
            )
            response.raise_for_status()
            if response.text.strip():
                return response.text
        except requests.RequestException as error:
            errors.append(f"{url}: {error}")

    raise requests.ConnectionError("; ".join(errors))


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
        job = Gaia.launch_job_async(query, dump_to_file=False)
        return job.get_results()

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
        job = Gaia.launch_job_async(query, dump_to_file=False)
        return job.get_results()

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


def fetch_gaia_source_data(source_id, release="DR3"):
    dr3_source_id = resolve_dr3_source_id(source_id, release)
    source_query = f"""
        SELECT
            source_id,
            ra,
            dec,
            l,
            b,
            ra_error,
            dec_error,
            parallax,
            parallax_over_error,
            astrometric_excess_noise,
            astrometric_excess_noise_sig,
            ruwe,
            phot_bp_rp_excess_factor,
            radial_velocity,
            phot_g_mean_mag,
            bp_rp
        FROM gaiadr3.gaia_source
        WHERE source_id = {dr3_source_id}
    """
    astrophysical_query = f"""
        SELECT
            classprob_dsc_combmod_quasar,
            classprob_dsc_combmod_galaxy,
            classprob_dsc_combmod_star,
            mh_gspphot
        FROM gaiadr3.astrophysical_parameters
        WHERE source_id = {dr3_source_id}
    """

    def launch_source_query():
        job = Gaia.launch_job_async(source_query, dump_to_file=False)
        return job.get_results()

    source_results = run_with_retries(
        launch_source_query,
        "ESA Gaia source table",
        attempts=2,
    )

    if len(source_results) == 0:
        raise QueryServiceError(
            "ESA Gaia source table",
            f"No Gaia DR3 source found for source_id {dr3_source_id}.",
        )

    def launch_astrophysical_query():
        job = Gaia.launch_job_async(astrophysical_query, dump_to_file=False)
        return job.get_results()

    try:
        astrophysical_results = run_with_retries(
            launch_astrophysical_query,
            "ESA Gaia astrophysical parameters",
            attempts=2,
        )
    except QueryServiceError as error:
        LOGGER.error("Gaia astrophysical parameters unavailable: %s", error)
        astrophysical_results = []

    row = source_results[0]
    if len(astrophysical_results) == 0:
        astrophysical_row = {
            "classprob_dsc_combmod_quasar": None,
            "classprob_dsc_combmod_galaxy": None,
            "classprob_dsc_combmod_star": None,
            "mh_gspphot": None,
        }
    else:
        astrophysical_row = astrophysical_results[0]

    queried_source_id = _clean_value(row["source_id"])
    object_type = format_object_type_probability(astrophysical_row)
    metallicity = _clean_value(astrophysical_row["mh_gspphot"])
    equatorial_coordinate_ra = _clean_value(row["ra"])
    equatorial_coordinate_dec = _clean_value(row["dec"])
    galactic_coordinate_l = _clean_value(row["l"])
    galactic_coordinate_b = _clean_value(row["b"])
    ra_error = _clean_value(row["ra_error"])
    dec_error = _clean_value(row["dec_error"])
    parallax = _clean_value(row["parallax"])
    parallax_over_error = _clean_value(row["parallax_over_error"])
    excess_noise = _clean_value(row["astrometric_excess_noise"])
    excess_noise_sig = _clean_value(row["astrometric_excess_noise_sig"])
    ruwe = _clean_value(row["ruwe"])
    bp_rp_excess_flux = _clean_value(row["phot_bp_rp_excess_factor"])
    radial_velocity = _clean_value(row["radial_velocity"])
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
        "ra_error": ra_error,
        "dec_error": dec_error,
        "parallax": parallax,
        "parallax_over_error": parallax_over_error,
        "astrometric_excess_noise": excess_noise,
        "astrometric_excess_noise_sig": excess_noise_sig,
        "ruwe": ruwe,
        "phot_bp_rp_excess_factor": bp_rp_excess_flux,
        "radial_velocity": radial_velocity,
        "phot_g_mean_mag": mean_g,
        "bp_rp": mean_bp_rp,
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
    parallax = source_data.get("parallax")
    dust_query_expected = (
        parallax is not None
        and parallax > 0
        and source_data.get("l") is not None
        and source_data.get("b") is not None
    )

    if dust_query_expected and derived_data.get("ebv") is None:
        warnings.append("NADC dust data unavailable")

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


def calculate_derived_data(source_data):
    derived_data = {
        **calculate_first_step(source_data),
        **calculate_error_check(source_data),
        **calculate_ruwe_check(source_data),
    }

    parallax_check = calculate_parallax_check(source_data)
    derived_data.update(parallax_check)

    if parallax_check["parallax_data_status"] == "insufficient or unreliable data":
        return derived_data

    distance_data = calculate_distance(source_data)
    derived_data.update(distance_data)
    dust_data = calculate_dust_extinction(source_data, distance_data)
    derived_data.update(dust_data)
    new_bp_rp_data = calculate_new_bp_rp(source_data, dust_data)
    derived_data.update(new_bp_rp_data)
    derived_data.update(
        calculate_bp_rp_excess_check(source_data, new_bp_rp_data)
    )
    absolute_magnitude_data = calculate_absolute_magnitude(
        source_data, distance_data, dust_data
    )
    derived_data.update(absolute_magnitude_data)
    visual_absolute_magnitude_data = calculate_visual_absolute_magnitude(
        new_bp_rp_data,
        absolute_magnitude_data,
    )
    derived_data.update(visual_absolute_magnitude_data)
    temperature_data = calculate_effective_temperature(
        source_data,
        new_bp_rp_data,
        visual_absolute_magnitude_data,
    )
    derived_data.update(temperature_data)
    luminosity_data = calculate_luminosity(absolute_magnitude_data)
    derived_data.update(luminosity_data)
    derived_data.update(calculate_radius(luminosity_data, temperature_data))
    derived_data.update(calculate_peak_wavelength(temperature_data))
    derived_data.update(
        calculate_star_type(
            source_data,
            temperature_data,
            visual_absolute_magnitude_data,
        )
    )
    derived_data.update(
        calculate_visual_apparent_magnitude(
            source_data,
            new_bp_rp_data,
            dust_data,
        )
    )
    derived_data.update(calculate_excess_noise_check(source_data))

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

    if parallax is None or parallax == 0:
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
    distance_parsecs = distance_data["distance_parsecs"]

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
    except QueryServiceError as error:
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
    return run_with_retries(
        lambda: fetch_dust_ebv_once(
            galactic_l,
            galactic_b,
            distance_kpc,
        ),
        "NADC dust calculator",
        attempts=2,
    )


def fetch_dust_ebv_once(galactic_l, galactic_b, distance_kpc):
    with requests.Session() as session:
        page_response = session.get(DUST_CALCULATOR_URL, timeout=20)
        page_response.raise_for_status()

        token_match = re.search(
            r'var\s+csrf_token\s*=\s*"([^"]+)"',
            page_response.text,
        )
        if token_match is None:
            raise ValueError("The dust calculator CSRF token was not found.")

        csrf_token = token_match.group(1)
        form_data = {
            "coord_system": "galactic",
            "coord1": str(galactic_l),
            "coord2": str(galactic_b),
            "d": str(distance_kpc),
            "csrf_token": csrf_token,
        }
        result_response = session.post(
            DUST_CALCULATOR_URL,
            data=form_data,
            headers={
                "Referer": DUST_CALCULATOR_URL,
                "X-CSRFToken": csrf_token,
            },
            timeout=40,
        )
        result_response.raise_for_status()

    ebv_match = re.search(
        r'E\(B-V\).*?<kbd>\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*mag\s*</kbd>',
        result_response.text,
        re.IGNORECASE | re.DOTALL,
    )
    if ebv_match is None:
        raise ValueError("E(B-V) was not found in the dust calculator response.")

    return float(ebv_match.group(1))


def calculate_absolute_magnitude(source_data, distance_data, dust_data):
    mean_g = source_data["phot_g_mean_mag"]
    distance_parsecs = distance_data["distance_parsecs"]
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


def calculate_effective_temperature(
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

    if bp_rp is None or absolute_magnitude is None:
        return {"visual_absolute_magnitude": None}

    visual_absolute_magnitude = (
        absolute_magnitude
        + 0.02704
        + 0.01424 * bp_rp
        + 0.1607 * (bp_rp ** 2)
        - 0.01235 * (bp_rp ** 3)
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

    if mean_g is None or bp_rp is None or mean_g_band_extinction is None:
        return {"visual_apparent_magnitude": None}

    corrected_mean_g = mean_g - mean_g_band_extinction
    visual_apparent_magnitude = (
        corrected_mean_g
        + 0.02704
        + 0.01424 * bp_rp
        + 0.1607 * (bp_rp ** 2)
        - 0.01235 * (bp_rp ** 3)
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
        return value.item()
    except AttributeError:
        return value


def main():
    root = tk.Tk()
    GaiaAssistApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
