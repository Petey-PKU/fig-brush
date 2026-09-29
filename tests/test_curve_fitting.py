import numpy as np
import pytest

from mcp_server.curve_fitting import fit_marker_curve


def test_boltzmann_curve_is_marker_driven_and_records_diagnostics():
    x = np.linspace(4.5, 7.5, 9)
    y = 3.0 + (235.0 - 3.0) / (1.0 + np.exp((x - 5.9) / 0.16))
    result = fit_marker_curve(x, y, model="boltzmann", x_domain=(4.4, 7.9), dense_points=120)

    line = result["line_data"]
    metadata = result["fit_metadata"]
    assert len(line["x"]) == 120
    assert line["x"][0] == pytest.approx(4.4)
    assert line["x"][-1] == pytest.approx(7.9)
    assert all(a >= b for a, b in zip(line["y"], line["y"][1:]))
    assert metadata["line_generated_from_markers"] is True
    assert metadata["original_research_model_recovered"] is False
    assert metadata["diagnostics"]["n_markers"] == 9
    assert metadata["diagnostics"]["rmse"] < 1e-4
    assert len(metadata["marker_relationship"]["residual"]) == 9


def test_four_pl_uses_logarithmic_x_and_preserves_source_marker_order():
    x = np.geomspace(0.03, 150.0, 10)
    log_x = np.log10(x)
    y = 1.0 + (100.0 - 1.0) / (1.0 + 10 ** ((log_x - 0.25) * 1.2))
    # Deliberately scramble input order: a worksheet fit still returns sorted
    # line data while retaining the sorted marker relationship in metadata.
    order = [4, 0, 7, 2, 9, 1, 6, 3, 8, 5]
    result = fit_marker_curve(x[order], y[order], model="4pl", x_domain=(0.024, 150), dense_points=80)

    line = result["line_data"]
    metadata = result["fit_metadata"]
    assert metadata["model"] == "four_parameter_logistic_decreasing"
    assert metadata["log_x"] is True
    assert line["x"][0] == pytest.approx(0.024)
    assert line["x"][-1] == pytest.approx(150.0)
    assert all(a < b for a, b in zip(line["x"], line["x"][1:]))
    source_x = metadata["marker_relationship"]["x"]
    assert source_x == sorted(source_x)
    assert metadata["diagnostics"]["rmse"] < 1e-3
    assert metadata["x_sampling"] == "log10/geometric"
    assert metadata["uncertainty"]["available"] is True
    assert set(metadata["uncertainty"]["parameter_standard_errors"]) == {
        "bottom", "top", "log_ic50", "hill_slope"
    }


def test_linear_fit_allows_zero_and_negative_x_and_uses_equispaced_domain():
    x = np.array([-3.0, -1.0, 0.0, 2.0, 4.0])
    y = 2.5 + 1.75 * x
    result = fit_marker_curve(x, y, model="linear", x_domain=(-4.0, 5.0), dense_points=50)

    line = result["line_data"]
    metadata = result["fit_metadata"]
    assert line["x"][0] == pytest.approx(-4.0)
    assert line["x"][-1] == pytest.approx(5.0)
    assert all(a < b for a, b in zip(line["x"], line["x"][1:]))
    assert metadata["model"] == "linear_regression"
    assert metadata["fit_method"] == "numpy.linalg.lstsq"
    assert metadata["x_sampling"] == "linear/equispaced"
    assert metadata["parameters"]["intercept"] == pytest.approx(2.5)
    assert metadata["parameters"]["slope"] == pytest.approx(1.75)
    assert metadata["diagnostics"]["rmse"] < 1e-10
    assert metadata["uncertainty"]["available"] is True


@pytest.mark.parametrize("model", ["linear", "4pl"])
def test_marker_fit_emits_editable_confidence_band_for_identifiable_fit(model):
    if model == "linear":
        x = np.linspace(0.0, 5.0, 8)
        y = 2.0 + 3.0 * x + np.array([-0.3, 0.2, 0.1, -0.1, 0.15, -0.2, 0.1, -0.05])
    else:
        x = np.geomspace(0.1, 100.0, 10)
        y = 1.0 + (100.0 - 1.0) / (1.0 + 10 ** ((np.log10(x) - 0.4) * 1.2))
        y = y + np.linspace(-0.5, 0.5, len(x))
    result = fit_marker_curve(x, y, model=model, dense_points=32)
    line = result["line_data"]
    assert len(line["lower"]) == len(line["x"]) == len(line["upper"])
    assert all(lo <= mid <= hi for lo, mid, hi in zip(line["lower"], line["y"], line["upper"]))
    assert result["fit_metadata"]["confidence_band"]["available"] is True


def test_boltzmann_accepts_negative_linear_x_but_four_pl_requires_positive_x():
    x = np.linspace(-2.0, 2.0, 7)
    y = 1.0 + (10.0 - 1.0) / (1.0 + np.exp((x - 0.25) / 0.5))
    result = fit_marker_curve(x, y, model="boltzmann", x_domain=(-3.0, 3.0), dense_points=40)
    assert result["line_data"]["x"][0] == pytest.approx(-3.0)

    with pytest.raises(ValueError, match="positive"):
        fit_marker_curve([-1, 1, 2, 3], [1, 2, 3, 4], model="4pl")


def test_fit_rejects_insufficient_or_nonidentifiable_markers_and_display_only_lines():
    with pytest.raises(ValueError, match="at least 4 finite"):
        fit_marker_curve([1, 2, 3], [1, 2, 3], model="boltzmann")
    with pytest.raises(ValueError, match="at least 2 finite"):
        fit_marker_curve([1], [1], model="linear")
    with pytest.raises(ValueError, match="two distinct"):
        fit_marker_curve([1, 1], [1, 2], model="linear")
    with pytest.raises(ValueError, match="display traces"):
        fit_marker_curve([1, 2, 3, 4], [4, 3, 2, 1], model="step")
