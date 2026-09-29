from __future__ import annotations

import math
import pytest

from origin_bridge.text_layout import (
    AxisGeometry,
    FrameGeometry,
    TextLayout,
    layout_text_label,
    normalize_origin_markup,
    text_value,
)


class FakeLabel:
    def __init__(self, *, x=5.0, y=10.0, dx=2.0, dy=4.0):
        self.props = {"x": x, "y": y, "dx": dx, "dy": dy}
        self.calls = []

    def get_float(self, name):
        return float(self.props[name])

    def set_float(self, name, value):
        self.calls.append((name, float(value)))
        self.props[name] = float(value)

    def set_int(self, name, value):
        self.calls.append((name, int(value)))
        self.props[name] = int(value)

    def set_str(self, name, value):
        self.calls.append((name, value))
        self.props[name] = value


def test_data_anchor_uses_origin_measured_dx_dy_for_center_middle():
    label = FakeLabel(x=5, y=10, dx=2, dy=4)
    result = layout_text_label(
        label,
        TextLayout(x=20, y=30, h_anchor="center", v_anchor="middle", paragraph_align="center", rotation=90),
    )

    assert result.attach == 2
    assert label.props["x1"] == pytest.approx(19)
    assert label.props["y1"] == pytest.approx(32)
    assert label.props["justify"] == 1
    assert label.props["rotate"] == 90
    assert result.measured_dx == 2
    assert result.measured_dy == 4


def test_data_right_bottom_anchor_uses_top_left_origin_convention():
    label = FakeLabel(dx=1.25, dy=5.5)
    result = layout_text_label(label, TextLayout(x=7, y=3, h_anchor="right", v_anchor="bottom"))

    assert result.x1 == pytest.approx(5.75)
    assert result.y1 == pytest.approx(8.5)


def test_page_anchor_maps_rich_text_size_on_log_x_axis():
    label = FakeLabel(x=1.0, y=10.0, dx=0.2, dy=2.0)
    frame = FrameGeometry(
        left=0.1,
        top=0.1,
        width=0.8,
        height=0.8,
        x_axis=AxisGeometry(0.1, 10.0, log=True),
        y_axis=AxisGeometry(0.0, 20.0),
    )
    result = layout_text_label(
        label,
        TextLayout(x=0.5, y=0.5, coordinate_space="page", h_anchor="center", v_anchor="middle"),
        frame=frame,
    )

    assert result.attach == 1
    assert result.page_width == pytest.approx(0.8 * (math.log10(1.1) - math.log10(0.9)) / 2.0, rel=1e-6)
    assert result.x1 == pytest.approx(0.5 - result.page_width / 2)
    assert result.y1 == pytest.approx(0.5 - result.page_height / 2)
    assert label.props["attach"] == 1


def test_page_requires_explicit_geometry_instead_of_guessing():
    with pytest.raises(ValueError, match="page text placement requires"):
        layout_text_label(FakeLabel(), TextLayout(x=0.5, y=0.5, coordinate_space="page"))


def test_unicode_scientific_runs_are_converted_to_origin_markup():
    assert normalize_origin_markup("CD8⁺ T cell") == r"CD8\+(+) T cell"
    assert normalize_origin_markup("PEPRA₍EE₎") == r"PEPRA\-(EE)"
    # Explicit markup is stable across repeated normalization.
    assert normalize_origin_markup(r"IC\-(50) (µg ml\+(-1))") == r"IC\-(50) (µg ml\+(-1))"


def test_text_value_prefers_explicit_markup_field():
    assert text_value({"text": "plain", "text_markup": r"IC\-(50)"}) == r"IC\-(50)"
