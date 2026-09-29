from pathlib import Path

from PIL import Image, ImageDraw

from mcp_server.reference import inspect_reference


def test_reference_extracts_page_ratio_and_frame_geometry(workspace_tmp: Path):
    path = workspace_tmp / "reference.png"
    image = Image.new("RGB", (1000, 320), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((180, 35, 830, 255), outline="black", width=2)
    image.save(path)

    result = inspect_reference(path)
    hints = result["image"]["geometry_hints"]
    frame = hints["plot_frame"]

    assert result["image"]["aspect_ratio"] > 3
    assert 2.5 < frame["aspect_ratio"] < 3.5
    assert all(hints["frame_sides"].values())
    assert result["reference_spec"]["style"]["page_aspect_ratio"] == result["image"]["aspect_ratio"]
    assert result["analysis_version"] == "0.3.1"
    assert result["reference_spec"]["scientific_context"]["contract_version"] == "0.3.1"
    assert hints["x_major_tick_count_hint"] >= 0
    assert hints["y_major_tick_count_hint"] >= 0
    assert "x_minor_tick_count_hint" in hints
    assert "y_minor_tick_count_hint" in hints


def test_single_lower_axis_is_bottom_not_spurious_top(workspace_tmp: Path):
    path = workspace_tmp / "one_sided.png"
    image = Image.new("RGB", (640, 360), "white")
    draw = ImageDraw.Draw(image)
    draw.line((90, 300, 560, 300), fill="black", width=2)
    draw.line((90, 40, 90, 300), fill="black", width=2)
    image.save(path)
    sides = inspect_reference(path)["image"]["geometry_hints"]["frame_sides"]
    assert sides["bottom"] is True
    assert sides["top"] is False
    assert sides["left"] is True
    assert sides["right"] is False

