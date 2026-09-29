from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

import pandas as pd

from .paths import InputValidationError, json_safe, resolve_input, sha256_file
from .semantic_analysis import analyze_dataframe


DATA_SUFFIXES = {".xlsx", ".csv", ".tsv", ".txt"}


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "utf-16", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise InputValidationError(f"Could not decode text data file: {path}")


def _detect_delimiter(text: str, suffix: str) -> str:
    if suffix == ".tsv":
        return "\t"
    sample = "\n".join(text.splitlines()[:20])
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
        return dialect.delimiter
    except csv.Error:
        for delimiter in (",", "\t", ";", "|"):
            if delimiter in sample:
                return delimiter
    return "\t" if "\t" in sample else ","


def load_tables(path: str | Path) -> dict[str, pd.DataFrame]:
    file_path = resolve_input(path, DATA_SUFFIXES)
    suffix = file_path.suffix.lower()
    if suffix == ".xlsx":
        workbook = pd.ExcelFile(file_path)
        return {
            str(sheet): pd.read_excel(file_path, sheet_name=sheet)
            for sheet in workbook.sheet_names
        }

    text = _read_text(file_path)
    delimiter = _detect_delimiter(text, suffix)
    frame = pd.read_csv(io.StringIO(text), sep=delimiter, engine="python")
    return {file_path.stem: frame}


def _is_numeric(series: pd.Series) -> bool:
    return bool(pd.api.types.is_numeric_dtype(series))


def _column_summary(series: pd.Series) -> dict[str, Any]:
    non_null = series.dropna()
    summary: dict[str, Any] = {
        "name": str(series.name),
        "dtype": str(series.dtype),
        "is_numeric": _is_numeric(series),
        "row_count": int(len(series)),
        "non_null_count": int(non_null.shape[0]),
        "missing_count": int(series.isna().sum()),
        "unique_count": int(non_null.nunique(dropna=True)),
        "sample_values": [json_safe(value) for value in non_null.head(5).tolist()],
    }
    if summary["is_numeric"] and not non_null.empty:
        numeric = pd.to_numeric(non_null, errors="coerce").dropna()
        if not numeric.empty:
            summary["min"] = float(numeric.min())
            summary["max"] = float(numeric.max())
            summary["mean"] = float(numeric.mean())
    return summary


def _candidate_models(frame: pd.DataFrame) -> list[dict[str, Any]]:
    numeric = [str(column) for column in frame.columns if _is_numeric(frame[column])]
    categorical = [str(column) for column in frame.columns if not _is_numeric(frame[column])]
    candidates: list[dict[str, Any]] = []

    if len(numeric) >= 2:
        candidates.append(
            {
                "data_model": "xy_or_wide_numeric",
                "confidence": 0.68 if not categorical else 0.62,
                "reason": "At least two numeric columns can represent X/Y or multiple series.",
                "numeric_columns": numeric,
                "categorical_columns": categorical,
            }
        )
    if categorical and numeric:
        candidates.append(
            {
                "data_model": "long_grouped",
                "confidence": 0.72,
                "reason": "Categorical and numeric columns can represent grouped observations.",
                "numeric_columns": numeric,
                "categorical_columns": categorical,
            }
        )
    if len(numeric) >= 2 and not categorical:
        candidates.append(
            {
                "data_model": "wide_replicates_or_series",
                "confidence": 0.64,
                "reason": "Multiple numeric columns may be replicates or independent series.",
                "numeric_columns": numeric,
                "categorical_columns": categorical,
            }
        )
    if not candidates:
        candidates.append(
            {
                "data_model": "undetermined",
                "confidence": 0.25,
                "reason": "The table does not contain enough typed columns for a plot mapping.",
                "numeric_columns": numeric,
                "categorical_columns": categorical,
            }
        )
    return candidates


def inspect_dataset(path: str | Path) -> dict[str, Any]:
    file_path = resolve_input(path, DATA_SUFFIXES)
    tables = load_tables(file_path)
    table_payloads: list[dict[str, Any]] = []
    warnings: list[str] = []
    for name, frame in tables.items():
        if frame.empty:
            warnings.append(f"Table {name!r} is empty.")
        table_payloads.append(
            {
                "name": name,
                "row_count": int(frame.shape[0]),
                "column_count": int(frame.shape[1]),
                "columns": [_column_summary(frame[column]) for column in frame.columns],
                "candidate_models": _candidate_models(frame),
                # Keep the dtype-oriented inventory for backwards
                # compatibility, but attach an auditable scientific reading
                # so inference can reason about signal, grouping, repeats,
                # and possible error columns instead of guessing from dtypes.
                "semantic_analysis": analyze_dataframe(frame, str(name)),
            }
        )
    return {
        "file": str(file_path),
        "suffix": file_path.suffix.lower(),
        "sha256": sha256_file(file_path),
        "tables": table_payloads,
        "warnings": warnings,
        "supported": True,
    }
