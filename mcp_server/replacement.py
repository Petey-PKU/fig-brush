"""User-facing replacement data contracts for screenshot templates.

The screenshot renderer needs a compact Origin worksheet with numeric helper
columns. Researchers usually work with a different surface: long raw
observations, summary values, and explicit uncertainty metadata. This module
keeps those two concerns separate. The generated rows are still synthetic
reference placeholders; they only define the shape of the replacement input.
"""

from __future__ import annotations

import csv
from copy import deepcopy
import json
from pathlib import Path
import re
from typing import Any

import pandas as pd


COLUMN_KINDS = {"column", "grouped_column", "bar"}


def _label_text(item: dict[str, Any]) -> str:
    return str(item.get("text", item.get("text_markup", ""))).strip()


def _category_labels(panel: dict[str, Any]) -> list[str]:
    explicit = panel.get("category_labels") or panel.get("categories")
    if isinstance(explicit, list) and explicit:
        return [str(value) for value in explicit]
    labels = [
        _label_text(item)
        for item in panel.get("labels", [])
        if isinstance(item, dict) and _label_text(item)
    ]
    if labels:
        return labels
    values: list[Any] = []
    for series in panel.get("series", []):
        if series.get("kind") not in COLUMN_KINDS:
            continue
        source = series.get("marker_data") or series.get("data", {}) or {}
        for value in source.get("x", []) or []:
            if value not in values:
                values.append(value)
    return [str(value) for value in values]


def _series_group(series: dict[str, Any], labels: list[str], x_value: Any | None = None) -> str:
    """Resolve a readable group name without treating it as scientific meaning."""
    if x_value is not None:
        try:
            index = int(round(float(x_value))) - 1
            if 0 <= index < len(labels):
                return labels[index]
        except (TypeError, ValueError):
            pass
    name = str(series.get("name", series.get("id", "Series")))
    cleaned = re.sub(r"(?i)(replicates?|markers?|raw|summary|bars?|columns?)$", "", name).strip(" _-")
    for label in labels:
        if cleaned.lower() == label.lower() or name.lower().startswith(label.lower()):
            return label
    return cleaned or name


def _finite(value: Any) -> Any:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    return number if number == number else ""


def _uncertainty_label(spec: dict[str, Any]) -> str:
    context = spec.get("scientific_context", {}) or {}
    reference = context.get("reference", {}) if isinstance(context, dict) else {}
    uncertainty = reference.get("uncertainty", {}) if isinstance(reference, dict) else {}
    if isinstance(uncertainty, dict):
        value = uncertainty.get("representation") or uncertainty.get("source")
        if value:
            text = str(value).lower()
            for name in ("sd", "sem", "standard deviation", "standard error", "ci", "confidence", "range"):
                if name in text:
                    return str(value)
    return "unknown"


def _panel_contract(panel: dict[str, Any], spec: dict[str, Any]) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    series = panel.get("series", []) or []
    columns = [item for item in series if item.get("kind") in COLUMN_KINDS]
    raw = [item for item in series if item.get("role", "").lower().find("raw") >= 0 or "replic" in str(item.get("id", "")).lower()]
    labels = _category_labels(panel)
    tables: dict[str, list[dict[str, Any]]] = {}
    if columns and raw:
        raw_rows: list[dict[str, Any]] = []
        for item in raw:
            source = item.get("marker_data") or item.get("data", {}) or {}
            for index, (x_value, y_value) in enumerate(zip(source.get("x", []) or [], source.get("y", []) or []), 1):
                raw_rows.append({
                    "Panel": panel["id"],
                    "Group": _series_group(item, labels, x_value),
                    "Replicate": index,
                    "Value": _finite(y_value),
                })
        summary_rows: list[dict[str, Any]] = []
        error_type = _uncertainty_label(spec)
        for item in columns:
            source = item.get("marker_data") or item.get("data", {}) or {}
            errors = source.get("y_error", []) or []
            for x_value, y_value, error in zip(
                source.get("x", []) or [], source.get("y", []) or [],
                errors or [""] * len(source.get("x", []) or []),
            ):
                if float(y_value or 0) == 0 and float(error or 0) == 0:
                    continue
                summary_rows.append({
                    "Panel": panel["id"],
                    "Group": _series_group(item, labels, x_value),
                    "Center": _finite(y_value),
                    "ErrorPlus": _finite(error),
                    "ErrorMinus": _finite(error),
                    "ErrorType": error_type,
                })
        tables["Raw_Data"] = raw_rows
        tables["Summary_Data"] = summary_rows
        return {
            "panel": panel["id"],
            "mode": "categorical_summary_raw",
            "input_tables": ["Raw_Data", "Summary_Data"],
            "derived_plot_data": panel.get("data_worksheet", f"{panel['id']}_Data"),
            "columns": {
                "Raw_Data": ["Panel", "Group", "Replicate", "Value"],
                "Summary_Data": ["Panel", "Group", "Center", "ErrorPlus", "ErrorMinus", "ErrorType"],
            },
            "statistics": {
                "summary_method": "unknown",
                "error_method": error_type,
                "p_value_method": "reference_annotation",
            },
        }, tables

    xy_rows: list[dict[str, Any]] = []
    for item in series:
        source = item.get("marker_data") or item.get("data", {}) or {}
        y_errors = source.get("y_error", []) or []
        x_errors = source.get("x_error", []) or []
        for index, (x_value, y_value) in enumerate(zip(source.get("x", []) or [], source.get("y", []) or [])):
            xy_rows.append({
                "Panel": panel["id"],
                "Series": item.get("name", item.get("id", "Series")),
                "Replicate": index + 1,
                "X": _finite(x_value),
                "Y": _finite(y_value),
                "YError": _finite(y_errors[index]) if index < len(y_errors) else "",
                "XError": _finite(x_errors[index]) if index < len(x_errors) else "",
            })
    tables["XY_Data"] = xy_rows
    return {
        "panel": panel["id"],
        "mode": "xy",
        "input_tables": ["XY_Data"],
        "derived_plot_data": panel.get("data_worksheet", f"{panel['id']}_Data"),
        "columns": {"XY_Data": ["Panel", "Series", "Replicate", "X", "Y", "YError", "XError"]},
        "statistics": {"summary_method": "not_applicable", "error_method": "unknown", "p_value_method": "reference_annotation"},
    }, tables


def build_replacement_bundle(spec: dict[str, Any], output_dir: str | Path) -> dict[str, Any]:
    """Write conventional input tables and an auditable replacement contract."""
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    tables: dict[str, list[dict[str, Any]]] = {}
    panels: list[dict[str, Any]] = []
    for panel in spec.get("panels", []):
        panel_contract, panel_tables = _panel_contract(panel, spec)
        panels.append(panel_contract)
        for name, rows in panel_tables.items():
            tables.setdefault(name, []).extend(rows)

    # A blank file is still useful for a graph family with no series in the
    # reference. Keep the column names explicit so spreadsheet imports do not
    # depend on the first placeholder row.
    columns_by_table = {
        "Raw_Data": ["Panel", "Group", "Replicate", "Value"],
        "Summary_Data": ["Panel", "Group", "Center", "ErrorPlus", "ErrorMinus", "ErrorType"],
        "XY_Data": ["Panel", "Series", "Replicate", "X", "Y", "YError", "XError"],
    }
    files: dict[str, str] = {}
    for table_name, rows in tables.items():
        columns = columns_by_table[table_name]
        path = output / f"{table_name}.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
        files[table_name] = str(path)
    contract = {
        "version": "1.0",
        "mode": "reference_placeholder_input_contract",
        "provenance": "All rows written here are synthetic visual placeholders derived from the screenshot.",
        "workbook_role": "User Input",
        "panels": panels,
        "files": {name: f"{name}.csv" for name in files},
        "rules": {
            "replaceable": ["Raw_Data.Value", "Summary_Data.Center", "Summary_Data.ErrorPlus", "Summary_Data.ErrorMinus", "XY_Data.X", "XY_Data.Y"],
            "layout_helpers": ["Derived plot worksheet X/category mapping and marker jitter are generated by fig-brush."],
            "unknown_statistics": ["summary_method", "error_method", "p_value_method"],
            "privacy": "No private research data is read or inferred during screenshot preparation.",
        },
    }
    contract_path = output / "replacement_contract.json"
    contract_path.write_text(json.dumps(contract, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"contract": contract, "contract_path": str(contract_path), "files": files}


def read_replacement_table(path: str | Path, table_name: str) -> pd.DataFrame:
    """Read a named replacement CSV or an Excel sheet for a future refresh."""
    source = Path(path).expanduser().resolve()
    if source.suffix.lower() in {".xlsx", ".xls", ".xlsm"}:
        return pd.read_excel(source, sheet_name=table_name)
    if source.suffix.lower() == ".csv":
        return pd.read_csv(source)
    raise ValueError(f"Unsupported replacement input: {source}")


def _read_csv_if_present(directory: Path, name: str) -> pd.DataFrame:
    path = directory / f"{name}.csv"
    if not path.is_file():
        return pd.DataFrame()
    return pd.read_csv(path)


def _group_index(labels: list[str], value: Any) -> int:
    text = str(value)
    for index, label in enumerate(labels, 1):
        if text.lower() == label.lower():
            return index
    return 0


def _number(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return default if pd.isna(number) else number


def refresh_reference_spec(spec: dict[str, Any], input_dir: str | Path) -> dict[str, Any]:
    """Apply user-facing input tables to a copy of a reference TemplateSpec.

    This only maps explicit user columns into the existing visual roles. It
    does not choose a mean/median, infer an error statistic, or recompute a
    significance test from screenshot placeholders.
    """
    directory = Path(input_dir).expanduser().resolve()
    refreshed = deepcopy(spec)
    raw = _read_csv_if_present(directory, "Raw_Data")
    summary = _read_csv_if_present(directory, "Summary_Data")
    xy = _read_csv_if_present(directory, "XY_Data")
    for panel in refreshed.get("panels", []):
        labels = _category_labels(panel)
        panel_id = str(panel["id"])
        columns = [item for item in panel.get("series", []) if item.get("kind") in COLUMN_KINDS]
        raw_series = [item for item in panel.get("series", []) if item.get("role", "").lower().find("raw") >= 0 or "replic" in str(item.get("id", "")).lower()]
        if columns and raw_series:
            if not summary.empty:
                rows = summary[summary.get("Panel", panel_id) == panel_id] if "Panel" in summary else summary
                by_group = {str(row["Group"]): row for _, row in rows.iterrows()}
                for item in columns:
                    source = dict(item.get("data", {}) or {})
                    series_group = _series_group(item, labels)
                    errors = []
                    values = []
                    for x_value in source.get("x", []) or []:
                        group = _series_group(item, labels, x_value)
                        row = by_group.get(group) if group.lower() == series_group.lower() else None
                        if row is None:
                            values.append(0.0)
                            errors.append(0.0)
                        else:
                            values.append(_number(row.get("Center", 0)))
                            errors.append(_number(row.get("ErrorPlus", 0)))
                    source["y"] = values
                    if "y_error" in source:
                        source["y_error"] = errors
                    item["data"] = source
                    if "marker_data" in item:
                        marker = dict(item["marker_data"])
                        marker["y"] = values
                        if "y_error" in marker:
                            marker["y_error"] = errors
                        item["marker_data"] = marker
            if not raw.empty:
                rows = raw[raw.get("Panel", panel_id) == panel_id] if "Panel" in raw else raw
                for item in raw_series:
                    group = _series_group(item, labels)
                    selected = rows[rows["Group"].astype(str).str.lower() == group.lower()] if "Group" in rows else rows
                    values = [_number(value) for value in selected.get("Value", []).tolist() if pd.notna(value)]
                    index = _group_index(labels, group)
                    if not values or not index:
                        continue
                    offsets = [0.0] if len(values) == 1 else list(pd.Series(range(len(values))).map(lambda n: -0.22 + 0.44 * n / (len(values) - 1)))
                    data = {"x": [index + float(offset) for offset in offsets], "y": values}
                    item["data"] = data
                    if "marker_data" in item:
                        item["marker_data"] = deepcopy(data)
            continue
        if not xy.empty:
            rows = xy[xy.get("Panel", panel_id) == panel_id] if "Panel" in xy else xy
            for item in panel.get("series", []):
                name = str(item.get("name", item.get("id", "Series")))
                selected = rows[rows["Series"].astype(str).str.lower() == name.lower()] if "Series" in rows else rows
                if selected.empty:
                    continue
                selected = selected[selected["X"].notna() & selected["Y"].notna()] if "X" in selected and "Y" in selected else selected
                item["data"] = {
                    "x": selected["X"].tolist(),
                    "y": selected["Y"].tolist(),
                    **({"y_error": selected["YError"].fillna(0).tolist()} if "YError" in selected and selected["YError"].notna().any() else {}),
                    **({"x_error": selected["XError"].fillna(0).tolist()} if "XError" in selected and selected["XError"].notna().any() else {}),
                }
                if "marker_data" in item:
                    item["marker_data"] = deepcopy(item["data"])
    refreshed["replacement_applied"] = {
        "input_dir": str(directory),
        "source": "user_supplied_local_tables",
        "statistics_recomputed": False,
        "note": "Summary and uncertainty columns were copied explicitly; no statistical meaning was inferred. ErrorPlus drives the current symmetric renderer; ErrorMinus remains in the input contract.",
    }
    return refreshed
