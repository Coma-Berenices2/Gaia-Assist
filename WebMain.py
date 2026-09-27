import html
import json
import os
import re
import socket
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import Main


HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", os.environ.get("GAIA_ASSIST_PORT", "65000")))
RENDER_ASSIGNED_PORT = "PORT" in os.environ


def build_display_data(source_data, derived_data):
    display_data = {column_name: None for column_name in Main.DISPLAY_COLUMNS}
    display_data.update(source_data)
    display_data.update(derived_data)
    return display_data


def format_display_rows(display_data):
    rows = []
    for column_name, label in Main.DISPLAY_COLUMNS.items():
        value = display_data.get(column_name)
        rows.append(
            {
                "key": column_name,
                "field": label,
                "value": "-" if value is None else str(value),
                "unit": Main.FIELD_UNITS.get(column_name, "") or "-",
                "isSecondary": column_name in Main.SECONDARY_DISPLAY_COLUMNS,
                "isGaia": column_name in Main.GAIA_COLUMNS,
                "isDerived": column_name in Main.DERIVED_COLUMNS,
            }
        )
    return rows


def run_query(source_id, release):
    source_data = Main.fetch_gaia_source_data(source_id, release)
    Main.log_missing_values(source_id, source_data)
    derived_data = Main.calculate_derived_data(source_data)
    display_data = build_display_data(source_data, derived_data)
    warnings = Main.collect_pipeline_warnings(source_data, derived_data)

    matched_source_id = display_data["source_id"]
    if release == "DR3":
        status = f"Loaded Gaia DR3 source {matched_source_id}."
    elif release == Main.COMMON_NAME_RELEASE:
        status = (
            f'Loaded DR3 source {matched_source_id} resolved from common name '
            f'"{source_id}".'
        )
    else:
        status = (
            f"Loaded DR3 counterpart {matched_source_id} for "
            f"{release} source {source_id}."
        )

    if warnings:
        status = f"{status[:-1]}; {'; '.join(warnings)}. See debug log."

    return {
        "status": status,
        "sourceId": "-" if matched_source_id is None else str(matched_source_id),
        "rows": format_display_rows(display_data),
    }


def chunk_sequence(values, size):
    for start in range(0, len(values), size):
        yield values[start:start + size]


def build_bulk_result_row(object_id, release, selected_columns, batch_data, batch_errors):
    try:
        if object_id in batch_errors:
            raise batch_errors[object_id]
        source_data = batch_data[object_id]
        Main.log_missing_values(object_id, source_data)
        derived_data = Main.calculate_derived_data(source_data)
        display_data = build_display_data(source_data, derived_data)
        return {
            column_name: (
                "-"
                if display_data.get(column_name) is None
                else str(display_data.get(column_name))
            )
            for column_name in selected_columns
        }, None
    except Exception as error:
        Main.LOGGER.exception(
            "Web bulk query failed for release=%s object=%s",
            release,
            object_id,
        )
        row = {column_name: "-" for column_name in selected_columns}
        if selected_columns:
            row[selected_columns[0]] = f"ERROR: {object_id}"
        return row, str(error)


def fetch_batch_sequentially(batch, release, batch_error):
    batch_data = {}
    batch_errors = {}
    for object_id in batch:
        try:
            batch_data[object_id] = Main.fetch_gaia_source_data(object_id, release)
        except Exception as error:
            batch_errors[object_id] = error

    if not batch_data and not batch_errors:
        for object_id in batch:
            batch_errors[object_id] = batch_error

    return batch_data, batch_errors


def run_bulk_query(objects, release, selected_columns):
    result_rows = []
    errors = []

    for batch in chunk_sequence(objects, Main.BULK_GAIA_BATCH_SIZE):
        try:
            batch_data, batch_errors = Main.fetch_gaia_source_data_batch(batch, release)
        except Exception as error:
            Main.LOGGER.exception(
                "Web bulk Gaia batch failed for release=%s batch=%s",
                release,
                batch,
            )
            batch_data, batch_errors = fetch_batch_sequentially(
                batch,
                release,
                error,
            )

        worker_count = min(Main.BULK_CALCULATION_WORKERS, max(len(batch), 1))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [
                executor.submit(
                    build_bulk_result_row,
                    object_id,
                    release,
                    selected_columns,
                    batch_data,
                    batch_errors,
                )
                for object_id in batch
            ]
            for object_id, future in zip(batch, futures):
                row, error = future.result()
                result_rows.append(row)
                if error is not None:
                    errors.append({"object": object_id, "error": error})

    return {
        "status": (
            f"Bulk query finished. Loaded {len(result_rows)} rows "
            f"in Gaia batches of up to {Main.BULK_GAIA_BATCH_SIZE}."
        ),
        "rows": result_rows,
        "errors": errors,
    }


def save_rows(rows, object_key, input_mode, input_value):
    Main.SAVED_OBJECTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now()
    safe_object_key = re.sub(r"[^A-Za-z0-9_-]+", "_", object_key).strip("_")
    if not safe_object_key:
        safe_object_key = "unknown_object"

    saved_file = Main.SAVED_OBJECTS_DIR / (
        f"gaia_{safe_object_key}_{timestamp:%Y%m%d_%H%M%S_%f}.txt"
    )

    with saved_file.open("w", encoding="utf-8") as output_file:
        output_file.write("Gaia Assist Saved Object Data\n")
        output_file.write(f"Saved At: {timestamp.isoformat(timespec='seconds')}\n")
        output_file.write(f"Input Mode: {input_mode}\n")
        output_file.write(f"Input Value: {input_value}\n")
        output_file.write("\n")
        output_file.write("Field\tValue\tUnit\n")

        for row in rows:
            field = row.get("field") or "-"
            value = row.get("value") or "-"
            unit = row.get("unit") or "-"
            output_file.write(f"{field}\t{value}\t{unit}\n")

    return saved_file


def save_bulk_rows(rows, selected_columns, input_mode, input_values):
    Main.SAVED_OBJECTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now()
    saved_file = Main.SAVED_OBJECTS_DIR / (
        f"gaia_bulk_{timestamp:%Y%m%d_%H%M%S_%f}.txt"
    )

    with saved_file.open("w", encoding="utf-8") as output_file:
        output_file.write("Gaia Assist Bulk Query Data\n")
        output_file.write(f"Saved At: {timestamp.isoformat(timespec='seconds')}\n")
        output_file.write(f"Input Mode: {input_mode}\n")
        output_file.write(f"Input Count: {len(input_values)}\n")
        output_file.write(f"Result Count: {len(rows)}\n")
        output_file.write("\n")
        headers = ["Input Row"] + [
            Main.DISPLAY_COLUMNS[column_name] for column_name in selected_columns
        ]
        units = ["-"] + [
            Main.FIELD_UNITS.get(column_name, "-") or "-"
            for column_name in selected_columns
        ]
        output_file.write("\t".join(headers) + "\n")
        output_file.write("\t".join(units) + "\n")

        for index, row in enumerate(rows):
            input_value = input_values[index] if index < len(input_values) else "-"
            values = [input_value]
            values.extend(row.get(column_name, "-") for column_name in selected_columns)
            output_file.write("\t".join(values) + "\n")

    return saved_file


def make_page():
    config = {
        "columns": Main.DISPLAY_COLUMNS,
        "fieldExplanations": Main.FIELD_EXPLANATIONS,
        "helpTutorial": Main.HELP_TUTORIAL,
        "bulkQueryGuide": Main.BULK_QUERY_GUIDE,
        "units": Main.FIELD_UNITS,
        "secondaryColumns": list(Main.SECONDARY_DISPLAY_COLUMNS),
        "gaiaColumns": list(Main.GAIA_COLUMNS),
        "derivedColumns": list(Main.DERIVED_COLUMNS),
        "primaryColumns": list(Main.PRIMARY_DISPLAY_ORDER),
        "bulkBatchSize": Main.BULK_GAIA_BATCH_SIZE,
        "commonNameRelease": Main.COMMON_NAME_RELEASE,
        "warningMessages": {
            "excess_noise_factor": (
                "The Excess Noise Factor observed of this celestial object might be "
                "abnormal. This can be caused by a hidden binary or companion stars, "
                'an exoplanet, or an unexplained "wobble".'
            ),
            "bp_rp_excess_correctness": (
                "Often seen in heavily obscured or red objects where the blue photons "
                "are entirely swallowed by dust/extinction, preventing an accurate "
                "BP measurement."
            ),
            "star_type": (
                "A luminosity class VI result indicates that the object may be either "
                "a poor main-sequence star (subdwarf) or a white dwarf."
            ),
        },
    }
    config_json = json.dumps(config)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Gaia Assist Web</title>
  <style>
    :root {{
      color-scheme: light;
      --border: #d8dde5;
      --ink: #172033;
      --muted: #5b6473;
      --blue: #0b63ce;
      --surface: #ffffff;
      --soft: #f5f7fa;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", Arial, sans-serif;
      color: var(--ink);
      background: #eef2f6;
    }}
    main {{
      max-width: 1080px;
      margin: 0 auto;
      padding: 24px;
    }}
    h1 {{
      margin: 0 0 4px;
      font-size: 30px;
      line-height: 1.15;
    }}
    .subtle {{
      margin: 0 0 18px;
      color: var(--muted);
    }}
    .controls {{
      display: grid;
      grid-template-columns: max-content minmax(220px, 1fr) max-content max-content;
      gap: 10px;
      align-items: center;
      margin-bottom: 10px;
    }}
    label {{ font-weight: 600; }}
    input, select, button {{
      font: inherit;
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 8px 10px;
      background: var(--surface);
    }}
    button {{
      cursor: pointer;
      background: #172033;
      border-color: #172033;
      color: white;
    }}
    button:disabled {{
      cursor: wait;
      opacity: 0.65;
    }}
    .options {{
      display: flex;
      justify-content: space-between;
      gap: 14px;
      align-items: center;
      margin: 8px 0 14px;
    }}
    .checkbox {{
      display: inline-flex;
      gap: 8px;
      align-items: center;
      color: var(--muted);
      font-weight: 400;
    }}
    .checkbox input {{ width: 16px; height: 16px; }}
    .button-row {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      align-items: center;
    }}
    .panel {{
      display: none;
      margin: 12px 0 16px;
      padding: 14px;
      border: 1px solid var(--border);
      background: var(--surface);
    }}
    .panel.active {{ display: block; }}
    .bulk-grid {{
      display: grid;
      grid-template-columns: 1fr max-content;
      gap: 10px;
      align-items: start;
    }}
    textarea {{
      width: 100%;
      min-height: 170px;
      resize: vertical;
      font: 13px Consolas, monospace;
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 10px;
    }}
    .field-tiles {{
      display: grid;
      grid-template-columns: repeat(5, minmax(150px, 1fr));
      gap: 6px;
      margin: 10px 0;
    }}
    .field-tile {{
      display: grid;
      grid-template-columns: max-content 1fr;
      gap: 5px;
      align-items: center;
      min-height: 30px;
      padding: 4px 6px;
      border: 1px solid var(--border);
      background: #f9fafc;
      cursor: grab;
      font-size: 12px;
    }}
    .field-tile:active {{ cursor: grabbing; }}
    .field-tile.drag-over {{ outline: 2px solid var(--blue); }}
    .field-tile span {{
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    .bulk-table th, .bulk-table td {{
      white-space: nowrap;
      min-width: 150px;
    }}
    .pager {{
      display: flex;
      justify-content: space-between;
      gap: 10px;
      align-items: center;
      margin-top: 10px;
    }}
    #status {{
      min-height: 24px;
      margin: 0 0 12px;
      color: var(--muted);
    }}
    .table-wrap {{
      overflow: auto;
      border: 1px solid var(--border);
      background: var(--surface);
    }}
    table {{
      width: 100%;
      min-width: 760px;
      border-collapse: collapse;
    }}
    th, td {{
      padding: 8px 10px;
      border-bottom: 1px solid var(--border);
      text-align: left;
      vertical-align: top;
    }}
    th {{
      position: sticky;
      top: 0;
      z-index: 1;
      background: var(--soft);
      font-weight: 700;
    }}
    td {{
      user-select: text;
      white-space: pre-wrap;
    }}
    .field-button {{
      padding: 0;
      border: 0;
      background: transparent;
      color: inherit;
      font: inherit;
      text-align: left;
      cursor: pointer;
    }}
    .field-button:hover, .warning-link:hover {{ text-decoration: underline; }}
    .warning-link {{
      color: inherit;
      cursor: pointer;
    }}
    .warning-star {{ color: var(--blue); }}
    .field-preview {{
      position: fixed;
      z-index: 20;
      display: none;
      max-width: 380px;
      padding: 9px 11px;
      border: 1px solid #172033;
      border-radius: 6px;
      background: #172033;
      color: #ffffff;
      font-size: 13px;
      line-height: 1.35;
      box-shadow: 0 10px 30px rgba(23, 32, 51, 0.22);
      pointer-events: none;
    }}
    .hidden {{ display: none; }}
    dialog {{
      border: 1px solid var(--border);
      border-radius: 8px;
      width: min(440px, calc(100vw - 38px));
      padding: 0;
      box-shadow: 0 18px 60px rgba(23, 32, 51, 0.24);
    }}
    dialog::backdrop {{ background: rgba(23, 32, 51, 0.22); }}
    .dialog-body {{ padding: 18px 20px 16px; }}
    .dialog-body h2 {{ margin: 0 0 10px; font-size: 18px; }}
    .dialog-body p {{
      margin: 0 0 16px;
      user-select: text;
      white-space: pre-wrap;
    }}
    @media (max-width: 760px) {{
      main {{ padding: 16px; }}
      .controls {{ grid-template-columns: 1fr; }}
      .options {{ align-items: stretch; flex-direction: column; }}
      .bulk-grid {{ grid-template-columns: 1fr; }}
      .field-tiles {{ grid-template-columns: repeat(2, minmax(140px, 1fr)); }}
      button {{ width: 100%; }}
    }}
  </style>
</head>
<body>
  <main>
    <h1>Gaia Assist 1.1</h1>
    <p class="subtle">Fetch core astrometric and photometric values from ESA Gaia.</p>

    <form id="queryForm" class="controls">
      <label id="inputLabel" for="sourceInput">Gaia Code</label>
      <input id="sourceInput" autocomplete="off" required>
      <select id="releaseSelect">
        <option>DR3</option>
        <option>DR2</option>
        <option>DR1</option>
        <option>{html.escape(Main.COMMON_NAME_RELEASE)}</option>
      </select>
      <button id="queryButton" type="submit">Start Query</button>
    </form>

    <div class="options">
      <label class="checkbox">
        <input id="hideGaiaData" type="checkbox">
        Hide Gaia Data
      </label>
      <label class="checkbox">
        <input id="hideDerivedData" type="checkbox">
        Hide Derived Data
      </label>
      <div>
        <button id="bulkToggleButton" type="button">Bulk Query</button>
        <button id="saveButton" type="button">Save</button>
        <button id="helpButton" type="button">Help</button>
      </div>
    </div>

    <section id="bulkPanel" class="panel">
      <h2>Bulk Query</h2>
      <div class="bulk-grid">
        <div>
          <label for="bulkInput">Object rows</label>
          <textarea id="bulkInput" placeholder="One object per row"></textarea>
        </div>
        <div class="button-row">
          <select id="bulkReleaseSelect">
            <option>DR3</option>
            <option>DR2</option>
            <option>DR1</option>
            <option>{html.escape(Main.COMMON_NAME_RELEASE)}</option>
          </select>
          <input id="bulkFileInput" type="file" accept=".txt,.csv,text/plain">
          <button id="bulkGuideButton" type="button">Guide</button>
          <button id="showBulkInputButton" type="button">Show Input Rows</button>
        </div>
      </div>
      <p class="subtle">Check fields to include. Drag compact blocks; final order reads left to right, top to bottom.</p>
      <div id="bulkFieldTiles" class="field-tiles"></div>
      <div class="button-row">
        <button id="bulkPrimaryButton" type="button">Select Primary Rows</button>
        <button id="bulkSelectAllButton" type="button">Select All</button>
        <button id="bulkRunButton" type="button">Run Bulk Query</button>
        <button id="bulkSaveButton" type="button">Save Bulk Results</button>
      </div>
      <p id="bulkStatus" class="subtle">Gaia source-table lookups run in batches of {Main.BULK_GAIA_BATCH_SIZE}.</p>
      <div class="table-wrap">
        <table id="bulkResultsTable" class="bulk-table">
          <thead id="bulkResultsHead"></thead>
          <tbody id="bulkResultsBody"></tbody>
        </table>
      </div>
      <div class="pager">
        <button id="bulkPrevButton" type="button">Previous Page</button>
        <div class="button-row">
          <span>Rows per page</span>
          <label class="checkbox"><input name="bulkPageSize" type="radio" value="10" checked>10</label>
          <label class="checkbox"><input name="bulkPageSize" type="radio" value="20">20</label>
          <label class="checkbox"><input name="bulkPageSize" type="radio" value="30">30</label>
        </div>
        <span id="bulkPageStatus">Page 1 of 1</span>
        <button id="bulkNextButton" type="button">Next Page</button>
      </div>
    </section>

    <p id="status">Enter a Gaia source_id to begin.</p>

    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Field</th>
            <th>Value</th>
            <th>Unit</th>
          </tr>
        </thead>
        <tbody id="resultsBody"></tbody>
      </table>
    </div>
  </main>

  <dialog id="infoDialog">
    <div class="dialog-body">
      <h2 id="dialogTitle"></h2>
      <p id="dialogMessage"></p>
      <button id="dialogClose" type="button">OK</button>
    </div>
  </dialog>
  <div id="fieldPreview" class="field-preview"></div>

  <script>
    const config = {config_json};
    const queryForm = document.querySelector("#queryForm");
    const inputLabel = document.querySelector("#inputLabel");
    const sourceInput = document.querySelector("#sourceInput");
    const releaseSelect = document.querySelector("#releaseSelect");
    const queryButton = document.querySelector("#queryButton");
    const saveButton = document.querySelector("#saveButton");
    const helpButton = document.querySelector("#helpButton");
    const hideGaiaData = document.querySelector("#hideGaiaData");
    const hideDerivedData = document.querySelector("#hideDerivedData");
    const bulkToggleButton = document.querySelector("#bulkToggleButton");
    const bulkPanel = document.querySelector("#bulkPanel");
    const bulkInput = document.querySelector("#bulkInput");
    const bulkReleaseSelect = document.querySelector("#bulkReleaseSelect");
    const bulkFileInput = document.querySelector("#bulkFileInput");
    const bulkGuideButton = document.querySelector("#bulkGuideButton");
    const showBulkInputButton = document.querySelector("#showBulkInputButton");
    const bulkFieldTiles = document.querySelector("#bulkFieldTiles");
    const bulkPrimaryButton = document.querySelector("#bulkPrimaryButton");
    const bulkSelectAllButton = document.querySelector("#bulkSelectAllButton");
    const bulkRunButton = document.querySelector("#bulkRunButton");
    const bulkSaveButton = document.querySelector("#bulkSaveButton");
    const bulkStatus = document.querySelector("#bulkStatus");
    const bulkResultsHead = document.querySelector("#bulkResultsHead");
    const bulkResultsBody = document.querySelector("#bulkResultsBody");
    const bulkPrevButton = document.querySelector("#bulkPrevButton");
    const bulkNextButton = document.querySelector("#bulkNextButton");
    const bulkPageStatus = document.querySelector("#bulkPageStatus");
    const statusLine = document.querySelector("#status");
    const resultsBody = document.querySelector("#resultsBody");
    const dialog = document.querySelector("#infoDialog");
    const dialogTitle = document.querySelector("#dialogTitle");
    const dialogMessage = document.querySelector("#dialogMessage");
    const dialogClose = document.querySelector("#dialogClose");
    const fieldPreview = document.querySelector("#fieldPreview");

    let currentRows = [];
    let lastSavedObjectKey = null;
    let bulkColumnOrder = Object.keys(config.columns);
    let bulkSelectedColumns = new Set(config.primaryColumns);
    let draggedBulkColumn = null;
    let bulkResultRows = [];
    let bulkInputRows = [];
    let bulkCurrentPage = 0;

    function showDialog(title, message) {{
      hideFieldPreview();
      dialogTitle.textContent = title;
      dialogMessage.textContent = message || "Explanation not added yet.";
      dialog.showModal();
    }}

    function showFieldPreview(button, key) {{
      fieldPreview.textContent = config.fieldExplanations[key] || "Explanation not added yet.";
      fieldPreview.style.display = "block";
      const buttonRect = button.getBoundingClientRect();
      const previewRect = fieldPreview.getBoundingClientRect();
      let left = buttonRect.left;
      let top = buttonRect.top - previewRect.height - 8;
      if (top < 4) {{
        top = buttonRect.bottom + 8;
      }}
      left = Math.max(4, Math.min(left, window.innerWidth - previewRect.width - 4));
      fieldPreview.style.left = `${{left}}px`;
      fieldPreview.style.top = `${{top}}px`;
    }}

    function hideFieldPreview() {{
      fieldPreview.style.display = "none";
    }}

    function renderWarningValue(row) {{
      const warning = config.warningMessages[row.key];
      if (!warning || !row.value.includes("*")) {{
        return document.createTextNode(row.value);
      }}

      const link = document.createElement("span");
      link.className = "warning-link";
      const textPart = row.value.replaceAll("*", "").trimEnd();
      link.append(document.createTextNode(textPart + " "));
      const star = document.createElement("span");
      star.className = "warning-star";
      star.textContent = "*";
      link.append(star);
      link.addEventListener("click", () => showDialog(row.field, warning));
      return link;
    }}

    function renderRows(rows) {{
      currentRows = rows;
      resultsBody.textContent = "";
      for (const row of rows) {{
        const tr = document.createElement("tr");
        tr.dataset.key = row.key;
        if ((row.isGaia && hideGaiaData.checked) || (row.isDerived && hideDerivedData.checked)) {{
          tr.classList.add("hidden");
        }}

        const fieldCell = document.createElement("td");
        const fieldButton = document.createElement("button");
        fieldButton.type = "button";
        fieldButton.className = "field-button";
        fieldButton.textContent = row.field;
        fieldButton.addEventListener("mouseenter", () => showFieldPreview(fieldButton, row.key));
        fieldButton.addEventListener("mouseleave", hideFieldPreview);
        fieldButton.addEventListener("focus", () => showFieldPreview(fieldButton, row.key));
        fieldButton.addEventListener("blur", hideFieldPreview);
        fieldButton.addEventListener("click", () => {{
          showDialog(row.field, config.fieldExplanations[row.key] || "");
        }});
        fieldCell.append(fieldButton);

        const valueCell = document.createElement("td");
        valueCell.append(renderWarningValue(row));

        const unitCell = document.createElement("td");
        unitCell.textContent = row.unit || "-";

        tr.append(fieldCell, valueCell, unitCell);
        resultsBody.append(tr);
      }}
    }}

    function compactLabel(label) {{
      return label.length <= 23 ? label : `${{label.slice(0, 20)}}...`;
    }}

    function renderBulkFieldTiles() {{
      bulkFieldTiles.textContent = "";
      for (const key of bulkColumnOrder) {{
        const tile = document.createElement("label");
        tile.className = "field-tile";
        tile.draggable = true;
        tile.dataset.key = key;
        tile.title = config.columns[key];

        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.checked = bulkSelectedColumns.has(key);
        checkbox.addEventListener("change", () => {{
          if (checkbox.checked) {{
            bulkSelectedColumns.add(key);
          }} else {{
            bulkSelectedColumns.delete(key);
          }}
        }});

        const text = document.createElement("span");
        text.textContent = compactLabel(config.columns[key]);

        tile.addEventListener("dragstart", () => {{
          draggedBulkColumn = key;
        }});
        tile.addEventListener("dragover", (event) => {{
          event.preventDefault();
          tile.classList.add("drag-over");
        }});
        tile.addEventListener("dragleave", () => tile.classList.remove("drag-over"));
        tile.addEventListener("drop", (event) => {{
          event.preventDefault();
          tile.classList.remove("drag-over");
          if (!draggedBulkColumn || draggedBulkColumn === key) {{
            return;
          }}
          const fromIndex = bulkColumnOrder.indexOf(draggedBulkColumn);
          const toIndex = bulkColumnOrder.indexOf(key);
          bulkColumnOrder.splice(fromIndex, 1);
          bulkColumnOrder.splice(toIndex, 0, draggedBulkColumn);
          draggedBulkColumn = null;
          renderBulkFieldTiles();
          renderBulkResults();
        }});

        tile.append(checkbox, text);
        bulkFieldTiles.append(tile);
      }}
    }}

    function selectedBulkColumns() {{
      return bulkColumnOrder.filter((key) => bulkSelectedColumns.has(key));
    }}

    function parseBulkInputRows() {{
      return bulkInput.value
        .split(/\\r?\\n/)
        .map((row) => row.trim())
        .filter(Boolean);
    }}

    function renderBulkResults() {{
      const columns = selectedBulkColumns();
      bulkResultsHead.textContent = "";
      bulkResultsBody.textContent = "";

      const headerRow = document.createElement("tr");
      for (const key of columns) {{
        const th = document.createElement("th");
        const unit = config.units[key] && config.units[key] !== "unitless"
          ? ` (${{config.units[key]}})`
          : "";
        th.textContent = `${{config.columns[key]}}${{unit}}`;
        headerRow.append(th);
      }}
      bulkResultsHead.append(headerRow);

      const pageSize = Number(document.querySelector("input[name='bulkPageSize']:checked").value);
      const totalPages = Math.max(1, Math.ceil(bulkResultRows.length / pageSize));
      bulkCurrentPage = Math.min(bulkCurrentPage, totalPages - 1);
      const start = bulkCurrentPage * pageSize;
      const pageRows = bulkResultRows.slice(start, start + pageSize);

      for (const row of pageRows) {{
        const tr = document.createElement("tr");
        for (const key of columns) {{
          const td = document.createElement("td");
          td.textContent = row[key] || "-";
          td.addEventListener("dblclick", () => {{
            navigator.clipboard.writeText(td.textContent);
            bulkStatus.textContent = `Copied: ${{td.textContent}}`;
          }});
          tr.append(td);
        }}
        bulkResultsBody.append(tr);
      }}

      bulkPageStatus.textContent = `Page ${{bulkCurrentPage + 1}} of ${{totalPages}}`;
      bulkPrevButton.disabled = bulkCurrentPage <= 0;
      bulkNextButton.disabled = bulkCurrentPage >= totalPages - 1;
    }}

    function renderEmptyRows() {{
      const rows = Object.entries(config.columns).map(([key, field]) => ({{
        key,
        field,
        value: "-",
        unit: config.units[key] || "-",
        isSecondary: config.secondaryColumns.includes(key),
        isGaia: config.gaiaColumns.includes(key),
        isDerived: config.derivedColumns.includes(key),
      }}));
      renderRows(rows);
    }}

    releaseSelect.addEventListener("change", () => {{
      inputLabel.textContent = releaseSelect.value === config.commonNameRelease
        ? "Common Name"
        : "Gaia Code";
    }});

    hideGaiaData.addEventListener("change", () => renderRows(currentRows));
    hideDerivedData.addEventListener("change", () => renderRows(currentRows));

    bulkToggleButton.addEventListener("click", () => {{
      bulkPanel.classList.toggle("active");
    }});

    bulkFileInput.addEventListener("change", async () => {{
      const file = bulkFileInput.files[0];
      if (!file) {{
        return;
      }}
      bulkInput.value = await file.text();
      bulkStatus.textContent = `Loaded ${{file.name}}.`;
    }});

    bulkGuideButton.addEventListener("click", () => {{
      showDialog("Bulk Query Guide", config.bulkQueryGuide);
    }});

    showBulkInputButton.addEventListener("click", () => {{
      showDialog("Bulk Query Input Rows", parseBulkInputRows().join("\\n") || "No rows entered yet.");
    }});

    bulkPrimaryButton.addEventListener("click", () => {{
      bulkSelectedColumns = new Set(config.primaryColumns);
      bulkColumnOrder = [
        ...config.primaryColumns.filter((key) => bulkColumnOrder.includes(key)),
        ...bulkColumnOrder.filter((key) => !config.primaryColumns.includes(key)),
      ];
      renderBulkFieldTiles();
      renderBulkResults();
    }});

    bulkSelectAllButton.addEventListener("click", () => {{
      bulkSelectedColumns = new Set(Object.keys(config.columns));
      renderBulkFieldTiles();
      renderBulkResults();
    }});

    document.querySelectorAll("input[name='bulkPageSize']").forEach((input) => {{
      input.addEventListener("change", () => {{
        bulkCurrentPage = 0;
        renderBulkResults();
      }});
    }});

    bulkPrevButton.addEventListener("click", () => {{
      if (bulkCurrentPage > 0) {{
        bulkCurrentPage -= 1;
        renderBulkResults();
      }}
    }});

    bulkNextButton.addEventListener("click", () => {{
      const pageSize = Number(document.querySelector("input[name='bulkPageSize']:checked").value);
      const totalPages = Math.max(1, Math.ceil(bulkResultRows.length / pageSize));
      if (bulkCurrentPage < totalPages - 1) {{
        bulkCurrentPage += 1;
        renderBulkResults();
      }}
    }});

    bulkRunButton.addEventListener("click", async () => {{
      bulkInputRows = parseBulkInputRows();
      const selectedColumns = selectedBulkColumns();
      if (!bulkInputRows.length) {{
        showDialog("Check bulk input", "Please enter at least one object.");
        return;
      }}
      if (!selectedColumns.length) {{
        showDialog("Choose data columns", "Please select at least one data field.");
        return;
      }}
      if (bulkReleaseSelect.value !== config.commonNameRelease && bulkInputRows.some((row) => !/^\\d+$/.test(row))) {{
        showDialog("Check bulk input", `${{bulkReleaseSelect.value}} mode requires numeric source IDs.`);
        return;
      }}

      bulkRunButton.disabled = true;
      bulkStatus.textContent = `Running bulk query in Gaia batches of up to ${{config.bulkBatchSize}}. This can take a long time...`;
      try {{
        const response = await fetch("/bulk-query", {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{
            objects: bulkInputRows,
            release: bulkReleaseSelect.value,
            selectedColumns,
          }}),
        }});
        const payload = await response.json();
        if (!response.ok) {{
          throw new Error(payload.error || "Bulk query failed.");
        }}
        bulkResultRows = payload.rows;
        bulkCurrentPage = 0;
        renderBulkResults();
        bulkStatus.textContent = payload.errors && payload.errors.length
          ? `${{payload.status}} ${{payload.errors.length}} rows had errors.`
          : payload.status;
      }} catch (error) {{
        bulkStatus.textContent = "Bulk query failed. See gaia_assist_debug.log.";
        showDialog("Bulk query failed", error.message);
      }} finally {{
        bulkRunButton.disabled = false;
      }}
    }});

    bulkSaveButton.addEventListener("click", async () => {{
      if (!bulkResultRows.length) {{
        showDialog("Nothing to save", "Please run a bulk query before saving.");
        return;
      }}
      try {{
        const response = await fetch("/bulk-save", {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{
            rows: bulkResultRows,
            selectedColumns: selectedBulkColumns(),
            inputMode: bulkReleaseSelect.value,
            inputValues: bulkInputRows,
          }}),
        }});
        const payload = await response.json();
        if (!response.ok) {{
          throw new Error(payload.error || "Save failed.");
        }}
        showDialog("Successfully saved", `Bulk data saved successfully to:\\n${{payload.path}}`);
      }} catch (error) {{
        showDialog("Save failed", error.message);
      }}
    }});

    dialogClose.addEventListener("click", () => dialog.close());

    helpButton.addEventListener("click", () => {{
      showDialog("Using Gaia Assist", config.helpTutorial);
    }});

    queryForm.addEventListener("submit", async (event) => {{
      event.preventDefault();
      const sourceId = sourceInput.value.trim();
      const release = releaseSelect.value;
      if (!sourceId) {{
        showDialog("Gaia Code required", "Please enter a Gaia source_id.");
        return;
      }}
      if (release !== config.commonNameRelease && !/^\\d+$/.test(sourceId)) {{
        showDialog("Check Gaia Code", "Gaia source_id values contain digits only.");
        return;
      }}

      queryButton.disabled = true;
      releaseSelect.disabled = true;
      statusLine.textContent = `Resolving ${{release}} source and querying Gaia DR3...`;

      try {{
        const response = await fetch("/query", {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{ sourceId, release }}),
        }});
        const payload = await response.json();
        if (!response.ok) {{
          throw new Error(payload.error || "Query failed.");
        }}
        renderRows(payload.rows);
        statusLine.textContent = payload.status;
      }} catch (error) {{
        statusLine.textContent = "Query failed. See gaia_assist_debug.log.";
        showDialog("Query failed", error.message);
      }} finally {{
        queryButton.disabled = false;
        releaseSelect.disabled = false;
      }}
    }});

    saveButton.addEventListener("click", async () => {{
      if (!currentRows.length || currentRows.every((row) => row.value === "-")) {{
        showDialog("Nothing to save", "Please query an object before saving.");
        return;
      }}

      const sourceRow = currentRows.find((row) => row.key === "source_id");
      const objectKey = sourceRow && sourceRow.value !== "-"
        ? sourceRow.value
        : (sourceInput.value.trim() || "unknown_object");

      if (objectKey === lastSavedObjectKey) {{
        const shouldSave = confirm(
          "This object was just saved. Do you still want to create another saved file for it?"
        );
        if (!shouldSave) {{
          return;
        }}
      }}

      try {{
        const response = await fetch("/save", {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{
            rows: currentRows,
            objectKey,
            inputMode: releaseSelect.value,
            inputValue: sourceInput.value.trim(),
          }}),
        }});
        const payload = await response.json();
        if (!response.ok) {{
          throw new Error(payload.error || "Save failed.");
        }}
        lastSavedObjectKey = objectKey;
        showDialog("Successfully saved", `Data saved successfully to:\\n${{payload.path}}`);
      }} catch (error) {{
        showDialog("Save failed", error.message);
      }}
    }});

    renderEmptyRows();
    renderBulkFieldTiles();
    renderBulkResults();
  </script>
</body>
</html>"""


class GaiaAssistWebHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urlparse(self.path)
        if parsed_path.path not in ("/", "/index.html"):
            self.send_error(404)
            return

        page = make_page().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(page)))
        self.end_headers()
        self.wfile.write(page)

    def do_POST(self):
        parsed_path = urlparse(self.path)
        try:
            payload = self.read_json_body()
            if parsed_path.path == "/query":
                response = self.handle_query(payload)
            elif parsed_path.path == "/save":
                response = self.handle_save(payload)
            elif parsed_path.path == "/bulk-query":
                response = self.handle_bulk_query(payload)
            elif parsed_path.path == "/bulk-save":
                response = self.handle_bulk_save(payload)
            else:
                self.send_error(404)
                return
        except Exception as error:
            Main.LOGGER.exception("Web request failed for path=%s", parsed_path.path)
            self.write_json({"error": str(error)}, status=500)
            return

        self.write_json(response)

    def handle_query(self, payload):
        source_id = str(payload.get("sourceId", "")).strip()
        release = str(payload.get("release", "DR3")).strip()
        allowed_releases = {"DR3", "DR2", "DR1", Main.COMMON_NAME_RELEASE}

        if not source_id:
            raise ValueError("Please enter a Gaia source_id.")
        if release not in allowed_releases:
            raise ValueError("Unknown Gaia ID release.")
        if release != Main.COMMON_NAME_RELEASE and not source_id.isdigit():
            raise ValueError("Gaia source_id values contain digits only.")

        return run_query(source_id, release)

    def handle_save(self, payload):
        rows = payload.get("rows")
        if not isinstance(rows, list) or not rows:
            raise ValueError("There is no data to save.")

        object_key = str(payload.get("objectKey", "")).strip() or "unknown_object"
        input_mode = str(payload.get("inputMode", "")).strip()
        input_value = str(payload.get("inputValue", "")).strip()
        saved_file = save_rows(rows, object_key, input_mode, input_value)
        return {"path": str(saved_file)}

    def handle_bulk_query(self, payload):
        objects = payload.get("objects")
        release = str(payload.get("release", "DR3")).strip()
        selected_columns = payload.get("selectedColumns")
        allowed_releases = {"DR3", "DR2", "DR1", Main.COMMON_NAME_RELEASE}

        if release not in allowed_releases:
            raise ValueError("Unknown Gaia ID release.")
        if not isinstance(objects, list):
            raise ValueError("Bulk objects must be sent as a list.")
        objects = [str(value).strip() for value in objects if str(value).strip()]
        if not objects:
            raise ValueError("Please enter at least one object.")
        if release != Main.COMMON_NAME_RELEASE and any(not value.isdigit() for value in objects):
            raise ValueError(f"{release} mode requires numeric source IDs.")
        if not isinstance(selected_columns, list):
            raise ValueError("Selected columns must be sent as a list.")
        selected_columns = [
            str(column_name)
            for column_name in selected_columns
            if column_name in Main.DISPLAY_COLUMNS
        ]
        if not selected_columns:
            raise ValueError("Please select at least one data field.")

        return run_bulk_query(objects, release, selected_columns)

    def handle_bulk_save(self, payload):
        rows = payload.get("rows")
        selected_columns = payload.get("selectedColumns")
        input_values = payload.get("inputValues")
        input_mode = str(payload.get("inputMode", "")).strip()

        if not isinstance(rows, list) or not rows:
            raise ValueError("There is no bulk data to save.")
        if not isinstance(selected_columns, list):
            raise ValueError("Selected columns must be sent as a list.")
        selected_columns = [
            str(column_name)
            for column_name in selected_columns
            if column_name in Main.DISPLAY_COLUMNS
        ]
        if not selected_columns:
            raise ValueError("Please select at least one data field.")
        if not isinstance(input_values, list):
            input_values = []
        input_values = [str(value) for value in input_values]

        saved_file = save_bulk_rows(rows, selected_columns, input_mode, input_values)
        return {"path": str(saved_file)}

    def read_json_body(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length)
        if not raw_body:
            return {}
        return json.loads(raw_body.decode("utf-8"))

    def write_json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        Main.LOGGER.info("Web server: " + format, *args)


def main():
    import WebMain_temperature as scientist
    from web_modes import make_handler
    handler = make_handler(sys.modules[__name__], scientist)
    port = PORT
    if len(sys.argv) > 1:
        port = int(sys.argv[1])

    try:
        server = ThreadingHTTPServer((HOST, port), handler)
    except OSError as error:
        if error.errno not in (10048, 98):
            raise
        if RENDER_ASSIGNED_PORT:
            raise
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind((HOST, 0))
            port = probe.getsockname()[1]
        server = ThreadingHTTPServer((HOST, port), handler)

    port = server.server_address[1]
    display_host = "localhost" if HOST in ("0.0.0.0", "::") else HOST
    url = f"http://{display_host}:{port}/"
    print(f"Gaia Assist Web is running at {url}", flush=True)
    try:
        server.serve_forever()
    finally:
        scientist.network.cancel_all()
        server.server_close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        error_log = Path(__file__).with_name("web_server_error.log")
        error_log.write_text(traceback.format_exc(), encoding="utf-8")
        raise
