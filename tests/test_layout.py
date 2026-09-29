from mcp_server.layout import resolve_layout


def test_layout_anchors_page_to_twelve_point_ticks_without_mutating_input():
    source = {
        "schema_version": "1.0",
        "graph_family": "line",
        "data_mapping": {},
        "statistics": {},
        "axes": {"x": {"tick_label_font_pt": 8}, "y": {"tick_label_font_pt": 8}},
        "style": {
            "page_aspect_ratio": 3.0,
            "plot_frame": {"left": 18, "top": 12, "right": 12, "bottom": 18},
            "estimated_text_height_ratio": 0.04,
            "tick_label_font_pt": 8,
            "line_width": 1,
        },
        "output": {"project_format": "opju", "preview_formats": ["png"]},
    }
    result = resolve_layout(source)

    assert source["style"]["tick_label_font_pt"] == 8
    assert result["style"]["tick_label_font_pt"] == 12
    assert result["axes"]["x"]["tick_label_font_pt"] == 12
    assert result["axes"]["y"]["tick_label_font_pt"] == 12
    assert result["style"]["page_aspect_ratio"] == 3.0
    assert result["style"]["page_width_mm"] <= 360
    assert abs(result["style"]["page_height_mm"] - result["style"]["page_width_mm"] / 3) < 1e-5
    assert result["style"]["open_zoom_percent"] == 100.0
    assert result["layout_resolution"]["policy"] == "tick_font_anchor"
