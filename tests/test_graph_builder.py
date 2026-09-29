import pandas as pd

import origin_bridge.graph_builder as graph_builder
from origin_bridge.graph_builder import (
    _add_confidence_band,
    _apply_pie_geometry,
    _error_column_index,
    _template_data_column_index,
    _shared_column_categories,
    template_by_family,
)


def test_shared_column_categories_keep_string_labels_and_reference_order():
    series = [
        {"data": {"x": ["Saline", "SPEN", "PEPRA"]}},
        {"data": {"x": ["Saline", "PEPRA", "SPNE"]}},
    ]
    assert _shared_column_categories(series) == ["Saline", "SPEN", "PEPRA", "SPNE"]


def test_shared_column_categories_align_sparse_numeric_labels():
    series = [
        {"data": {"x": [1, 3], "y": [10, 30]}},
        {"data": {"x": [3, 1], "y": [31, 11]}},
    ]
    assert _shared_column_categories(series) == [1, 3]


def test_pie_rgb_column_index_follows_optional_template_columns():
    assert _template_data_column_index({"x": [], "y": [], "color_rgb": []}, "color_rgb") == 2
    assert _template_data_column_index({"x": [], "y": [], "y_error": [], "x_error": [], "color_rgb": []}, "color_rgb") == 4


def test_error_column_mapping_pairs_sem_columns_with_y_series():
    frame = pd.DataFrame({"X": [1, 2], "Y1": [3, 4], "Y2": [5, 6], "SEM1": [0.1, 0.2], "SEM2": [0.3, 0.4]})
    spec = {"statistics": {"error_type": "sem", "error_columns": {"sem": ["SEM1", "SEM2"]}}}
    mapping = {"x": "X", "y": "Y1", "series": ["Y2"]}
    assert _error_column_index(frame, spec, mapping, "y", 0) == 3
    assert _error_column_index(frame, spec, mapping, "y", 1) == 4


def test_error_column_mapping_uses_one_shared_error_column():
    frame = pd.DataFrame({"X": [1, 2], "Y1": [3, 4], "Y2": [5, 6], "SD": [0.1, 0.2]})
    spec = {"statistics": {"error_type": "sd", "error_columns": {"sd": ["SD"]}}}
    assert _error_column_index(frame, spec, {}, "y", 0) == 3
    assert _error_column_index(frame, spec, {}, "y", 1) == 3


class _Layer:
    def __init__(self):
        self.calls = []

    def add_plot(self, worksheet, **kwargs):
        self.calls.append(kwargs)
        return object()

    def group(self):
        self.grouped = True

    def rescale(self):
        self.rescaled = True


class _Graph:
    def __init__(self, layer):
        self.layer = layer

    def __getitem__(self, index):
        return self.layer


def test_standard_builder_passes_sem_error_column_to_origin(monkeypatch):
    frame = pd.DataFrame({"X": [1, 2], "Y": [3, 4], "SD": [0.1, 0.2]})
    layer = _Layer()
    graph = _Graph(layer)
    monkeypatch.setattr(graph_builder, "apply_layer_style", lambda *args, **kwargs: [])
    monkeypatch.setattr(graph_builder, "apply_annotations", lambda *args, **kwargs: [])
    monkeypatch.setattr(graph_builder, "apply_plot_style", lambda *args, **kwargs: [])
    monkeypatch.setattr(graph_builder, "apply_error_bar_style", lambda *args, **kwargs: [])
    spec = {
        "graph_family": "column",
        "data_mapping": {"x": "X", "numeric_columns": ["Y"]},
        "statistics": {"error_type": "sd", "error_columns": {"sd": ["SD"]}},
        "style": {"error_bars": {"direction": "both"}},
    }
    graph_builder._add_standard_plots(graph, object(), frame, spec)
    assert layer.calls[0]["colx"] == 0
    assert layer.calls[0]["coly"] == 1
    assert layer.calls[0]["colyerr"] == 2


def test_template_sheet_has_deterministic_fallback_name(monkeypatch):
    calls = {}

    class Sheet:
        def set_labels(self, labels):
            calls["labels"] = labels

        def set_label(self, *args):
            calls.setdefault("short_labels", []).append(args)

    def fake_add_dataframe(op, frame, name, book=None):
        calls["name"] = name
        return Sheet()

    monkeypatch.setattr(graph_builder, "add_dataframe", fake_add_dataframe)
    graph_builder._add_template_sheet(
        object(), {"id": "S1", "name": "Series", "data": {"x": [1], "y": [2]}}
    )
    assert calls["name"] == "S1_Data"


def test_confidence_band_adds_two_editable_lines_and_fill_to_next(monkeypatch):
    class Plot:
        def __init__(self):
            self.calls = []
            self.color = None
            self.symbol_kind = None
            self.transparency = None

        def set_float(self, *args):
            self.calls.append(("set_float", args))

        def set_fill_area(self, **kwargs):
            self.calls.append(("set_fill_area", kwargs))

    class Layer:
        def __init__(self):
            self.plots = []

        def add_plot(self, worksheet, **kwargs):
            plot = Plot()
            plot.add_kwargs = kwargs
            self.plots.append(plot)
            return plot

    monkeypatch.setattr("originpro.utils.ocolor", lambda value: 123)
    layer = Layer()
    plots = _add_confidence_band(layer, object(), 2, 4, 5, {"color": "#336699"})
    assert len(plots) == 2
    assert [plot.add_kwargs for plot in layer.plots] == [
        {"coly": 4, "colx": 2, "type": "l"},
        {"coly": 5, "colx": 2, "type": "l"},
    ]
    assert any(call[0] == "set_fill_area" for call in layer.plots[0].calls)


def test_pie_geometry_uses_flat_view_for_plain_pie():
    class Plot:
        def __init__(self):
            self.commands = []

        def set_cmd(self, *commands):
            self.commands.extend(commands)

    plot = Plot()
    applied = _apply_pie_geometry(plot, "pie", {})
    assert "view_angle" in applied
    assert plot.commands == ["-pgpva 90"]


def test_pie3d_geometry_keeps_editable_view_parameters():
    class Plot:
        def __init__(self):
            self.commands = []

        def set_cmd(self, *commands):
            self.commands.extend(commands)

    plot = Plot()
    _apply_pie_geometry(plot, "pie3d", {
        "start_azimuth": 20, "thickness": 12,
        "horizontal_offset": 3, "doughnut_hole": 35,
    })
    assert plot.commands[0] == "-pgpva 45"
    assert "-pgpa 20" in plot.commands
    assert "-pgpho 3" in plot.commands
    assert "-pgpdh 35" in plot.commands


def test_pie_templates_separate_flat_and_perspective_defaults():
    templates = template_by_family()
    assert templates["pie"].lower() == "pie"
    assert templates["pie3d"].lower() == "pie.otpu"
