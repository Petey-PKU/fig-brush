from pathlib import Path

import pytest

from mcp_server.template import build_style_manifest, pixel_to_value, prepare_template, validate_template


def minimal_spec():
    return {
        "schema_version": "2.0", "mode": "reference_template",
        "canvas": {"width_px": 100, "height_px": 80, "font_reference_px": 10, "font_anchor_pt": 12},
        "style": {"page_aspect_ratio": 1.25},
        "panels": [{"id": "Panel1", "frame_px": [10, 10, 90, 70], "axes": {
            "x": {"min": 0, "max": 10}, "y": {"min": 0, "max": 10}}, "series": [{
                "id": "Series1", "name": "Series 1", "kind": "line", "data": {"x": [0, 5, 10], "y": [0, 4, 2]}}]}],
        "output": {"preview_formats": ["png"]},
    }


def test_reference_template_schema_rejects_private_or_malformed_data():
    validate_template(minimal_spec())
    broken = minimal_spec()
    broken["panels"][0]["series"][0]["data"]["y"] = [1]
    with pytest.raises(Exception):
        validate_template(broken)


def test_pixel_calibration_linear_and_log():
    axis = {"min": 0, "max": 10}
    assert pixel_to_value(50, 0, 100, axis) == 5
    assert pixel_to_value(50, 0, 100, {"min": 1, "max": 100, "scale": "log10"}) == pytest.approx(10)


def test_prepare_template_records_reference_only_policy():
    from PIL import Image
    import shutil

    root = Path(__file__).resolve().parent / ".runtime" / "template_unit"
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True)
    image = root / "ref.png"
    Image.new("RGB", (100, 80), "white").save(image)
    result = prepare_template(str(image), minimal_spec(), str(root / "output"))
    assert result["spec"]["data_policy"]["original_data_recovered"] is False
    assert Path(result["template_spec"]).is_file()
    assert Path(result["style_manifest"]).is_file()
    style_manifest = __import__("json").loads(
        (root / "output" / "style_manifest.json").read_text(encoding="utf-8")
    )
    assert style_manifest["kind"] == "origin_visual_style"
    assert style_manifest["style_only"] is True
    assert "data" not in style_manifest["panels"][0]["series"][0]
    assert Path(root / "output" / "替换数据说明.md").is_file()
    assert result["manifest"]["series"][0]["columns"] == {"A": "x", "B": "y"}
    shutil.rmtree(root, ignore_errors=True)


def test_prepare_template_uses_fast_visual_placeholders_by_default():
    """Approximation changes precision, never axis geometry or marker count."""
    from PIL import Image
    import shutil

    root = Path(__file__).resolve().parent / ".runtime" / "approximate_placeholders"
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True)
    image = root / "ref.png"
    Image.new("RGB", (100, 80), "white").save(image)
    spec = minimal_spec()
    series = spec["panels"][0]["series"][0]
    series["data"] = {"x": [6.589, 6.641, 6.712], "y": [1.2345, 2.3456, 3.4567]}
    result = prepare_template(str(image), spec, str(root / "output"))
    rendered = result["spec"]
    policy = rendered["placeholder_policy"]
    data = rendered["panels"][0]["series"][0]["data"]
    assert policy["mode"] == "approximate_visual"
    assert policy["fit_dense_points"] == 120
    assert data["x"] == [6.59, 6.64, 6.71]
    assert data["y"] == [1.23, 2.35, 3.46]
    assert len(data["x"]) == 3
    assert rendered["panels"][0]["axes"]["x"] == {"min": 0, "max": 10}
    assert result["manifest"]["data_policy"]["placeholder_mode"] == "approximate_visual"
    assert "快速视觉占位策略" in (root / "output" / "替换数据说明.md").read_text(encoding="utf-8")
    shutil.rmtree(root, ignore_errors=True)


def test_placeholder_policy_exact_preserves_values_and_fit_density():
    from PIL import Image
    import shutil

    root = Path(__file__).resolve().parent / ".runtime" / "exact_placeholders"
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True)
    image = root / "ref.png"
    Image.new("RGB", (100, 80), "white").save(image)
    spec = minimal_spec()
    spec["placeholder_policy"] = {"mode": "exact"}
    series = spec["panels"][0]["series"][0]
    series["kind"] = "line_symbol"
    series["data"] = {"x": [1.23456, 2.34567, 3.45678], "y": [1.11111, 2.22222, 3.33333]}
    series["marker_data"] = dict(series["data"])
    series["fit_request"] = {"model": "linear", "points": "marker_data"}
    result = prepare_template(str(image), spec, str(root / "output"))
    rendered = result["spec"]["panels"][0]["series"][0]
    assert rendered["data"]["x"][0] == pytest.approx(1.23456)
    assert len(rendered["line_data"]["x"]) == 400
    assert result["manifest"]["placeholder_policy"]["mode"] == "exact"
    shutil.rmtree(root, ignore_errors=True)


def test_approximate_placeholder_uses_compact_default_fit_sampling():
    from PIL import Image
    import shutil

    root = Path(__file__).resolve().parent / ".runtime" / "approximate_fit_density"
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True)
    image = root / "ref.png"
    Image.new("RGB", (100, 80), "white").save(image)
    spec = minimal_spec()
    series = spec["panels"][0]["series"][0]
    series["kind"] = "line_symbol"
    series["data"] = {"x": [1, 2, 3], "y": [2, 4, 3]}
    series["marker_data"] = dict(series["data"])
    series["fit_request"] = {"model": "linear", "points": "marker_data"}
    result = prepare_template(str(image), spec, str(root / "output"))
    rendered = result["spec"]["panels"][0]["series"][0]
    assert len(rendered["line_data"]["x"]) == 120
    assert rendered["fit_request"]["dense_points"] == 120
    shutil.rmtree(root, ignore_errors=True)


def test_compare_reference_creates_diagnostic_directory(workspace_tmp: Path):
    from PIL import Image
    from mcp_server.template import compare_reference

    reference = workspace_tmp / "reference.png"
    preview = workspace_tmp / "preview.png"
    Image.new("RGB", (32, 24), "white").save(reference)
    Image.new("RGB", (64, 48), "white").save(preview)
    result = compare_reference(str(reference), str(preview), str(workspace_tmp / "diagnostics"))

    assert result["reference_size"] == [32, 24]
    assert (workspace_tmp / "diagnostics" / "comparison_overlay.png").is_file()
    assert (workspace_tmp / "diagnostics" / "visual_comparison.json").is_file()


def test_reference_template_accepts_editable_doughnut_categories():
    spec = minimal_spec()
    panel = spec["panels"][0]
    panel["graph_family"] = "doughnut"
    panel["series"][0]["kind"] = "doughnut"
    panel["series"][0]["data"] = {"x": ["A", "B"], "y": [25, 75]}
    validate_template(spec)


def test_reference_template_accepts_explicit_pie3d_geometry():
    spec = minimal_spec()
    panel = spec["panels"][0]
    panel["graph_family"] = "pie3d"
    panel["series"][0]["kind"] = "pie3d"
    panel["series"][0]["data"] = {"x": ["A", "B", "C"], "y": [20, 35, 45]}
    panel["series"][0]["style"] = {
        "pie_geometry": "3d", "view_angle": 42,
        "start_azimuth": 15, "thickness": 10,
    }
    validate_template(spec)


def test_approximate_policy_preserves_pie_category_labels():
    from PIL import Image
    import shutil

    root = Path(__file__).resolve().parent / ".runtime" / "pie_categories"
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True)
    image = root / "ref.png"
    Image.new("RGB", (100, 80), "white").save(image)
    spec = minimal_spec()
    panel = spec["panels"][0]
    panel["graph_family"] = "pie"
    panel["series"][0]["kind"] = "pie"
    panel["series"][0]["data"] = {"x": ["B cells", "T cells"], "y": [57.123, 42.877]}
    panel["series"][0]["marker_data"] = {"x": ["B cells", "T cells"], "y": [57.123, 42.877]}
    result = prepare_template(str(image), spec, str(root / "output"))
    series = result["spec"]["panels"][0]["series"][0]
    assert series["data"]["x"] == ["B cells", "T cells"]
    assert series["marker_data"]["x"] == ["B cells", "T cells"]
    assert series["data"]["y"] == [57.1, 42.9]
    shutil.rmtree(root, ignore_errors=True)


def test_reference_template_accepts_editable_heatmap_matrix():
    spec = minimal_spec()
    panel = spec["panels"][0]
    panel["graph_family"] = "heatmap"
    panel.pop("series")
    panel["matrix"] = {
        "values": [[0.2, 0.8], [1.5, 2.0]],
        "x_labels": ["A", "B"],
        "y_labels": ["low", "high"],
        "colormap": "Thermometer.pal",
    }
    validate_template(spec)


def test_prepare_template_applies_only_explicit_marker_fit_request():
    from PIL import Image
    import shutil

    root = Path(__file__).resolve().parent / ".runtime" / "fit_request"
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True)
    image = root / "ref.png"
    Image.new("RGB", (100, 80), "white").save(image)
    spec = minimal_spec()
    series = spec["panels"][0]["series"][0]
    series["kind"] = "line_symbol"
    series["data"] = {"x": [4.5, 5.0, 5.5, 6.0, 6.5], "y": [95, 88, 56, 18, 4]}
    series["marker_data"] = dict(series["data"])
    series["fit_request"] = {
        "model": "boltzmann",
        "points": "marker_data",
        "options": {"x_range": [4.5, 7.0], "dense_points": 60},
    }
    result = prepare_template(str(image), spec, str(root / "output"))
    rendered = result["spec"]["panels"][0]["series"][0]
    assert len(rendered["line_data"]["x"]) == 60
    assert len(rendered["line_data"]["lower"]) == 60
    assert len(rendered["line_data"]["upper"]) == 60
    assert rendered["fit_metadata"]["line_generated_from_markers"] is True
    assert rendered["fit_metadata"]["confidence_band"]["available"] is True
    assert rendered["fit_request"]["x_range"] == [4.5, 7.0]
    assert result["manifest"]["series"][0]["line_rows"] == 60
    assert "FitLower" in result["manifest"]["series"][0]["columns"]
    assert "FitUpper" in result["manifest"]["series"][0]["columns"]
    shutil.rmtree(root, ignore_errors=True)


def test_template_allows_negative_linear_fit_range_but_model_checks_log_domain():
    from PIL import Image
    import shutil

    root = Path(__file__).resolve().parent / ".runtime" / "fit_model_domains"
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True)
    image = root / "ref.png"
    Image.new("RGB", (100, 80), "white").save(image)

    spec = minimal_spec()
    series = spec["panels"][0]["series"][0]
    series["kind"] = "line_symbol"
    series["data"] = {"x": [-2, -1, 0, 1, 2], "y": [1, 3, 5, 7, 9]}
    series["marker_data"] = dict(series["data"])
    series["fit_request"] = {"model": "linear", "points": "marker_data",
                              "options": {"x_range": [-3, 3], "dense_points": 40}}
    result = prepare_template(str(image), spec, str(root / "output"))
    fit_meta = result["spec"]["panels"][0]["series"][0]["fit_metadata"]
    assert fit_meta["model"] == "linear_regression"
    assert fit_meta["line_domain"] == [-3.0, 3.0]

    bad = minimal_spec()
    bad_series = bad["panels"][0]["series"][0]
    bad_series["kind"] = "line_symbol"
    bad_series["data"] = {"x": [1, 2, 3, 4], "y": [90, 70, 30, 5]}
    bad_series["marker_data"] = dict(bad_series["data"])
    bad_series["fit_request"] = {"model": "4pl", "points": "marker_data",
                                  "options": {"x_range": [-1, 4]}}
    with pytest.raises(Exception, match="positive"):
        prepare_template(str(image), bad, str(root / "bad-output"))
    shutil.rmtree(root, ignore_errors=True)


def test_marker_data_does_not_trigger_a_fit_without_fit_request():
    from PIL import Image
    import shutil

    root = Path(__file__).resolve().parent / ".runtime" / "fit_opt_in"
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True)
    image = root / "ref.png"
    Image.new("RGB", (100, 80), "white").save(image)
    spec = minimal_spec()
    series = spec["panels"][0]["series"][0]
    series["marker_data"] = {"x": [1, 2, 3, 4], "y": [1, 3, 2, 1]}
    result = prepare_template(str(image), spec, str(root / "output"))
    rendered = result["spec"]["panels"][0]["series"][0]
    assert "line_data" not in rendered
    assert "fit_metadata" not in rendered
    shutil.rmtree(root, ignore_errors=True)


def test_prepare_template_reuses_shared_x_for_same_observations():
    from PIL import Image
    import shutil

    root = Path(__file__).resolve().parent / ".runtime" / "shared_x"
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True)
    image = root / "ref.png"
    Image.new("RGB", (100, 80), "white").save(image)
    spec = minimal_spec()
    panel = spec["panels"][0]
    panel["series"][0]["kind"] = "line"
    panel["series"][0]["data"] = {"x": [1, 2, 3], "y": [2, 4, 3]}
    panel["series"].append({
        "id": "Series2", "name": "Series 2", "kind": "line",
        "data": {"x": [1, 2, 3], "y": [1, 3, 5]},
    })
    result = prepare_template(str(image), spec, str(root / "output"))
    rendered_panel = result["spec"]["panels"][0]
    assert rendered_panel["shared_x_header"] == "Panel1_X"
    assert [item["columns"]["X"] for item in result["manifest"]["series"]] == ["Panel1_X", "Panel1_X"]
    shutil.rmtree(root, ignore_errors=True)


def test_build_style_manifest_excludes_observations_and_keeps_visual_contract():
    spec = minimal_spec()
    series = spec["panels"][0]["series"][0]
    series["data"] = {"x": [1, 2, 3], "y": [9, 8, 7], "y_error": [0.2, 0.3, 0.4]}
    series["style"] = {"color": "#B00000", "symbol": 19, "symbol_size": 8, "line_width": 2}
    spec["panels"][0]["legend"] = {"visible": True, "position": "top_right"}
    style_manifest = build_style_manifest(spec)
    panel = style_manifest["panels"][0]
    item = panel["series"][0]
    assert item["style"] == series["style"]
    assert panel["frame_fraction"] == {"left": 0.1, "top": 0.125, "right": 0.9, "bottom": 0.875}
    assert panel["axes"]["x"]["min"] == 0
    assert "major_tick_increment" not in panel["axes"]["x"]
    assert "data" not in item
    assert "marker_data" not in item
    assert "y_error" not in item


def test_style_manifest_keeps_axis_format_but_excludes_fit_operations():
    spec = minimal_spec()
    axis = spec["panels"][0]["axes"]["y"]
    axis.update({"major_tick_increment": 2, "major_tick_count": 6,
                 "minor_tick_count": 1, "show_labels": True, "decimals": 0})
    series = spec["panels"][0]["series"][0]
    series["fit_request"] = {"model": "linear", "dense_points": 80}
    series["fit_metadata"] = {"model": "linear", "covariance": [[1, 2], [2, 4]],
                               "line_generated_from_markers": True}
    style_manifest = build_style_manifest(spec)
    panel = style_manifest["panels"][0]
    assert panel["axes"]["y"]["major_tick_increment"] == 2
    assert panel["axes"]["y"]["show_labels"] is True
    item = panel["series"][0]
    assert "fit_request" not in item
    assert "fit_metadata" not in item
    assert style_manifest["application"]["template_type"] == "standard_graph_template"
    assert style_manifest["application"]["data_required_to_read"] is False


def test_prepare_template_keeps_marker_x_independent_in_mixed_column_panel():
    from PIL import Image
    import shutil

    root = Path(__file__).resolve().parent / ".runtime" / "mixed_column_x"
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True)
    image = root / "ref.png"
    Image.new("RGB", (100, 80), "white").save(image)
    spec = minimal_spec()
    panel = spec["panels"][0]
    panel["series"][0]["kind"] = "column"
    panel["series"][0]["data"] = {"x": [1, 2, 3], "y": [10, 20, 30]}
    panel["series"].append({
        "id": "Series2", "name": "Markers", "kind": "scatter",
        "data": {"x": [0.85, 1.15, 2.1], "y": [11, 15, 24]},
    })
    result = prepare_template(str(image), spec, str(root / "output"))
    rendered_panel = result["spec"]["panels"][0]
    assert rendered_panel["shared_x_header"] == "Panel1_X"
    assert [item["columns"]["X"] for item in result["manifest"]["series"]] == [
        "Panel1_X", "Series2_X"
    ]
    shutil.rmtree(root, ignore_errors=True)


def test_marker_sheet_keeps_error_columns_when_marker_data_omits_them():
    from PIL import Image
    import shutil

    root = Path(__file__).resolve().parent / ".runtime" / "marker_errors"
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True)
    image = root / "ref.png"
    Image.new("RGB", (100, 80), "white").save(image)
    spec = minimal_spec()
    series = spec["panels"][0]["series"][0]
    series["data"] = {"x": [1, 2, 3], "y": [2, 4, 3], "y_error": [0.2, 0.3, 0.25]}
    series["marker_data"] = {"x": [1, 2, 3], "y": [2, 4, 3]}
    result = prepare_template(str(image), spec, str(root / "output"))
    assert result["manifest"]["series"][0]["columns"]["YErr"] == "Series1_YErr"
    shutil.rmtree(root, ignore_errors=True)
