from __future__ import annotations

from copy import deepcopy
from typing import Any

from .layout import resolve_layout
from .semantic_analysis import semantic_from_inventory


GRAPH_FAMILIES = {
    "column",
    "grouped_column",
    "scatter",
    "line",
    "box",
    "violin",
    "histogram",
    "heatmap",
    "regression",
    "pie",
    "doughnut",
    "pie3d",
    "doughnut3d",
}


def _flatten_notes(reference: dict[str, Any] | None, user_notes: str) -> str:
    parts = [user_notes or ""]
    if reference:
        parts.append(str(reference.get("user_notes", "")))
        spec = reference.get("reference_spec", {}) or {}
        parts.extend(
            str(spec.get(key, ""))
            for key in ("graph_family", "data_model", "caption", "description")
        )
    return " ".join(parts).lower()


def _family_from_notes(notes: str) -> str | None:
    aliases = {
        "grouped_column": ("grouped bar", "grouped column", "分组柱", "分组条"),
        # Check explicit pie variants before the generic ``bar`` token. A
        # phrase such as "pie with error bars" still describes a pie, and
        # "3d-pie" must not fall through to the plain family.
        "doughnut3d": (
            "3d doughnut", "3-d doughnut", "3d donut", "3-d donut",
            "doughnut3d", "doughnut 3d", "3d-doughnut", "三维环形图",
        ),
        "pie3d": (
            "3d pie", "3-d pie", "three-dimensional pie", "three dimensional pie", "pie3d",
            "pie 3d", "3d-pie", "三维饼图",
        ),
        "doughnut": ("doughnut", "donut", "环形图"),
        "pie": ("pie chart", "pie", "饼图"),
        # Check the specific analytical family before the generic ``line``
        # token; notes such as "regression line" should not be routed to a
        # plain connected-trace template.
        "regression": ("regression", "correlation", "回归", "相关"),
        "column": ("bar", "column", "柱状", "条形"),
        "scatter": ("scatter", "散点"),
        "line": ("line", "折线", "time series", "时间序列"),
        "box": ("box plot", "boxplot", "箱线"),
        "violin": ("violin", "小提琴"),
        "histogram": ("histogram", "density", "直方", "密度"),
        "heatmap": ("heatmap", "matrix", "热图", "矩阵"),
    }
    for family, terms in aliases.items():
        if any(term in notes for term in terms):
            return family
    return None


def _choose_family(
    table: dict[str, Any], notes: str, reference_family: str | None = None
) -> tuple[str, float, str]:
    if reference_family in GRAPH_FAMILIES:
        return reference_family, 0.9, "Graph family was supplied by image analysis."
    explicit = _family_from_notes(notes)
    if explicit:
        return explicit, 0.88, "Graph family was supplied by image analysis or user notes."
    semantic = semantic_from_inventory(table)
    recommended = (semantic or {}).get("recommended_graph", {}) if semantic else {}
    semantic_family = recommended.get("graph_family")
    semantic_confidence = recommended.get("confidence")
    if semantic_family in GRAPH_FAMILIES and isinstance(semantic_confidence, (int, float)):
        return (
            semantic_family,
            float(semantic_confidence),
            "Graph family was selected from ordered-axis, grouping, replicate, distribution, and signal evidence in the data.",
        )
    candidates = table.get("candidate_models", [])
    model = candidates[0].get("data_model") if candidates else "undetermined"
    if model in {"xy_or_wide_numeric", "wide_replicates_or_series"}:
        return "scatter", 0.68, "Numeric columns support an XY-style plot, but series semantics are unresolved."
    if model == "long_grouped":
        return "column", 0.66, "A categorical and numeric column support grouped observations."
    return "column", 0.42, "No reliable graph family was found from the table alone."


def _mapping(table: dict[str, Any], family: str) -> dict[str, Any]:
    columns = table.get("columns", [])
    column_names = {column["name"] for column in columns}
    numeric = [column["name"] for column in columns if column.get("is_numeric")]
    categorical = [column["name"] for column in columns if not column.get("is_numeric")]
    mapping: dict[str, Any] = {"table": table.get("name"), "numeric_columns": numeric, "categorical_columns": categorical}
    semantic = semantic_from_inventory(table)
    semantic_mapping = (semantic or {}).get("mapping", {}) if semantic else {}
    # The semantic analyzer has access to row order and repeated-group
    # structure, which the compact column inventory cannot reconstruct.
    # Preserve only columns that are actually present in this table.
    if isinstance(semantic_mapping, dict):
        for key, value in semantic_mapping.items():
            if key == "table":
                continue
            if isinstance(value, list):
                filtered = [name for name in value if name in column_names]
                if filtered:
                    mapping[key] = filtered
            elif isinstance(value, str) and value in column_names:
                mapping[key] = value
    if family in {"scatter", "line", "regression"} and len(numeric) >= 2:
        # The first numeric column is the X coordinate; graph_builder must only
        # add the remaining numeric columns as Y plots.  Keeping X in
        # numeric_columns would draw the X data a second time as a Y series.
        mapping.setdefault("x", numeric[0])
        mapping.setdefault("y", numeric[1])
        mapping.setdefault("series", numeric[2:])
        mapping["numeric_columns"] = [mapping["y"], *mapping.get("series", [])]
    elif categorical and numeric:
        mapping.setdefault("category", categorical[0])
        mapping.setdefault("values", numeric)
        # Explicit SD/SEM/CI columns describe uncertainty and should not be
        # plotted as independent means. Keep them in statistics/mapping for
        # the Origin bridge and leave the actual value series clean.
        error_names = set(sum(((semantic or {}).get("error_structure", {}) or {}).get("columns", {}).values(), []))
        if error_names:
            mapping["values"] = [name for name in mapping.get("values", numeric) if name not in error_names]
    else:
        mapping.update({"values": numeric})
    return mapping


def _apply_reference_axis_hints(
    axes: dict[str, Any], style: dict[str, Any]
) -> dict[str, Any]:
    """Turn image-derived tick evidence into explicit Origin axis settings.

    The image detector exposes hints separately from the model's semantic
    interpretation.  Counts of short tick strokes are measurable geometric
    evidence, so they take precedence over a model's visual guess.  This is
    especially important when one axis has a single minor tick per major
    interval while the other has four: treating both axes as ``4`` produces a
    plausible but visibly different figure.  A user can still request a
    deliberate change in ``user_notes`` before rendering.
    """
    resolved = dict(axes or {})
    for name in ("x", "y"):
        axis = dict(resolved.get(name, {}) or {})
        major_hint = axis.get("major_tick_count_hint", style.get(f"{name}_major_tick_count_hint"))
        minor_hint = axis.get("minor_tick_count_hint", style.get(f"{name}_minor_tick_count_hint"))
        if isinstance(major_hint, (int, float)) and major_hint >= 2:
            axis["major_tick_count"] = int(round(major_hint))
        if isinstance(minor_hint, (int, float)) and minor_hint >= 0:
            axis["minor_tick_count"] = int(round(minor_hint))
        resolved[name] = axis
    return resolved


def _apply_reference_tick_length_hints(style: dict[str, Any]) -> dict[str, Any]:
    """Convert raster tick lengths into Origin point values at the 12 pt anchor.

    Reference images and Origin previews rarely have the same pixel width.  The
    measured stroke length is therefore scaled by the ratio of the target plot
    frame to the reference plot frame before converting to Origin's point-like
    tick-length properties.  The conversion constants are calibrated for the
    96 dpi Origin export used by the bridge and keep the small strokes visible
    after the page is resized to the standard 12 pt layout.
    """
    resolved = dict(style or {})
    frame = resolved.get("plot_frame", {}) or {}
    try:
        reference_frame_width = float(frame.get("width_px"))
        left = float(frame.get("left", 15.0))
        right = float(frame.get("right", 15.0))
        preview_width = float(resolved.get("preview_width_px", 1600))
        target_frame_width = preview_width * max(0.05, (100.0 - left - right) / 100.0)
        scale = target_frame_width / reference_frame_width if reference_frame_width > 0 else 1.0
    except (TypeError, ValueError):
        scale = 1.0

    # Origin's ticklength and mticklength are not one-to-one CSS pixels. These
    # factors were measured against the 96 dpi export path used in tests. Minor
    # strokes need a slightly larger point value because Origin rasterizes them
    # more aggressively than major strokes at the same nominal length.
    for axis_name in ("x", "y"):
        for kind, pixels_key, points_per_pixel in (
            ("major", "major", 1.25),
            ("minor", "minor", 0.83),
        ):
            hint = resolved.get(f"{axis_name}_{pixels_key}_tick_length_px_hint")
            if not isinstance(hint, (int, float)) or hint <= 0:
                continue
            value = max(0.5, round(float(hint) * scale / points_per_pixel, 1))
            resolved[f"{kind}_tick_length"] = value
    return resolved


def infer_plot_spec(
    reference: dict[str, Any] | None,
    inventory: dict[str, Any],
    user_notes: str = "",
) -> dict[str, Any]:
    tables = inventory.get("tables", [])
    if not tables:
        return {
            "status": "needs_clarification",
            "clarification_questions": ["数据文件没有可用工作表。请提供至少一张包含表头和数据的表。"],
        }
    table = tables[0]
    notes = _flatten_notes(reference, user_notes)
    raw_reference = reference or {}
    spec = raw_reference.get("reference_spec", raw_reference) or {}
    reference_hint = spec.get("graph_family_hint")
    family, family_confidence, reason = _choose_family(
        table, notes, spec.get("graph_family") or reference_hint
    )
    if not spec.get("graph_family") and reference_hint in GRAPH_FAMILIES and not (
        semantic_from_inventory(table)
        and (semantic_from_inventory(table) or {}).get("recommended_graph", {}).get("graph_family") == reference_hint
    ):
        family_confidence = min(family_confidence, 0.78)
        reason = "The reference image has a visual family hint, but the family still needs confirmation."
    style = _apply_reference_tick_length_hints(dict(spec.get("style", {}) or {}))
    axes = _apply_reference_axis_hints(
        dict(spec.get("axes", {}) or {}),
        dict(spec.get("style", {}) or {}),
    )
    legend = dict(spec.get("legend", {}) or {})
    annotations = dict(spec.get("annotations", {}) or {})
    input_statistics = spec.get("statistics", {}) or {}
    error_type = (
        spec.get("error_type")
        or style.get("error_type")
        or input_statistics.get("error_type")
    )
    if not error_type and any(term in notes for term in ("无误差线", "no error bar", "without error bar")):
        error_type = "none"

    questions: list[str] = []
    semantic = semantic_from_inventory(table)
    semantic_error = ((semantic or {}).get("error_structure", {}) or {}).get("inferred_error_type")
    if not error_type and semantic_error:
        error_type = semantic_error
    # A continuous trace with no error column is a legitimate raw signal.  For
    # category comparisons we still ask explicitly, because silently treating
    # repeated values as means or error bars changes the scientific claim.
    if not error_type and family in {"scatter", "regression", "line"}:
        error_type = "none"
    if family in {"column", "grouped_column", "box", "violin"} and not error_type:
        questions.append("如果图中包含误差线，请确认使用 SD、SEM、95% CI，还是其他误差表示；如果没有误差线，请回复“无误差线”。")
    xy_mapping = _mapping(table, family) if family in {"scatter", "line", "regression"} else {}
    if family in {"scatter", "line", "regression"} and not xy_mapping.get("x"):
        questions.append("该图需要至少两列数值数据作为 X 和 Y，请确认列映射。")
    if family_confidence < 0.85:
        questions.append("请确认参考图对应的图形类型，或补充图注/实验说明。")

    confidence = family_confidence
    if reference and spec.get("confidence"):
        confidence = min(0.99, max(confidence, float(spec["confidence"])))
    interpretation = deepcopy(semantic or {})
    # Scientific context is an interpretation contract supplied by the image
    # reader/user. Keep it separate from geometry so a renderer cannot mistake
    # pixel measurements for domain meaning.
    context = (
        spec.get("scientific_context")
        or (raw_reference.get("reference_spec", {}) or {}).get("scientific_context")
        or raw_reference.get("scientific_context")
    )
    if isinstance(context, dict):
        interpretation["scientific_context"] = deepcopy(context)
    # The analyzer can flag unresolved experimental-unit or representation
    # decisions. Surface those questions before rendering, rather than hiding
    # them behind a plausible template.
    for question in (interpretation.get("unresolved_questions", []) if isinstance(interpretation, dict) else []):
        if isinstance(question, str) and question not in questions:
            questions.append(question)
    reference_visual = raw_reference.get("visual_semantics") or spec.get("visual_semantics")
    if isinstance(reference_visual, dict):
        interpretation["reference_visual_cues"] = reference_visual
    reference_context = (context or {}).get("reference", {}) if isinstance(context, dict) else {}
    if isinstance(reference_context, dict):
        for unresolved in reference_context.get("unresolved", []) or []:
            if isinstance(unresolved, str) and unresolved not in questions:
                questions.append(unresolved)
    if context and not reference_context.get("research_question"):
        questions.append("请补充参考图要回答的研究问题，避免只复制图形外观而改变图的科学含义。")
    if context and reference_context.get("uncertainty", "unknown") == "unknown":
        questions.append("请确认参考图是否表达误差/置信区间/重复测量；当前图像语义尚未确认。")
    resolved_mapping = _mapping(table, family)
    # Column names are the only defensible axis labels when the reference or
    # user has not supplied a caption. Carry them into the editable project so
    # the figure remains interpretable after export.
    if isinstance(axes, dict):
        x_title = resolved_mapping.get("x") or resolved_mapping.get("category")
        y_title = resolved_mapping.get("y")
        if not y_title:
            values = resolved_mapping.get("values") or resolved_mapping.get("numeric_columns") or []
            y_title = values[0] if values else None
        if x_title and isinstance(axes.get("x"), dict):
            axes["x"].setdefault("title", str(x_title))
        if y_title and isinstance(axes.get("y"), dict):
            axes["y"].setdefault("title", str(y_title))
    plot_spec = {
        "schema_version": "1.0",
        "graph_family": family,
        "data_model": spec.get("data_model") or (semantic or {}).get("data_model") or (table.get("candidate_models") or [{}])[0].get("data_model"),
        "data_mapping": resolved_mapping,
        "statistics": {
            "error_type": error_type,
            "raw_points": style.get("raw_points", input_statistics.get("raw_points", False)),
            "error_columns": (interpretation.get("error_structure", {}) or {}).get("columns", {}),
        },
        "axes": axes,
        "legend": legend,
        "annotations": annotations,
        "style": style,
        "confidence": confidence,
        "inference_reason": reason,
        # This block is intentionally retained in the editable PlotSpec and
        # manifest. It explains what the figure is meant to communicate and
        # which observations support that choice; it is not a visual style
        # instruction and never replaces a statistical analysis.
        "interpretation": interpretation,
        "source_file": inventory.get("file"),
        "source_table": table.get("name"),
        "output": {"project_format": "opju", "preview_formats": ["png", "svg"]},
    }
    plot_spec = resolve_layout(plot_spec)
    if questions:
        return {
            "status": "needs_clarification",
            "plot_spec": plot_spec,
            "clarification_questions": questions,
        }
    return {"status": "ready", "plot_spec": plot_spec, "clarification_questions": []}
