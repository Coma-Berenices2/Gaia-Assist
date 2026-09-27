"""Standalone, exportable figures for the optional bulk cluster analysis.

Figures use Matplotlib's object API, so importing this module never starts a
GUI or selects a pyplot backend. The result dictionaries are prepared by the
cluster data helpers before the figures are built.
"""

import csv
import textwrap

from matplotlib.figure import Figure
from matplotlib.patches import Rectangle

from temperature_cluster_analysis import BROWN_DWARF_NOTE, LUMINOSITY_ROWS, SPECTRAL_COLUMNS
from scientist_distance import RAW_FIELDS, DERIVED_FIELDS
DISTANCE_EXPORT_FIELDS = (*RAW_FIELDS, *DERIVED_FIELDS)
from temperature_carbon import CARBON_FIELDS

LUMINOSITY_LABELS = [
    "White dwarf (WD)", "Subdwarf (VI)", "Main sequence (V)",
    "Subgiant (IV)", "Giant (III)", "Bright giant (II)", "Supergiant (I)",
]
CLEAN_COLOR = "#2069b0"
CONTAMINATED_COLOR = "#e38127"


def _stats(result):
    return result.get("stats", result)


def analysis_summary(result, kind):
    """Describe plotted and skipped objects using the data helper's totals."""
    stats = _stats(result)
    included = stats.get("included", len(result.get("points", [])))
    total = stats.get("total", included)
    label = "Ordinary-grid stars" if kind == "spectral" and any(result.get("carbon_counts", {}).values()) else "Included"
    pieces = [f"{label}: {included} of {total}"]
    skip_labels = [
        ("excluded_contaminated", "contaminated excluded"),
        ("missing", "missing usable data"),
        ("out_of_range", "outside plot limits"),
        ("failed", "failed queries"),
    ]
    for key, label in skip_labels:
        if stats.get(key, 0):
            pieces.append(f"{label}: {stats[key]}")
    if kind == "spectral" and stats.get("first_estimate_used", 0):
        pieces.append(f"first listed estimate used: {stats['first_estimate_used']}")
    if kind == "spectral" and result.get("status_counts"):
        pieces.append("Classification: " + ", ".join(f"{key} {value}" for key, value in result["status_counts"].items()))
    if kind == "spectral" and any(result.get("carbon_counts", {}).values()):
        pieces.append("Carbon chemistry counted separately; excluded from ordinary K/M cells")
    return "; ".join(pieces)


def _footer(result, kind, include_contaminated):
    choice = "included" if include_contaminated else "excluded"
    return "\n".join(textwrap.wrap(f"Contaminated stars: {choice}.  {analysis_summary(result, kind)}", 165 if kind == "spectral" else 100))


def build_cmd_figure(result, include_contaminated=False):
    """Plot each included star once; BP−RP increases from left to right.

    Each scatter artist stores its ordered source records in
    ``artist._cluster_points`` for the desktop's point selection handler.
    """
    fig = Figure(figsize=(8.7, 7.2), dpi=100, facecolor="white")
    ax = fig.add_subplot(111)
    fig.subplots_adjust(left=0.105, right=0.97, bottom=0.18, top=0.89)
    points = result.get("points", [])
    for contaminated, color, label in (
        (False, CLEAN_COLOR, "No contamination flag"),
        (True, CONTAMINATED_COLOR, "Contaminated (flagged)"),
    ):
        subset = [point for point in points if bool(point.get("contaminated")) == contaminated]
        if not subset:
            continue
        artist = ax.scatter(
            [point["new_bp_rp"] for point in subset],
            [point["absolute_magnitude"] for point in subset],
            s=30, c=color, alpha=0.8, edgecolors="white", linewidths=0.35,
            label=label, picker=5, zorder=3,
        )
        artist._cluster_points = subset
    ax.set_xlim(-1, 4)
    ax.set_ylim(15, -10)
    ax.set_xticks([-1, 0, 1, 2, 3, 4])
    ax.set_yticks([-10, -5, 0, 5, 10, 15])
    ax.set_xlabel("New BP−RP", fontsize=11, labelpad=9)
    ax.set_ylabel("Absolute Magnitude", fontsize=11, labelpad=9)
    ax.set_title("Cluster colour–magnitude diagram", fontsize=15, pad=17)
    ax.grid(True, color="#dfe6ed", linewidth=0.7, zorder=0)
    ax.set_axisbelow(True)
    if points:
        ax.legend(loc="best", fontsize=9, framealpha=0.95)
    else:
        ax.text(0.5, 0.5, "No stars meet the current filters and plot limits.",
                transform=ax.transAxes, ha="center", va="center", fontsize=11,
                color="#5b6874", wrap=True)
    fig.text(0.105, 0.09, textwrap.fill(_footer(result, "cmd", include_contaminated), 125),
             fontsize=8, color="#475569", ha="left", va="top")
    fig.text(0.105, 0.036,
             "Limits: −1 ≤ New BP−RP ≤ 4; −10 ≤ Absolute Magnitude ≤ 15.",
             fontsize=8, color="#475569", ha="left")
    return fig


def build_spectral_figure(result, include_contaminated=False):
    """Build a full, labelled 7 × 72 spectral/luminosity count matrix."""
    counts = result["counts"]
    if len(counts) != len(LUMINOSITY_ROWS) or any(
        len(row) != len(SPECTRAL_COLUMNS) for row in counts
    ):
        raise ValueError("Spectral counts must contain 7 luminosity rows and 72 columns.")
    fig = Figure(figsize=(24, 6), dpi=100, facecolor="white")
    ax = fig.add_subplot(111)
    fig.subplots_adjust(left=0.095, right=0.988, bottom=0.24, top=0.76)
    highest = max(1, max(value for row in counts for value in row))
    mesh = ax.imshow(counts, cmap="Blues", vmin=0, vmax=highest,
                     interpolation="nearest", aspect="auto", origin="upper")
    mesh._cluster_counts = counts
    for row_index, row in enumerate(counts):
        for column_index, value in enumerate(row):
            ax.text(column_index, row_index, str(int(value)),
                    ha="center", va="center", fontsize=8,
                    color="white" if value > highest * 0.55 else "#172b43")
    ax.set_xticks(range(len(SPECTRAL_COLUMNS)))
    ax.set_xticklabels(["WR"] + list("0123456789") * 7 + ["BD"], fontsize=8)
    ax.set_yticks(range(len(LUMINOSITY_ROWS)))
    ax.set_yticklabels(LUMINOSITY_LABELS, fontsize=10)
    ax.tick_params(axis="both", which="major", length=0, pad=8)
    ax.set_xticks([index - 0.5 for index in range(73)], minor=True)
    ax.set_yticks([index - 0.5 for index in range(8)], minor=True)
    ax.grid(which="minor", color="#cbd5e1", linewidth=0.5)
    ax.tick_params(which="minor", bottom=False, left=False)
    # The coloured bands and heavier boundaries make the ten subtypes per
    # spectral group legible without repeating the letter in every narrow cell.
    groups = [
        ("WR", -0.5, 1, "#d3b6f1"), ("O", 0.5, 10, "#9aaeea"),
        ("B", 10.5, 10, "#b8c9f3"), ("A", 20.5, 10, "#d9e5f5"),
        ("F", 30.5, 10, "#f1eccb"), ("G", 40.5, 10, "#f5db99"),
        ("K", 50.5, 10, "#efbd8b"), ("M", 60.5, 10, "#e9958e"),
        ("BD", 70.5, 1, "#bba89b"),
    ]
    for label, left, width, color in groups:
        ax.add_patch(Rectangle((left, 1.035), width, 0.1,
                               transform=ax.get_xaxis_transform(),
                               facecolor=color, edgecolor="white", clip_on=False))
        ax.text(left + width / 2, 1.085, label,
                transform=ax.get_xaxis_transform(), ha="center", va="center",
                fontsize=9 if width == 1 else 12, fontweight="bold", color="#25354a")
        ax.axvline(left, color="#8093a8", linewidth=1.1)
    ax.axvline(71.5, color="#8093a8", linewidth=1.1)
    ax.set_xlim(-0.5, 71.5)
    ax.set_ylim(6.5, -0.5)
    ax.set_xlabel("Spectral type / colour →  ·  Subtype 0–9 within each letter group",
                  fontsize=11, labelpad=13)
    ax.set_ylabel("Luminosity class", fontsize=11, labelpad=10)
    fig.suptitle("Estimated spectral type × luminosity class", x=0.54, y=0.94,
                 fontsize=17, fontweight="bold")
    fig.text(0.095, 0.11, _footer(result, "spectral", include_contaminated),
             fontsize=9, color="#475569", ha="left")
    fig.text(0.095, 0.065, "Each number is the star count in that intersecting classification; 0 means no stars.",
             fontsize=9, color="#475569", ha="left")
    if _stats(result).get("assumed_bd_v", 0):
        fig.text(0.095, 0.027, BROWN_DWARF_NOTE,
                 fontsize=8, color="#475569", ha="left")
    return fig


def save_analysis_csv(result, kind, path):
    """Save the plotted CMD records or the full spectral count matrix."""
    if kind not in ("cmd", "spectral"):
        raise ValueError("Analysis kind must be 'cmd' or 'spectral'.")
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        if kind == "cmd":
            columns = ["source_id", "new_bp_rp", "absolute_magnitude", "contaminated",
                       "classification_status", "temperature_status", "teff_gspphot",
                       "bp_rp_temperature", "effective_temperature", "adopted_temperature_source",
                       "temperature_selection_reason", *CARBON_FIELDS, *DISTANCE_EXPORT_FIELDS]
            writer.writerow(columns)
            for point in result.get("points", []):
                writer.writerow([point.get(key) for key in columns])
        else:
            writer.writerow(["luminosity_class"] + list(SPECTRAL_COLUMNS))
            for label, row in zip(LUMINOSITY_ROWS, result["counts"]):
                writer.writerow([label] + [int(value) for value in row])
            for category, matrix in result.get("status_matrices", {}).items():
                writer.writerow([])
                writer.writerow([category] + list(SPECTRAL_COLUMNS))
                for label, row in zip(LUMINOSITY_ROWS, matrix):
                    writer.writerow([label] + row)
            writer.writerow([])
            writer.writerow(["classification_status", "count"])
            writer.writerows(result.get("status_counts", {}).items())
            writer.writerow(["carbon_chemical_identification", "count"])
            writer.writerows(result.get("carbon_counts", {}).items())
            records = result.get("classification_records", [])
            if records:
                writer.writerow([])
                writer.writerow(list(records[0]))
                for row in records:
                    writer.writerow(list(row.values()))
