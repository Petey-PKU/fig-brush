from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw

from mcp_server.format_brush import analyze_format, build_format_parameters
from mcp_server.server import format_brush_tool


def _reference(path: Path) -> None:
    image = Image.new("RGB", (640, 360), "white")
    draw = ImageDraw.Draw(image)
    draw.line((90, 300, 560, 300), fill="black", width=2)
    draw.line((90, 40, 90, 300), fill="black", width=2)
    draw.line((140, 260, 250, 170, 360, 210, 500, 90), fill="#2E75B6", width=3)
    image.save(path)


def test_analyze_format_writes_two_data_free_core_artifacts(workspace_tmp: Path):
    image = workspace_tmp / "reference.png"
    _reference(image)
    result = analyze_format(str(image), str(workspace_tmp / "format"))

    assert result["status"] == "analyzed"
    assert result["review_required"] is True
    assert Path(result["apply_guide"]).is_file()
    parameters = json.loads(Path(result["format_parameters"]).read_text(encoding="utf-8"))
    analysis = json.loads(Path(result["reference_analysis"]).read_text(encoding="utf-8"))
    assert parameters["kind"] == "origin_format_parameters"
    assert parameters["source"]["file"] == "reference.png"
    assert parameters["data_policy"]["contains_user_data"] is False
    assert parameters["plot_frame"]["sides"]["bottom"] is True
    assert parameters["axes"]["x"]["show_ticks"] is True
    assert parameters["palette"]["detected"]
    assert analysis["image"]["width"] == 640
    assert analysis["file"] == "reference.png"
    guide_text = Path(result["apply_guide"]).read_text(encoding="utf-8")
    assert "format_parameters.json" in guide_text
    assert "reference_analysis.json" in guide_text
    assert "apply-format" in guide_text
    assert "APPLY_FORMAT" in Path(result["apply_guide"]).name
    assert not (workspace_tmp / "format" / "result.opju").exists()


def test_format_brush_tool_is_reference_only_by_default(workspace_tmp: Path):
    image = workspace_tmp / "reference.png"
    _reference(image)
    result = format_brush_tool(str(image), str(workspace_tmp / "format"))
    assert result["status"] == "analyzed"
    assert "template" not in result


def test_build_format_parameters_keeps_explicit_zero_values():
    reference = {
        "file": "reference.png",
        "sha256": "abc",
        "image": {
            "width": 100,
            "height": 80,
            "mode": "RGB",
            "aspect_ratio": 1.25,
            "palette": [],
            "geometry_hints": {
                "plot_frame": {"left": 10, "top": 10, "right": 10, "bottom": 10, "width_px": 80, "height_px": 60},
                "frame_sides": {"top": False, "right": False, "bottom": True, "left": True},
                "page_aspect_ratio": 1.25,
                "x_major_tick_count_hint": 2,
                "x_minor_tick_count_hint": 0,
                "y_major_tick_count_hint": 2,
                "y_minor_tick_count_hint": 0,
                "detection_confidence": 0.5,
            },
        },
        "reference_spec": {"style": {}, "axes": {}},
    }
    result = build_format_parameters(reference)
    assert result["axes"]["x"]["minor_tick_count"] == 0
    assert result["plot_frame"]["sides"]["top"] is False
