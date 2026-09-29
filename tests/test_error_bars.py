import pytest

from origin_bridge.error_bars import apply_error_bar_style


class FakePlot:
    def __init__(self):
        self.commands = []
        self.properties = []

    def set_cmd(self, *commands):
        self.commands.append(list(commands))

    def set_int(self, prop, value):
        self.properties.append((prop, value))


def test_error_bar_style_maps_documented_commands_and_x_y_directions():
    plot = FakePlot()
    applied = apply_error_bar_style(plot, {
        "y": {"color": "#ff0000", "line_width": 1.25, "cap_width": 6, "direction": "plus",
              "symbol_through": True},
        "x": {"color": (0, 128, 255), "direction": "minus"},
    })

    assert applied == [
        "y.direction", "y.line_width", "y.cap_width", "y.color", "y.symbol_through",
        "x.direction", "x.color",
    ]
    assert plot.commands == [
        ["-erdy 1", "-erw 1.25", "-erwc 6", "-cr color(255,0,0)"],
        ["-erdx 2", "-cr color(0,128,255)"],
    ]
    assert plot.properties == [("errorbar2d.throughsymbol", 1)]


def test_error_bar_style_accepts_flat_y_style_and_rejects_ambiguous_direction():
    plot = FakePlot()
    assert apply_error_bar_style(plot, {"direction": "both", "line_width": 0.5}) == [
        "y.direction", "y.line_width"
    ]
    assert plot.commands == [["-erdy 0", "-erw 0.5"]]
    with pytest.raises(ValueError, match="cannot combine"):
        apply_error_bar_style(FakePlot(), {"y": {"direction": "plus", "minus": True}})
