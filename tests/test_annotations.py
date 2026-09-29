import pandas as pd

from mcp_server.annotations import resolve_annotations
from origin_bridge.styles import apply_annotations


def _spec():
    return {
        "schema_version": "1.0",
        "graph_family": "line",
        "data_mapping": {"x": "m/z", "numeric_columns": ["intensity"]},
        "statistics": {},
        "axes": {
            "x": {"min": 60000, "max": 200000},
            "y": {"min": 0, "max": 1000},
        },
        "annotations": {
            "text_labels": [{"role": "peak_value", "text": "150446.009", "x": 150446.009, "y": 980}],
            # These coordinates imitate a reference screenshot. The resolver
            # must recenter them on the peak in the supplied data.
            "lines": [{"role": "peak_marker", "x1": 145000, "y1": 900, "x2": 155000, "y2": 900}],
        },
        "style": {},
        "output": {"project_format": "opju", "preview_formats": ["png"]},
    }


def test_peak_marker_follows_data_and_centers_label():
    frame = pd.DataFrame({"m/z": [149000, 150446, 151000], "intensity": [100, 930, 120]})
    result = resolve_annotations(_spec(), frame)
    label = result["annotations"]["text_labels"][0]
    line = result["annotations"]["lines"][0]

    assert label["role"] == "peak_value"
    assert label["align"] == "center"
    assert label["x"] == 150446.0
    assert line["role"] == "peak_marker"
    assert line["x1"] < 150446 < line["x2"]
    assert line["y1"] == line["y2"]
    assert line["anchor_y"] == line["y1"]
    assert result["annotations"]["resolution"]["policy"] == "data_relative_peak_marker"


def test_plain_horizontal_statistical_lines_are_not_peak_resolved():
    spec = _spec()
    spec["annotations"] = {
        "text_labels": [{"text": "*", "x": 1.4, "y": 34}],
        "lines": [{"x1": 1.2, "y1": 34, "x2": 1.8, "y2": 34}],
    }
    frame = pd.DataFrame({"m/z": [149000, 150446, 151000], "intensity": [100, 930, 120]})
    result = resolve_annotations(spec, frame)
    assert result["annotations"]["text_labels"][0] == spec["annotations"]["text_labels"][0]
    assert result["annotations"]["lines"][0] == spec["annotations"]["lines"][0]
    assert "resolution" not in result["annotations"]


class _Label:
    def __init__(self, text):
        self.text = text
        self.props = {"x": 0.0, "y": 0.0, "dx": 0.1, "dy": 0.05}

    def set_int(self, name, value):
        self.props[name] = int(value)

    def set_float(self, name, value):
        self.props[name] = float(value)

    def get_float(self, name):
        return float(self.props[name])


class _Line:
    def __init__(self, coords):
        self.coords = tuple(coords)
        self.props = {}
        self.width = None
        self.color = None

    def set_int(self, name, value):
        self.props[name] = int(value)

    def set_float(self, name, value):
        self.props[name] = float(value)


class _AnnotationLayer:
    def __init__(self):
        self.labels = []
        self.lines = []

    def add_label(self, text, x, y):
        label = _Label(text)
        label.props.update({"x": x, "y": y})
        self.labels.append(label)
        return label

    def add_line(self, x1, y1, x2, y2):
        line = _Line((x1, y1, x2, y2))
        self.lines.append(line)
        return line


def test_significance_bracket_expands_to_three_page_attached_lines_and_arrow_support():
    layer = _AnnotationLayer()
    result = apply_annotations(layer, {
        "significance_brackets": [{
            "x1": 0.2, "x2": 0.4, "y": 0.3, "stem_height": 0.02,
            "coordinate_system": "page", "text": "P = 0.01", "text_offset": 0.01,
            "line_width": 0.8,
        }],
        "lines": [{"x1": 0.1, "y1": 0.1, "x2": 0.1, "y2": 0.2, "coordinate_system": "page", "arrow_end": True}],
    })
    assert result.count("annotation.line") == 4
    assert len(layer.lines) == 4
    assert all(line.props["attach"] == 1 for line in layer.lines)
    assert layer.lines[0].coords == (0.1, 0.1, 0.1, 0.2)
    assert layer.lines[0].props["arrowendshape"] == 2
    assert len(layer.labels) == 1
    assert layer.labels[0].text == "P = 0.01"
    assert layer.labels[0].props["attach"] == 1


def test_significance_bracket_can_use_data_coordinates():
    layer = _AnnotationLayer()
    result = apply_annotations(layer, {
        "brackets": [{
            "x1": 1.0, "x2": 2.0, "y": 34.0, "stem_height": 3.0,
            "coordinate_system": "data", "text": "*",
        }],
    })
    assert result.count("annotation.line") == 3
    assert all(line.props["attach"] == 2 for line in layer.lines)
    # Positive data-space stem height points down towards the bars.
    assert layer.lines[0].coords == (1.0, 31.0, 1.0, 34.0)
    assert layer.lines[1].coords == (1.0, 34.0, 2.0, 34.0)
    assert layer.lines[2].coords == (2.0, 34.0, 2.0, 31.0)
