from __future__ import annotations

from origin_bridge.style_apply import format_parameters_to_style


class _Axis:
    def set_limits(self, **kwargs):
        self.limits = kwargs

    def set_int(self, key, value):
        setattr(self, key.replace(".", "_"), value)

    def set_float(self, key, value):
        setattr(self, key.replace(".", "_"), value)


class _Layer:
    def __init__(self):
        self.axes = {"x": _Axis(), "y": _Axis()}

    def axis(self, name):
        return self.axes.get(name)

    def label(self, _name):
        return None

    def set_int(self, key, value):
        setattr(self, key.replace(".", "_"), value)

    def set_float(self, key, value):
        setattr(self, key.replace(".", "_"), value)


class _Page:
    name = "Graph1"

    def __init__(self):
        self.layer = _Layer()

    def __getitem__(self, index):
        if index != 0:
            raise IndexError(index)
        return self.layer


class _Origin:
    def __init__(self, path):
        self.page = _Page()
        self.path = path
        self.closed = False

    def graph_list(self, _kind):
        return [self.page]

    def save(self, destination):
        open(destination, "wb").write(b"opju")
        return True

    def exit(self):
        self.closed = True


def test_format_parameters_translate_to_origin_style_fields():
    style, warnings = format_parameters_to_style(
        {
            "kind": "origin_format_parameters",
            "canvas": {"page_aspect_ratio": 1.5, "width_px": 1200},
            "plot_frame": {
                "margins_percent": {"left": 10, "top": 12, "right": 8, "bottom": 15},
                "sides": {"top": False, "right": False, "bottom": True, "left": True},
            },
            "axes": {
                "x": {
                    "scale": "linear",
                    "major_tick_count": 5,
                    "major_tick_length_pt_96dpi": 3,
                    "tick_direction": "out",
                }
            },
            "typography": {"base_font_pt": 9, "font_family": "Arial"},
        }
    )
    assert style["page_aspect_ratio"] == 1.5
    assert style["page_width_px"] == 1200
    assert style["plot_frame"]["left"] == 10.0
    assert style["frame_sides"]["bottom"] is True
    assert style["axes"]["x"]["major_tick_length"] == 3
    assert style["tick_label_font_pt"] == 9.0
    assert any("font_family" in warning for warning in warnings)


def test_incomplete_measurements_are_skipped_with_warning():
    style, warnings = format_parameters_to_style(
        {
            "kind": "origin_format_parameters",
            "plot_frame": {"margins_percent": {"left": 10}},
            "axes": {"x": {"major_tick_count": "unknown"}},
        }
    )
    assert "plot_frame" not in style
    assert "axes" not in style
    assert any("margins" in warning for warning in warnings)


def test_apply_format_saves_a_copy_and_preserves_source(workspace_tmp, monkeypatch):
    import origin_bridge.style_apply as style_apply

    source = workspace_tmp / "input.opju"
    source.write_bytes(b"original")
    origin = _Origin(source)
    monkeypatch.setattr(style_apply, "open_origin_project", lambda *_args, **_kwargs: origin)
    result = style_apply.apply_format_to_project(
        str(source),
        {
            "kind": "origin_format_parameters",
            "canvas": {"page_aspect_ratio": 1.5, "width_px": 1000},
            "plot_frame": {"margins_percent": {"left": 10, "top": 10, "right": 10, "bottom": 10}},
            "axes": {"x": {"scale": "linear"}},
        },
        export_preview=False,
    )
    assert result["status"] == "applied"
    assert (workspace_tmp / "input_formatted.opju").read_bytes() == b"opju"
    assert source.read_bytes() == b"original"
    assert origin.closed is True


def test_apply_format_to_active_graph_uses_origin_active_layer(monkeypatch):
    import origin_bridge.style_apply as style_apply

    class _Graph(_Page):
        name = "Graph2"

        def __init__(self):
            super().__init__()
            self.active = 2
            self.page_props = {}

        def __len__(self):
            return 2

        def get_int(self, key):
            assert key == "active"
            return self.active

        def set_int(self, key, value):
            self.page_props[key] = value

        def set_float(self, key, value):
            self.page_props[key] = value

        def __getitem__(self, index):
            if index not in (0, 1):
                raise IndexError(index)
            return self.layer

    class _ActiveOrigin:
        def __init__(self, graph):
            self.graph = graph

        def find_graph(self, name=""):
            assert name == ""
            return self.graph

        def set_show(self, _show):
            return None

    graph = _Graph()
    monkeypatch.setattr(style_apply, "_import_originpro", lambda: _ActiveOrigin(graph))
    result = style_apply.apply_format_to_active_graph(
        {
            "kind": "origin_format_parameters",
            "canvas": {"page_aspect_ratio": 1.5, "width_px": 1000},
            "plot_frame": {"margins_percent": {"left": 10, "top": 10, "right": 10, "bottom": 10}},
            "axes": {"x": {"scale": "linear"}},
        }
    )
    assert result["status"] == "applied"
    assert result["mode"] == "active_graph"
    assert result["graph"] == "Graph2"
    assert result["layer_index"] == 1
    assert result["saved"] is False
    assert "page.width" in result["applied"]
