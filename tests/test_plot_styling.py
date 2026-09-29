from origin_bridge.plot_styling import apply_plot_border
from origin_bridge.styles import apply_layer_style


class FakePlot:
    def __init__(self):
        self.calls = []

    def set_cmd(self, *commands):
        self.calls.append(commands)


class FakeAxis:
    def __init__(self):
        self.scale = None
        self.properties = []

    def set_limits(self, **kwargs):
        self.properties.append(("limits", kwargs))

    def set_int(self, prop, value):
        self.properties.append((prop, value))

    def set_float(self, prop, value):
        self.properties.append((prop, value))


class FakeLayer:
    def __init__(self):
        self.axes = {"x": FakeAxis(), "y": FakeAxis()}

    def axis(self, name):
        return self.axes.get(name)

    def set_int(self, prop, value):
        return None

    def set_float(self, prop, value):
        return None

    def label(self, name):
        return None


def test_column_border_uses_column_specific_switches():
    plot = FakePlot()
    applied = apply_plot_border(plot, {"border_width": 1.25, "border_color": "#102030"}, kind="column")
    assert applied == ["-pbw 1.25", "-pbc color(16,32,48)"]
    assert plot.calls == [("-pbw 1.25", "-pbc color(16,32,48)")]


def test_symbol_border_is_opt_in():
    plot = FakePlot()
    assert apply_plot_border(plot, {"border_width": 0.7}, kind="scatter") == ["-kh 0.7"]
    assert plot.calls == [("-kh 0.7",)]


def test_axis_scale_accepts_canonical_log10_and_linear_values():
    layer = FakeLayer()
    apply_layer_style(layer, {"axes": {"x": {"scale": "log10"}, "y": {"scale": "linear"}}})
    assert layer.axes["x"].scale == "log10"
    assert layer.axes["y"].scale == "linear"


def test_axis_scale_keeps_legacy_log_boolean():
    layer = FakeLayer()
    apply_layer_style(layer, {"axes": {"x": {"log": True}}})
    assert layer.axes["x"].scale == "log10"
