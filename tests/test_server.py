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


def test_prepare_reference_template_defaults_to_no_origin_popup(workspace_tmp: Path):
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
        str(image), spec, str(workspace_tmp / "output-default")
    )
    assert result["status"] == "prepared"
    assert result["render_deferred"] is True
    assert Path(result["style_manifest"]).is_file()


def test_apply_active_format_forwards_to_origin_bridge(monkeypatch):
    import mcp_server.server as server

    calls = {}

    def fake_apply(path, **kwargs):
        calls["path"] = path
        calls.update(kwargs)
        return {"status": "applied", "mode": "active_graph"}

    monkeypatch.setattr(server, "apply_format_to_active_graph", fake_apply)
    result = server.apply_active_format(
        "format_parameters.json",
        graph_name="Graph2",
        layer_index=1,
        show_origin=False,
        preview_path="preview.png",
    )
    assert result["status"] == "applied"
    assert calls == {
        "path": "format_parameters.json",
        "graph_name": "Graph2",
        "layer_index": 1,
        "show_origin": False,
        "export_preview_path": "preview.png",
    }


def test_stage_format_clipboard_forwards_to_origin_bridge(monkeypatch):
    import mcp_server.server as server

    calls = {}

    def fake_stage(path, **kwargs):
        calls["path"] = path
        calls.update(kwargs)
        return {"status": "staged", "clipboard": "origin_format"}

    monkeypatch.setattr(server, "stage_origin_format_clipboard", fake_stage)
    result = server.stage_format_clipboard(
        "reference.opju", graph_name="Graph1", scope="fonts", show_origin=False
    )
    assert result["status"] == "staged"
    assert calls == {
        "path": "reference.opju",
        "graph_name": "Graph1",
        "scope": "fonts",
        "show_origin": False,
    }
