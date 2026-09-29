from pathlib import Path

from PIL import Image

from mcp_server.server import prepare_reference_template_tool


def test_prepare_reference_template_can_defer_origin_render(workspace_tmp: Path):
    image = workspace_tmp / "reference.png"
    Image.new("RGB", (100, 80), "white").save(image)
    spec = {
        "schema_version": "2.0", "mode": "reference_template",
        "canvas": {"width_px": 100, "height_px": 80, "font_reference_px": 10, "font_anchor_pt": 12},
        "style": {"page_aspect_ratio": 1.25},
        "panels": [{"id": "Panel1", "frame_px": [10, 10, 90, 70], "axes": {
            "x": {"min": 0, "max": 10}, "y": {"min": 0, "max": 10}}, "series": [{
                "id": "Series1", "name": "Series 1", "kind": "line",
                "data": {"x": [0, 5, 10], "y": [0, 4, 2]}}]}],
    }

    result = prepare_reference_template_tool(
        str(image), spec, str(workspace_tmp / "output"), render_origin=False
    )

    assert result["status"] == "prepared"
    assert result["render_deferred"] is True
    assert (workspace_tmp / "output" / "template_spec.json").is_file()
    assert not (workspace_tmp / "output" / "result.opju").exists()
