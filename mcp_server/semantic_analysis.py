"""Descriptive evidence for a model-led scientific interpretation.

Header matches are hypotheses. This module does not infer experimental units,
physical identities, significance, or preprocessing from numerical shape.
"""
from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd


# Bound English tokens to avoid matching CI inside precision or n inside signal.
_ROLE_PATTERNS = {
    "error_sd": r"\b(sd|std|stdev|standard deviation)\b|标准差",
    "error_sem": r"\b(sem|standard error)\b|标准误",
    "error_ci": r"\b(ci|confidence interval)\b|(^|[_ .-])ci(?:90|95|99)?($|[_ .-])|置信区间",
    "sample_size": r"^(n|sample size|样本量)$",
    "replicate": r"^(rep|replicate|repeat)( id)?\d*$|^重复(编号)?\d*$",
    "identifier": r"\b(id|subject|patient|sample|specimen|batch)\b|编号|样品|受试者|批次",
    "group": r"\b(group|condition|treatment|category|class)\b|分组|条件|处理|类别",
    "mean": r"\b(mean|average|avg|median)\b|均值|平均|中位数",
    "x": r"^(x|x value|xdata)$|\b(time|wavelength|wavenumber|frequency|retention time|dose|concentration|temperature|position)\b|m/z|时间|波长|波数|频率|浓度|温度|位移|质荷比",
    "y": r"^(y|y value|ydata)$|\b(intensity|signal|response|absorbance|fluorescence|counts?|value|measurement)\b|强度|信号|响应|吸光|荧光|数值",
}
_METADATA = {"identifier", "group", "replicate", "sample_size", "error_sd", "error_sem", "error_ci"}


def _role(name: str, numeric: bool) -> tuple[str, float]:
    normalized = re.sub(r"[_\-]+", " ", name.lower()).strip()
    for role, pattern in _ROLE_PATTERNS.items():
        if re.search(pattern, normalized):
            return role, 0.88 if role not in {"x", "y"} else 0.80
    return ("numeric", 0.4) if numeric else ("categorical", 0.6)


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").astype(float)


def _column_analysis(frame: pd.DataFrame) -> list[dict[str, Any]]:
    columns = []
    for name in frame.columns:
        series = frame[name]
        numeric = bool(pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series))
        role, confidence = _role(str(name), numeric)
        item = {
            "name": str(name), "role": role, "role_confidence": confidence,
            "role_evidence": "column header" if role not in {"numeric", "categorical"} else "dtype only",
            "is_numeric": numeric, "missing_count": int(series.isna().sum()),
            "unique_count": int(series.nunique(dropna=True)),
        }
        if numeric:
            values = _numeric(series)
            finite = values[np.isfinite(values)]
            item["nonfinite_count"] = int((values.notna() & ~np.isfinite(values)).sum())
            item["finite_count"] = len(finite)
            if not finite.empty:
                diff = finite.diff().dropna()
                increasing = bool(len(diff) and (diff > 0).all())
                decreasing = bool(len(diff) and (diff < 0).all())
                item.update({
                    "min": float(finite.min()), "max": float(finite.max()),
                    "median": float(finite.median()),
                    "ordered_profile": {"ordered": increasing or decreasing,
                                        "strictly_increasing": increasing,
                                        "strictly_decreasing": decreasing},
                })
        else:
            item["levels"] = series.dropna().astype(str).drop_duplicates().head(20).tolist()
        columns.append(item)
    return columns


def describe_xy(frame: pd.DataFrame, x_name: str, y_name: str) -> dict[str, Any]:
    """Inspect original paired rows; report candidates, never validated peaks.

    Missing/nonfinite points stay in place while checking adjacent samples, so
    gaps cannot create artificial maxima or shift a reported source row.
    """
    x, y = _numeric(frame[x_name]).to_numpy(), _numeric(frame[y_name]).to_numpy()
    valid = np.isfinite(x) & np.isfinite(y)
    positions = np.flatnonzero(valid)
    result: dict[str, Any] = {
        "x": x_name, "y": y_name, "paired_n": int(valid.sum()),
        "excluded_nonfinite_pairs": int((~valid).sum()),
        "processing": "untransformed source values; no smoothing, baseline subtraction, or normalization",
    }
    if not len(positions):
        return result
    def point(index: int) -> dict[str, Any]:
        return {"source_row": index + 1, "x": float(x[index]), "y": float(y[index])}
    ymax = float(y[valid].max())
    maxima = positions[y[positions] == ymax]
    result.update({"maximum_observed": point(int(maxima[0])), "maximum_tie_count": len(maxima),
                   "range": [float(y[valid].min()), ymax],
                   "y_quantiles": {str(q): float(np.quantile(y[valid], q)) for q in (0.05, 0.5, 0.95)}})
    adjacent = valid[1:-1] & valid[:-2] & valid[2:]
    indices = np.flatnonzero(adjacent & (y[1:-1] > y[:-2]) & (y[1:-1] > y[2:])) + 1
    ranked = sorted(indices.tolist(), key=lambda i: (-y[i], i))[:5]
    result["local_maximum_candidates"] = [point(i) for i in ranked]
    result["candidate_method"] = "strict maximum among three adjacent source rows; top five by Y; endpoints and plateaus excluded"
    result["limitations"] = [
        "Candidates may be noise or parts of the same envelope, not resolved analytical peaks.",
        "A low quantile is descriptive and is not a validated physical baseline.",
        "Source rows are one-based data-row positions, excluding the header.",
    ]
    return result


def _candidate(family: str, score: float, reason: str) -> dict[str, Any]:
    return {"graph_family": family, "confidence": score, "reason": reason}


def analyze_dataframe(frame: pd.DataFrame, table_name: str | None = None) -> dict[str, Any]:
    columns = _column_analysis(frame)
    names = {c["name"]: c for c in columns}
    numeric = [c["name"] for c in columns if c["is_numeric"]]
    measured = [n for n in numeric if names[n]["role"] not in _METADATA]
    categories = [c["name"] for c in columns if c["role"] == "group" or c["role"] == "categorical"]
    identifiers = [c["name"] for c in columns if c["role"] in {"identifier", "replicate"}]
    errors = {kind: [c["name"] for c in columns if c["role"] == f"error_{kind}"] for kind in ("sd", "sem", "ci")}
    present_errors = [kind for kind, values in errors.items() if values]
    named_x = [n for n in measured if names[n]["role"] == "x"]
    named_y = [n for n in measured if names[n]["role"] in {"y", "mean"}]
    x = named_x[0] if len(named_x) == 1 else None
    # X/Y headers identify axes; arbitrary sorted columns do not.
    coordinate_pair = len(measured) == 2 and set(n.lower() for n in measured) == {"x", "y"}
    if coordinate_pair:
        x = next(n for n in measured if n.lower() == "x")
    group = categories[0] if len(categories) == 1 else None
    mapping = {"table": table_name, "numeric_columns": [], "categorical_columns": categories}
    candidates, findings, questions = [], [], []
    representation, model = "unknown", "undetermined"
    mapping_confidence = 0.55
    if present_errors or any(names[n]["role"] == "mean" for n in measured):
        representation = "summary_values"
    if x and len(measured) >= 2:
        ys = [n for n in measured if n != x]
        y = next((n for n in named_y if n != x), ys[0])
        ys = [y] + [n for n in ys if n != y]
        mapping.update({"x": x, "y": y, "series": ys[1:], "numeric_columns": ys})
        mapping_confidence = 0.90 if len(named_x) == 1 else 0.80
        model = "ordered_xy_series" if names[x].get("ordered_profile", {}).get("ordered") else "xy_series"
        if representation == "unknown":
            representation = "sampled_values"  # does not assert biological independence
        ordered = names[x].get("ordered_profile", {}).get("ordered")
        spectrum_axis = bool(re.search(r"m/z|wavelength|wavenumber|波长|波数|质荷", x, re.I))
        # Time supports an ordered display; spectra additionally require the
        # agent to check profile vs centroid/stick acquisition from context.
        if ordered:
            candidates.append(_candidate("line", 0.86 if not group and not identifiers else 0.70,
                "Named ordered coordinate supports a trace; verify that connecting samples is meaningful."))
        candidates.append(_candidate("scatter", 0.78, "Named axes support paired numeric values."))
        for y in ys[:8]:
            findings.append(describe_xy(frame, x, y))
        if spectrum_axis:
            questions.append("Confirm profile/centroid acquisition and whether a label means a sampled apex, centroid, or assigned species.")
    elif group and measured:
        mapping.update({"category": group, "values": measured, "numeric_columns": measured})
        mapping_confidence = 0.86
        counts = frame.groupby(group, dropna=False).size()
        repeated = bool((counts > 1).any())
        model = "long_repeated_observations" if repeated else "long_grouped"
        if representation == "summary_values":
            candidates.append(_candidate("column" if len(measured) == 1 else "grouped_column", 0.78,
                "Named summaries permit a group comparison only after uncertainty is mapped."))
        elif repeated and len(measured) == 1:
            representation = "observations_or_repeated_measurements"
            candidates.append(_candidate("box", 0.79, "Repeated group rows support inspecting distributions; display individual values for small groups."))
            questions.append("Are rows independent samples, repeated measurements, or technical replicates?")
        else:
            candidates.append(_candidate("column", 0.65, "Group labels and measurements exist; raw versus summary semantics are unresolved."))
            questions.append("Do numeric columns represent separate measurements, replicate observations, or summaries?")
    elif len(measured) == 1:
        mapping.update({"values": measured, "numeric_columns": measured})
        model = "univariate_numeric"
        candidates.append(_candidate("histogram", 0.72, "One numeric measurement supports a distribution if rows are observations."))
    elif len(measured) >= 2:
        # A proposed XY mapping is explicitly low confidence, never an
        # automatic assignment of IDs or an automatic regression/heatmap.
        mapping.update({"x": measured[0], "y": measured[1], "series": measured[2:], "numeric_columns": measured[1:]})
        model = "xy_or_wide_numeric"
        candidates.append(_candidate("scatter", 0.64, "Numeric columns could be axes, replicates, or separate outcomes; resolve their roles first."))
        questions.append("Which columns are X/Y, independent series, or repeated observations? Numeric shape alone cannot decide.")
        matrix_hint = bool(re.search(r"matrix|heatmap|correlation|矩阵|热图|相关", str(table_name or ""), re.I))
        matrix_shape = len(measured) >= 4 and 0.25 <= len(frame) / max(1, len(measured)) <= 8.0
        if matrix_shape and matrix_hint:
            mapping.pop("x", None)
            mapping.pop("y", None)
            mapping["matrix_columns"] = measured
            model = "numeric_matrix"
            candidates.append(_candidate("heatmap", 0.78, "Table name and near-matrix dimensions support a matrix pattern; verify row/column meaning."))
            questions.append("Confirm that rows and columns form a comparable matrix and that the first row/column are not hidden axis labels.")
    if identifiers:
        questions.append("Identifier/replicate columns require a decision about pairing, grouping, and the independent experimental unit.")
    replicate_columns = [n for n in numeric if names[n]["role"] == "replicate"]
    if len(replicate_columns) > 1:
        model = "wide_replicates_or_series"
        questions.append("Replicate-named columns may contain repeated values rather than IDs; resolve their layout before aggregation.")
    candidates.sort(key=lambda c: c["confidence"], reverse=True)
    recommended = candidates[0] if candidates else _candidate("column", 0.25, "No reliable mapping is available.")
    if categories and not group:
        mapping_confidence = min(mapping_confidence, 0.55)
        questions.append("Multiple categorical factors need an explicit group/series/panel mapping.")
    quality = {"row_count": len(frame), "column_count": len(columns), "duplicate_rows": int(frame.duplicated().sum()),
               "missing_count": int(frame.isna().sum().sum()),
               "nonfinite_count": sum(c.get("nonfinite_count", 0) for c in columns)}
    limitations = ["Heuristic confidence scores are routing rules, not calibrated probabilities.",
                  "No smoothing, normalization, aggregation, fitting, outlier removal, or significance testing has been applied."]
    if quality["missing_count"] or quality["nonfinite_count"]:
        limitations.append("Missing/nonfinite pairs are excluded only from descriptive evidence; source data are unchanged.")
    intent = {"line": "progression_or_spectrum", "scatter": "association", "box": "distribution", "histogram": "distribution", "column": "comparison", "grouped_column": "comparison"}.get(recommended["graph_family"], "undetermined")
    return {
        "analysis_version": "0.2", "table": table_name, "data_model": model,
        "representation": representation, "experimental_unit": "unknown",
        "column_roles": columns, "mapping": mapping, "mapping_confidence": mapping_confidence,
        "error_structure": {"columns": errors, "inferred_error_type": present_errors[0] if len(present_errors) == 1 else None,
                            "status": "header_evidence_only", "requires_value_column_mapping": bool(present_errors)},
        "data_quality": quality, "signal_findings": findings,
        "candidate_graphs": candidates, "recommended_graph": recommended,
        "scientific_question": {"intent": intent, "statement": "A candidate display purpose; the research question must come from experimental context."},
        "unresolved_questions": questions, "limitations": limitations,
    }


def semantic_from_inventory(table: dict[str, Any]) -> dict[str, Any] | None:
    value = table.get("semantic_analysis")
    return value if isinstance(value, dict) else None
