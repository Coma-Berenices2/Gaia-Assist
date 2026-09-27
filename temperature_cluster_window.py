"""Opt-in desktop charts for a completed bulk query."""

import logging
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from temperature_carbon import is_carbon
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from temperature_cluster_analysis import (
    LUMINOSITY_ROWS, SPECTRAL_COLUMNS, prepare_cmd_data, prepare_spectral_data,
)
from temperature_cluster_plots import (
    analysis_summary, build_cmd_figure, build_spectral_figure, save_analysis_csv,
)


LOGGER = logging.getLogger("gaia_assist_temperature")


class ClusterAnalysisWindow:
    def __init__(self, parent, rows):
        self.rows = deepcopy(rows)
        self.carbon_only = tk.BooleanVar(value=False)
        self.kind = None
        self.result = None
        self.figure = None
        self.figure_canvas = None
        self.plot_connections = []
        self.window = tk.Toplevel(parent)
        self.window.title("Advanced Cluster Analysis")
        self.window.geometry("1100x820")
        self.window.minsize(760, 560)
        self.window.transient(parent)
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(1, weight=1)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Destroy>", self.on_destroy, add="+")
        self.include_contaminated = tk.BooleanVar(self.window, value=False)
        self.summary = tk.StringVar(self.window, value="Choose a chart to begin.")
        self.detail = tk.StringVar(self.window, value="")

        header = ttk.Frame(self.window, padding=(18, 16, 18, 12))
        header.grid(row=0, column=0, sticky="ew")
        ttk.Label(header, text="Advanced Cluster Analysis", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(
            header, text=f"{len(self.rows)} bulk-query objects across all pages. Choose a chart:",
        ).pack(anchor="w", pady=(4, 10))
        choices = ttk.Frame(header)
        choices.pack(fill="x")
        self.cmd_button = ttk.Button(
            choices, text="1. Generate CMD", command=lambda: self.generate_chart("cmd"),
        )
        self.cmd_button.pack(side="left")
        self.spectral_button = ttk.Button(
            choices, text="2. Generate Spectral Counts", command=lambda: self.generate_chart("spectral"),
        )
        self.spectral_button.pack(side="left", padx=(8, 0))

        plot_frame = ttk.Frame(self.window, padding=(18, 0))
        plot_frame.grid(row=1, column=0, sticky="nsew")
        plot_frame.columnconfigure(0, weight=1)
        plot_frame.rowconfigure(0, weight=1)
        self.viewport = tk.Canvas(plot_frame, background="white", highlightthickness=0)
        self.viewport.grid(row=0, column=0, sticky="nsew")
        x_scroll = ttk.Scrollbar(plot_frame, orient="horizontal", command=self.viewport.xview)
        x_scroll.grid(row=1, column=0, sticky="ew")
        y_scroll = ttk.Scrollbar(plot_frame, orient="vertical", command=self.viewport.yview)
        y_scroll.grid(row=0, column=1, sticky="ns")
        self.viewport.configure(xscrollcommand=x_scroll.set, yscrollcommand=y_scroll.set)
        self.viewport.create_text(
            330, 160, text="Generate a CMD or a spectral-type count chart.\n\n"
            "Use the scrollbars to explore wide charts.",
            fill="#596575", font=("Segoe UI", 12), justify="center", width=550,
        )

        footer = ttk.Frame(self.window, padding=(18, 12, 18, 16))
        footer.grid(row=2, column=0, sticky="ew")
        filters = ttk.Frame(footer)
        filters.pack(fill="x")
        ttk.Checkbutton(filters, text="Carbon-star candidates", variable=self.carbon_only,
                        command=self.refresh_chart).pack(side="left", padx=(0, 12))
        ttk.Label(filters, text="Asterisk-flagged stars:").pack(side="left", padx=(0, 8))
        for text, value in (("Exclude", False), ("Include", True)):
            ttk.Radiobutton(
                filters, text=text, variable=self.include_contaminated, value=value,
                command=self.refresh_chart,
            ).pack(side="left", padx=(0, 10))
        self.summary_label = ttk.Label(footer, textvariable=self.summary, wraplength=1020)
        self.summary_label.pack(fill="x", pady=(8, 3))
        ttk.Label(footer, textvariable=self.detail, wraplength=1020, foreground="#365a80").pack(fill="x")
        actions = ttk.Frame(footer)
        actions.pack(fill="x", pady=(10, 0))
        self.save_chart_button = ttk.Button(actions, text="Save Chart…", command=self.save_chart, state="disabled")
        self.save_chart_button.pack(side="left")
        self.save_data_button = ttk.Button(actions, text="Save Chart Data (CSV)…", command=self.save_data, state="disabled")
        self.save_data_button.pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Close", command=self.close).pack(side="right")

    def refresh_chart(self):
        if self.kind is not None:
            self.generate_chart(self.kind)

    def generate_chart(self, kind):
        included = self.include_contaminated.get()
        rows = [row for row in self.rows if not self.carbon_only.get() or is_carbon(row)]
        self.window.configure(cursor="watch")
        self.window.update_idletasks()
        try:
            if kind == "cmd":
                result = prepare_cmd_data(rows, include_contaminated=included)
                figure = build_cmd_figure(result, include_contaminated=included)
            else:
                result = prepare_spectral_data(rows, include_contaminated=included)
                figure = build_spectral_figure(result, include_contaminated=included)
            self.dispose_plot()
            self.viewport.delete("all")
            self.figure = figure
            self.kind = kind
            self.result = result
            self.figure_canvas = FigureCanvasTkAgg(figure, master=self.viewport)
            width, height = (int(size * figure.dpi) for size in figure.get_size_inches())
            self.viewport.create_window(
                (0, 0), window=self.figure_canvas.get_tk_widget(), anchor="nw", width=width, height=height,
            )
            self.viewport.configure(scrollregion=(0, 0, width, height))
            self.viewport.xview_moveto(0)
            self.viewport.yview_moveto(0)
            self.plot_connections = [
                self.figure_canvas.mpl_connect("pick_event", self.on_pick),
                self.figure_canvas.mpl_connect("motion_notify_event", self.on_motion),
            ]
            self.figure_canvas.draw()
            self.summary.set(analysis_summary(result, kind))
            self.detail.set(
                "Click a point to see its Source ID and plotted values."
                if kind == "cmd" else "Scroll horizontally for all spectral types; hover over a cell for its count."
            )
            self.save_chart_button.configure(state="normal")
            self.save_data_button.configure(state="normal")
        except Exception as error:
            LOGGER.exception("Generating cluster chart failed")
            self.dispose_plot()
            self.viewport.delete("all")
            self.kind = None
            self.result = None
            self.summary.set("Chart could not be generated. Choose a chart to try again.")
            self.save_chart_button.configure(state="disabled")
            self.save_data_button.configure(state="disabled")
            messagebox.showerror("Chart could not be generated", str(error), parent=self.window)
        finally:
            self.window.configure(cursor="")

    def on_pick(self, event):
        points = getattr(event.artist, "_cluster_points", ())
        if len(event.ind) and points:
            point = points[int(event.ind[0])]
            self.detail.set(
                f"Source ID: {point['source_id']} | New BP−RP: {point['new_bp_rp']:.6g} | "
                f"Absolute Magnitude: {point['absolute_magnitude']:.6g}"
                + (" | Asterisk-flagged" if point["contaminated"] else "")
            )

    def on_motion(self, event):
        if self.kind != "spectral" or event.inaxes is not self.figure.axes[0]:
            return
        if event.xdata is None or event.ydata is None:
            return
        column, row = int(event.xdata + 0.5), int(event.ydata + 0.5)
        if 0 <= row < len(LUMINOSITY_ROWS) and 0 <= column < len(SPECTRAL_COLUMNS):
            count = self.result["counts"][row][column]
            breakdown = ", ".join(f"{name}: {matrix[row][column]}" for name, matrix in self.result.get("status_matrices", {}).items())
            self.detail.set(f"{SPECTRAL_COLUMNS[column]} × {LUMINOSITY_ROWS[row]}: {count} objects | {breakdown}")

    def default_filename(self):
        policy = "including_flagged" if self.include_contaminated.get() else "excluding_flagged"
        return f"cluster_{self.kind}_{policy}_{datetime.now():%Y%m%d_%H%M%S}"

    def save_chart(self):
        if self.figure is None:
            return
        path = filedialog.asksaveasfilename(
            parent=self.window, title="Save cluster chart", initialfile=self.default_filename(),
            defaultextension=".png", filetypes=[("PNG image", "*.png"), ("PDF document", "*.pdf"), ("SVG image", "*.svg")],
        )
        if not path:
            return
        try:
            if Path(path).suffix.lower() not in (".png", ".pdf", ".svg"):
                raise ValueError("Choose a PNG, PDF, or SVG filename.")
            self.figure.savefig(path, dpi=200, bbox_inches="tight", facecolor="white")
            self.detail.set(f"Chart saved to {path}")
        except Exception as error:
            LOGGER.exception("Saving cluster chart failed")
            messagebox.showerror("Save failed", str(error), parent=self.window)

    def save_data(self):
        if self.result is None:
            return
        path = filedialog.asksaveasfilename(
            parent=self.window, title="Save plotted data", initialfile=self.default_filename(),
            defaultextension=".csv", filetypes=[("CSV data", "*.csv")],
        )
        if not path:
            return
        try:
            save_analysis_csv(self.result, self.kind, path)
            self.detail.set(f"Chart data saved to {path}")
        except Exception as error:
            LOGGER.exception("Saving cluster chart data failed")
            messagebox.showerror("Save failed", str(error), parent=self.window)

    def dispose_plot(self):
        if self.figure_canvas is not None:
            for connection in self.plot_connections:
                self.figure_canvas.mpl_disconnect(connection)
            widget = self.figure_canvas.get_tk_widget()
            # Cancel TkAgg's pending resize redraw on the widget that registered it.
            idle_draw = getattr(self.figure_canvas, "_idle_draw_id", None)
            if idle_draw is not None:
                widget.after_cancel(idle_draw)
                self.figure_canvas._idle_draw_id = None
            widget.destroy()
            self.figure_canvas = None
        if self.figure is not None:
            self.figure.clear()
            self.figure = None
        self.plot_connections = []

    def on_destroy(self, event):
        if event.widget is self.window:
            # Child Tk widgets have already been destroyed when the parent closes.
            if self.figure_canvas is not None:
                for connection in self.plot_connections:
                    self.figure_canvas.mpl_disconnect(connection)
            self.figure_canvas = None
            self.figure = None
            self.plot_connections = []

    def close(self):
        self.dispose_plot()
        self.window.destroy()
