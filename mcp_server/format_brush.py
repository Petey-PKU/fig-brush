"""Small, reference-only format brush workflow.

The rest of the package contains a number of compatibility tools for older
Origin workflows.  This module is the intentionally boring front door: read a
reference image, turn measurable visual evidence into a stable parameter
bundle, and leave the user's data out of the result.  Native Origin export is
kept as an optional second step because it needs a completed TemplateSpec and
an Origin installation.
"""
from __future__ import annotations

from copy import deepcopy
from collections import Counter
from pathlib import Path
from typing import Any

from .paths import InputValidationError, write_json
from .reference import inspect_reference


FORMAT_PARAMETERS_VERSION = "1.0"
APPLY_GUIDE_FILENAME = "APPLY_FORMAT.md"


def _format_value(value: Any, *, digits: int = 2) -> str:
    """Render a small JSON value for the human-facing apply guide."""
    if value is None:
        return "未检测到"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, float):
        return f"{value:.{digits}f}".rstrip("0").rstrip(".")
    if isinstance(value, (list, tuple)):
        return ", ".join(_format_value(item, digits=digits) for item in value)
    return str(value)


def _write_apply_guide(output_dir: Path, parameters: dict[str, Any]) -> Path:
    """Write the one-page human path for applying a JSON format bundle.

    The JSON files remain the machine-readable contract.  This small sidecar
    keeps users from having to interpret that contract before they can use it.
    It deliberately contains visual settings only and never copies a local
    worksheet path or any recovered values.
    """
    canvas = parameters.get("canvas", {}) or {}
    frame = parameters.get("plot_frame", {}) or {}
    margins = frame.get("margins_percent", {}) or {}
    typography = parameters.get("typography", {}) or {}
    axes = parameters.get("axes", {}) or {}
    palette = parameters.get("palette", {}) or {}
    detected = palette.get("detected", []) or []
    review = parameters.get("review", {}) or {}
    review_reasons = review.get("reasons", []) or []

    def axis_rows(axis_name: str) -> list[str]:
        axis = axes.get(axis_name, {}) or {}
        label = "X" if axis_name == "x" else "Y"
        rows = [
            f"| {label} 轴 | {axis.get('scale', 'linear')} | "
            f"{_format_value(axis.get('tick_direction', 'out'))} | "
            f"{_format_value(axis.get('major_tick_count'))} | "
            f"{_format_value(axis.get('minor_tick_count'))} |",
        ]
        return rows

    margin_text = "、".join(
        f"{name} {_format_value(margins.get(name))}%"
        for name in ("left", "top", "right", "bottom")
        if margins.get(name) is not None
    ) or "未检测到"
    palette_text = ", ".join(str(color) for color in detected) or "未可靠检测到；在 Origin 中按参考图确认"
    review_text = (
        "；".join(str(reason) for reason in review_reasons)
        if review_reasons
        else "无额外复核提示"
    )
    lines = [
        "# Origin 格式刷使用说明",
        "",
        "这个文件是给人的一页式操作说明。通常不需要打开 JSON 或运行脚本；把自己的 Origin 图打开后，在 Codex 对话中说“把这个格式粘贴到当前 Origin 图”即可。",
        "两个 JSON 的分工：",
        "- `format_parameters.json`：唯一需要参考的格式参数（页面、边距、坐标轴、字体和配色）。",
        "- `reference_analysis.json`：检测证据和置信度，供复核使用；不需要导入 Origin。",
        "",
        "## 最短操作路径",
        "",
        "1. 在 Origin 打开自己的数据图（散点、折线、柱形等），让目标 Graph 处于激活状态。",
        "2. 在当前 Codex 对话中说“把这个格式粘贴到当前 Origin 图”。系统会直接连接已打开的 Origin，只改视觉属性，不覆盖或自动保存你的项目。",
        "3. 如果你已有带参考 Graph 的 `.opju`，让 Codex 先准备 Origin 原生格式剪贴板；切回自己的 Graph 后右键选择 Origin 自带的“粘贴格式”。Origin 必须保持打开到粘贴完成。",
        "4. 没有可用的 Origin 会话时，仍可在 fig-brush 根目录运行下面这一条命令（或把脚本写成完整路径）。它会生成一个新的格式化副本，不会覆盖原项目：",
        "",
        "```powershell",
        "python scripts\\origin_plot_cli.py apply-format <your-project.opju> format_parameters.json",
        "```",
        "",
        "其中 `format_parameters.json` 就是本文件夹里的文件；如果当前目录不是 fig-brush 根目录，请把它写成该文件的完整路径。",
        "",
        "5. 打开命令返回的 `<your-project>_formatted.opju`，检查数据列、轴范围和文字；确认后即可继续编辑或另存为 Origin 模板。",
        "",
        "如果当前环境不能运行 Origin，仍可按下面的表格在 Origin 中手动设置。设置顺序是 `Format > Page`、`Format > Layer`、`Format > Axes`、`Plot Details`。",
        "",
        "## 可直接照抄的参数",
        "",
        "| 项目 | 参考值 | 在 Origin 中的位置 |",
        "| --- | --- | --- |",
        f"| 画布比例 | {_format_value(canvas.get('aspect_ratio'))}（{_format_value(canvas.get('width_px'))} × {_format_value(canvas.get('height_px'))} px） | `Format > Page` |",
        f"| 图层边距 | {margin_text} | `Format > Layer` |",
        f"| 字体 | {_format_value(typography.get('font_family'))}，约 {_format_value(typography.get('base_font_pt'))} pt | `Format > Axes` / `Plot Details` |",
        f"| X 轴 | 线性：{_format_value((axes.get('x', {}) or {}).get('frame_line_width_px'))} px，刻度朝 {_format_value((axes.get('x', {}) or {}).get('tick_direction', 'out'))} | `Format > Axes` |",
        f"| Y 轴 | 线性：{_format_value((axes.get('y', {}) or {}).get('frame_line_width_px'))} px，刻度朝 {_format_value((axes.get('y', {}) or {}).get('tick_direction', 'out'))} | `Format > Axes` |",
        f"| 配色 | {palette_text} | `Plot Details > Group/Line/Symbol` |",
        "",
        "## 坐标轴和图例",
        "",
        "| 轴 | 比例 | 刻度方向 | 主刻度数（提示） | 次刻度数（提示） |",
        "| --- | --- | --- | ---: | ---: |",
        *axis_rows("x"),
        *axis_rows("y"),
        "",
        "图例、文字、显著性括号和图形类别可能无法从图片可靠识别。请根据自己的图注和数据角色复核。",
        f"当前复核提示：{review_text}。",
        "",
        "## 如果文件夹里有 `.otpu`",
        "",
        "可直接在 Origin 的模板/主题菜单中导入或应用 `.otpu`，再检查数据列和轴范围。`.otpu` 是可选的原生模板；只有 JSON 时，按本页表格设置即可。",
        "",
        "最后，把调整好的图另存为自己的 Origin 模板。以后只需新建图并套用该模板，不必再次阅读 JSON。",
        "",
        "> 图片只能提供可见外观，不能确定原始数据、拟合算法或统计显著性。",
        "",
    ]
    guide_path = output_dir / APPLY_GUIDE_FILENAME
    guide_path.write_text("\n".join(lines), encoding="utf-8")
    return guide_path


def _visible_palette(image_path: str | Path) -> list[str]:
    """Find a few non-paper colours, including sparse coloured traces."""
    try:
        from PIL import Image

        with Image.open(image_path) as image:
            pixels = list(image.convert("RGB").getdata())
            # Keep the scan bounded for very large exports while preserving
            # solid pixels from thin coloured traces.
            stride = max(1, len(pixels) // 500_000)
            pixels = pixels[::stride]
    except Exception:
        return []
    buckets: Counter[tuple[int, int, int]] = Counter()
    for red, green, blue in pixels:
        if min(red, green, blue) >= 245:
            continue
        if max(red, green, blue) - min(red, green, blue) < 18:
            continue
        bucket = tuple(min(255, (value // 16) * 16 + 8) for value in (red, green, blue))
        buckets[bucket] += 1
    ranked = sorted(
        buckets.items(),
        key=lambda item: item[1] * (1.0 + (max(item[0]) - min(item[0])) / 96.0),
        reverse=True,
    )
    return ["#%02X%02X%02X" % color for color, _ in ranked[:8]]


def _axis_parameters(
    axis_name: str,
    style: dict[str, Any],
    axis: dict[str, Any],
    geometry: dict[str, Any],
) -> dict[str, Any]:
    """Return a compact, Origin-oriented description for one axis."""
    prefix = axis_name.lower()
    frame_sides = geometry.get("frame_sides", {}) or {}
    side = "bottom" if prefix == "x" else "left"
    values: dict[str, Any] = {
        "scale": axis.get("scale", "linear"),
        "title": axis.get("title"),
        "major_tick_count": axis.get(
            "major_tick_count", style.get(f"{prefix}_major_tick_count_hint", 0)
        ),
        "minor_tick_count": axis.get(
            "minor_tick_count", style.get(f"{prefix}_minor_tick_count_hint", 0)
        ),
        "major_tick_length_px": style.get(f"{prefix}_major_tick_length_px_hint"),
        "minor_tick_length_px": style.get(f"{prefix}_minor_tick_length_px_hint"),
        "frame_line_width_px": style.get(f"{prefix}_frame_line_width_px_hint"),
        "tick_direction": axis.get("tick_direction", "out"),
        "show_labels": axis.get("show_labels", True),
        "show_ticks": bool(frame_sides.get(side, False)),
        "evidence": {
            "frame_side_detected": bool(frame_sides.get(side, False)),
            "tick_positions_px": style.get(f"{prefix}_tick_positions_hint", []),
        },
    }
    # Origin uses point-like lengths while the detector observes raster
    # pixels. Keep both values and make the 96-DPI conversion explicit so a
    # user can paste the approximate value into Origin without guessing.
    for pixel_key, point_key in (
        ("major_tick_length_px", "major_tick_length_pt_96dpi"),
        ("minor_tick_length_px", "minor_tick_length_pt_96dpi"),
        ("frame_line_width_px", "frame_line_width_pt_96dpi"),
    ):
        value = values.get(pixel_key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            values[point_key] = round(float(value) * 72.0 / 96.0, 2)
    # Keep only evidence that is present.  This makes the file easy to review
    # and avoids turning detector defaults into claims about the image.
    return {key: value for key, value in values.items() if value is not None}


def build_format_parameters(reference: dict[str, Any]) -> dict[str, Any]:
    """Convert :func:`inspect_reference` output into a user-facing parameter pack.

    The result is deliberately data-free.  It describes appearance and the
    measured evidence needed to reproduce it in Origin; it never contains a
    worksheet, observations, or a recovered scientific value.
    """
    if not isinstance(reference, dict) or not isinstance(reference.get("image"), dict):
        raise InputValidationError("reference analysis must contain an image object.")
    image = reference["image"]
    geometry = image.get("geometry_hints", {}) or {}
    spec = reference.get("reference_spec", {}) or {}
    style = dict(spec.get("style", {}) or {})
    axes = dict(spec.get("axes", {}) or {})
    frame = dict(geometry.get("plot_frame", {}) or style.get("plot_frame", {}) or {})
    panels = []
    for panel in spec.get("panels", []) or []:
        if not isinstance(panel, dict):
            continue
        panels.append({
            key: deepcopy(panel[key])
            for key in ("id", "graph_family", "frame_px", "axes", "legend", "labels", "annotations")
            if key in panel
        })

    detected_palette = []
    for color in image.get("palette", []) or []:
        if not isinstance(color, str) or not color.startswith("#") or len(color) != 7:
            continue
        try:
            rgb = tuple(int(color[index : index + 2], 16) for index in (1, 3, 5))
        except ValueError:
            continue
        # Quantization often returns almost-white paper as a dominant colour.
        # It is useful as a background hint but not as a series colour.
        if min(rgb) >= 245:
            continue
        detected_palette.append(color.upper())

    review_reasons: list[str] = []
    try:
        geometry_confidence = float(geometry.get("detection_confidence", 0) or 0)
    except (TypeError, ValueError):
        geometry_confidence = 0.0
    if not spec.get("graph_family") and not spec.get("graph_family_hint"):
        review_reasons.append("graph_family_requires_visual_confirmation")
    if not panels:
        review_reasons.append("panel_and_series_roles_require_visual_confirmation")
    if geometry_confidence < 0.75:
        review_reasons.append("geometry_detection_confidence_is_low")

    parameters: dict[str, Any] = {
        "format_version": FORMAT_PARAMETERS_VERSION,
        "kind": "origin_format_parameters",
        "analysis_version": reference.get("analysis_version"),
        "source": {
            # A format bundle can be shared with collaborators. Keep the
            # image identity without leaking the local user's directory.
            "file": Path(str(reference.get("file"))).name if reference.get("file") else None,
            "sha256": reference.get("sha256"),
            "image_width_px": image.get("width"),
            "image_height_px": image.get("height"),
            "image_mode": image.get("mode"),
        },
        "canvas": {
            "aspect_ratio": image.get("aspect_ratio"),
            "width_px": image.get("width"),
            "height_px": image.get("height"),
            "page_aspect_ratio": geometry.get("page_aspect_ratio", style.get("page_aspect_ratio")),
            "background": "white",
        },
        "plot_frame": {
            "margins_percent": {
                key: frame[key] for key in ("left", "top", "right", "bottom") if key in frame
            },
            "width_px": frame.get("width_px"),
            "height_px": frame.get("height_px"),
            "aspect_ratio": frame.get("aspect_ratio"),
            "sides": deepcopy(geometry.get("frame_sides", {})),
        },
        "axes": {
            "x": _axis_parameters("x", style, dict(axes.get("x", {}) or {}), geometry),
            "y": _axis_parameters("y", style, dict(axes.get("y", {}) or {}), geometry),
        },
        "typography": {
            "base_font_pt": style.get("base_font_pt", 12),
            "estimated_text_height_px": geometry.get("estimated_text_height_px"),
            "estimated_text_height_ratio": geometry.get("estimated_text_height_ratio"),
            "tick_label_height_px": geometry.get("tick_label_height_px"),
            "tick_label_height_ratio": geometry.get("tick_label_height_ratio"),
            "font_family": style.get("font_family", "Arial"),
        },
        "palette": {
            "detected": detected_palette,
            "black": "#000000",
            "white": "#FFFFFF",
        },
        "graph_family": spec.get("graph_family") or spec.get("graph_family_hint"),
        "panels": panels,
        "origin_mapping": {
            "page": "Format > Page",
            "layer": "Format > Layer",
            "axes": "Format > Axes",
            "plots": "Plot Details > Group/Line/Symbol",
            "apply_order": ["page", "layer", "axes", "plots", "legend", "annotations"],
        },
        "confidence": {
            "geometry": geometry.get("detection_confidence", 0),
            "visual_semantics": spec.get("confidence", 0),
        },
        "review": {
            "required": bool(review_reasons),
            "reasons": review_reasons,
        },
        "model_required": {
            "graph_family": "根据参考图和图注确认（例如 scatter、line、column、heatmap）",
            "series_roles": "确认每条线/点/柱代表的实验对象和图例文本",
            "axis_text": "OCR 或人工复核轴标题、单位、刻度格式",
            "legend_and_annotations": "确认图例位置、注释、显著性括号和统计含义",
            "exact_font_and_colors": "像素检测只能给出近似值，最终在 Origin 中复核",
        },
        "data_policy": {
            "contains_user_data": False,
            "contains_recovered_measurements": False,
            "placeholder_values_required": False,
        },
            "next_step": "如果 Origin 已打开且目标 Graph 已激活，请让 Codex 调用 apply_active_format 将本文件直接套用；如果有参考 .opju，可先用 stage_format_clipboard，再在目标图右键使用 Origin 自带的粘贴格式；没有 Origin 会话时再用 apply-format 生成副本。轴范围、标签和统计含义以自己的数据为准。",
        "limits": [
            "截图可以确定可见外观，不能确定原始数据、拟合算法或统计显著性。",
            "颜色、文字和图例若未被像素检测可靠识别，应在 Origin 中人工复核。",
            "复杂多面板、3D、等高线和断轴图仍需要补充 TemplateSpec 才能导出原生模板。",
        ],
    }
    # Remove null values recursively while retaining explicit false/zero values.
    def compact(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: compact(item) for key, item in value.items() if item is not None}
        if isinstance(value, list):
            return [compact(item) for item in value]
        return value

    return compact(parameters)


def analyze_format(image_path: str, output_dir: str, user_notes: str = "") -> dict[str, Any]:
    """Analyze one image and write the JSON contract plus a human guide."""
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    reference = inspect_reference(image_path, user_notes)
    extra_palette = _visible_palette(image_path)
    if extra_palette:
        image_palette = list(reference.get("image", {}).get("palette", []) or [])
        reference.setdefault("image", {})["palette"] = list(dict.fromkeys(image_palette + extra_palette))[:8]
    # The detailed analysis is useful for review, but its source path should
    # remain portable when the output folder is copied to another machine.
    reference_for_output = deepcopy(reference)
    if reference_for_output.get("file"):
        reference_for_output["file"] = Path(str(reference_for_output["file"])).name
    parameters = build_format_parameters(reference_for_output)
    reference_path = output / "reference_analysis.json"
    parameters_path = output / "format_parameters.json"
    write_json(reference_path, reference_for_output)
    write_json(parameters_path, parameters)
    guide_path = _write_apply_guide(output, parameters)
    return {
        "status": "analyzed",
        "output_dir": str(output),
        "reference_analysis": str(reference_path),
        "format_parameters": str(parameters_path),
        "apply_guide": str(guide_path),
        "primary_output": str(guide_path),
        "format_version": FORMAT_PARAMETERS_VERSION,
        "contains_user_data": False,
        "review_required": bool(parameters.get("review", {}).get("required")),
        "review_reasons": parameters.get("review", {}).get("reasons", []),
    }
