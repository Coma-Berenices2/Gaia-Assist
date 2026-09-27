"""Desktop controls for the isolated temperature experiment."""
from dataclasses import asdict, replace
from pathlib import Path
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from temperature_model import TemperatureOptions
from temperature_schema import format_display_value
from temperature_storage import load_records


def open_network_settings(app):
    import scientist_network as network
    window = tk.Toplevel(app.root)
    window.title("Scientist network and cache settings")
    frame = ttk.Frame(window, padding=16)
    frame.pack(fill="both", expand=True)
    labels = {"request_timeout": "Per-request timeout (seconds)", "overall_timeout": "Overall limit per query / batch (seconds)",
        "optional_timeout": "Optional data wait (seconds)", "cache_ttl": "Cache expiry (seconds)",
        "batch_size": "IDs per batch", "sync_limit": "Maximum IDs for synchronous TAP",
        "attempts": "Transient request attempts (1–3)", "poll_interval": "Async polling interval (seconds)"}
    variables = {}
    for row, (key, value) in enumerate(asdict(network.settings()).items()):
        ttk.Label(frame, text=labels[key]).grid(row=row, column=0, sticky="w", pady=4)
        variables[key] = tk.StringVar(value=str(value))
        ttk.Entry(frame, textvariable=variables[key], width=14).grid(row=row, column=1, padx=12)
    def apply():
        try:
            values = {k: (int(v.get()) if k in ("batch_size", "sync_limit", "attempts") else float(v.get())) for k, v in variables.items()}
            network.save_settings(network.NetworkOptions(**values))
        except (ValueError, OSError) as error:
            messagebox.showerror("Check network settings", str(error), parent=window)
            return
        window.destroy()
    ttk.Button(frame, text="Save", command=apply).grid(row=len(labels), column=1, pady=10)
    return window


def open_distance_settings(app):
    window = tk.Toplevel(app.root)
    window.title("Scientist distance settings")
    frame = ttk.Frame(window, padding=18)
    frame.pack(fill="both", expand=True)
    mode = tk.StringVar(value=app.temperature_options.distance_mode)
    threshold = tk.StringVar(value=str(app.temperature_options.distance_auto_threshold*100))
    ttk.Label(frame, text="Adopted distance").grid(row=0, column=0, sticky="w")
    ttk.Combobox(frame, textvariable=mode, values=("Baseline", "Bayesian geometric", "Automatic"), state="readonly").grid(row=0, column=1, padx=12)
    ttk.Label(frame, text="Automatic baseline uncertainty limit (%)").grid(row=1, column=0, pady=12)
    ttk.Entry(frame, textvariable=threshold, width=12).grid(row=1, column=1)
    ttk.Label(frame, wraplength=550, text="Automatic keeps a valid baseline at or below this fractional parallax uncertainty; otherwise it prefers the published geometric distance. This is an application policy, not proof of accuracy. Bayesian mode falls back explicitly when unavailable. Rerun to apply; cached catalogue inputs are reused. Loading saved results never recalculates them.").grid(row=2, column=0, columnspan=2, sticky="w")
    def apply():
        try:
            app.temperature_options = replace(app.temperature_options, distance_mode=mode.get(), distance_auto_threshold=float(threshold.get())/100)
        except ValueError as error:
            messagebox.showerror("Check distance settings", str(error), parent=window)
            return
        app.status.set("Distance settings saved; rerun to recalculate using cached inputs where available.")
        window.destroy()
    ttk.Button(frame, text="Apply to Subsequent Queries", command=apply).grid(row=3, column=1, pady=14)
    return window


def open_settings(app):
    window = tk.Toplevel(app.root)
    window.title("Temperature settings — applies to subsequent queries")
    frame = ttk.Frame(window, padding=16)
    frame.pack(fill="both", expand=True)
    values = asdict(app.temperature_options)
    variables = {}
    fields = (
        ("method", "BP−RP calibration", ("Casagrande2021", "Mucciarelli2021")),
        ("population", "Population hypothesis", ("auto", "dwarf", "giant")),
        ("population_reason", "Population evidence / provenance", None),
        ("metallicity_mode", "Composition input", ("solar", "trusted", "raw_gaia")),
        ("feh", "Trusted [Fe/H] (dex)", None),
        ("feh_error", "Trusted [Fe/H] error (optional)", None),
        ("metallicity_source", "Composition provenance", None),
        ("blue_metallicity_cutoff", "Blue solar-composition cutoff (BP−RP)", None),
        ("override", "Adopted source preference", ("auto", "Gaia GSP-Phot", "Gaia ESP-HS", "BP-RP")),
        ("override_reason", "Reason for overriding automatic choice", None),
        ("min_snr", "Minimum BP and RP S/N", None),
        ("excess_nsigma", "C* tolerance (sigma)", None),
        ("wide_interval", "Wide Gaia interval fraction", None),
        ("disagreement_k", "Disagreement threshold (K)", None),
        ("disagreement_fraction", "Disagreement fraction", None),
    )
    for row, (key, label, choices) in enumerate(fields):
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=3)
        variable = tk.StringVar(value="" if values[key] is None else str(values[key]))
        variables[key] = variable
        widget = ttk.Combobox(frame, textvariable=variable, values=choices, state="readonly", width=40) if choices else ttk.Entry(frame, textvariable=variable, width=43)
        widget.grid(row=row, column=1, sticky="ew")
    zero = tk.BooleanVar(value=values["zero_reddening"])
    vetted = tk.BooleanVar(value=values["metallicity_vetted"])
    fallback = tk.BooleanVar(value=values["allow_explorer_fallback"])
    row = len(fields)
    ttk.Checkbutton(frame, text="Use approximate Explorer BP-RP fallback when scientific temperatures are unavailable", variable=fallback).grid(row=row, column=0, columnspan=2, sticky="w", pady=3)
    row += 1
    ttk.Checkbutton(frame, text="I have vetted the supplied metallicity; provenance text alone is not validation", variable=vetted).grid(row=row, column=0, columnspan=2, sticky="w", pady=3)
    row += 1
    ttk.Checkbutton(frame, text="Explicitly assume zero reddening (provisional)", variable=zero).grid(row=row, column=0, columnspan=2, sticky="w", pady=8)
    ttk.Label(frame, text="Settings apply to subsequent single and bulk queries. Rerun an object to change its adoption.\nSolar composition is assumed by default. Raw Gaia M/H is not calibrated [Fe/H].\nOverrides apply only to eligible estimates and do not remove review flags.", wraplength=650).grid(row=row+1, column=0, columnspan=2, sticky="w")

    def apply():
        try:
            updated = {key: var.get().strip() for key, var in variables.items()}
            for key in ("feh", "feh_error", "blue_metallicity_cutoff", "min_snr", "excess_nsigma", "wide_interval", "disagreement_k", "disagreement_fraction"):
                updated[key] = float(updated[key]) if updated[key] else None
            updated["zero_reddening"] = zero.get()
            updated["metallicity_vetted"] = vetted.get()
            updated["allow_explorer_fallback"] = fallback.get()
            app.temperature_options = TemperatureOptions(**{**asdict(app.temperature_options), **updated})
        except (ValueError, TypeError) as error:
            messagebox.showerror("Check temperature settings", str(error), parent=window)
            return
        app.status.set("Temperature settings saved for subsequent queries; rerun to update displayed results.")
        window.destroy()
    ttk.Button(frame, text="Apply to Subsequent Queries", command=apply).grid(row=row+2, column=1, sticky="e", pady=(12, 0))
    return window


def load_saved_results(app):
    # Works whether the experiment was imported or launched as __main__.
    experiment = sys.modules[type(app).__module__]
    path = filedialog.askopenfilename(parent=app.root, title="Load results without recalculating",
        filetypes=(("Saved Gaia results", "*.json *.txt *.csv"), ("All files", "*.*")))
    if not path:
        return
    try:
        records = load_records(path, experiment.DISPLAY_COLUMNS)
        if not records:
            raise ValueError("The saved file has no result rows")
        app.query_cancel.set()
        app.query_generation += 1
        app.finish_query()
        if len(records) == 1 and "_analysis_data" not in records[0]:
            record = records[0]
            app.reset_sky_image()
            app.current_record = record
            for key, variable in app.result_vars.items():
                display = format_display_value(key, record.get(key))
                variable.set(display)
                app.update_result_value(key, display)
            app.update_row_visibility()
            app.gaia_code.set(str(record.get("source_id") or ""))
            app.status.set(f"Loaded {Path(path).name}; saved values preserved, no recalculation.")
        else:
            bulk = experiment.BulkQueryWindow(app)
            bulk.object_inputs = [str(row.get("_input_value") or row.get("source_id") or row.get("_analysis_data", {}).get("source_id") or i+1) for i, row in enumerate(records)]
            bulk.result_rows = []
            for row in records:
                data = row.get("_analysis_data", row)
                bulk.result_rows.append({**{key: format_display_value(key, data.get(key)) for key in experiment.DISPLAY_COLUMNS},
                    "_analysis_data": data, "_cluster_warning_reasons": row.get("_cluster_warning_reasons", experiment.cluster_analysis_warning_reasons(data)),
                    "_query_failed": row.get("_query_failed", False)})
            bulk.bulk_completed = True
            bulk.show_results_page()
            bulk.update_cluster_analysis_button()
            bulk.status.set(f"Loaded {len(records)} saved rows; original files unchanged.")
    except (OSError, ValueError, TypeError, KeyError) as error:
        messagebox.showerror("Could not load saved results", str(error), parent=app.root)
