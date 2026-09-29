"""Scientific, marker-driven candidate fits used by reference reconstructions.

The reference image only gives us visible marker locations.  This module keeps
those observations as the source of truth and generates a smooth editable
curve from a named *candidate* model.  It deliberately does not claim that the
model or fitted parameters are the original analysis from the paper.

The public entry point returns JSON-friendly dictionaries so that a fit can be
written directly into a PlotSpec and audited beside the marker columns.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Iterable, Sequence

import numpy as np
from scipy.optimize import curve_fit
from scipy.stats import t as student_t


_EPS = np.finfo(float).eps


@dataclass(frozen=True)
class FitDefinition:
    """A candidate model and its scientific notation."""

    name: str
    formula: str
    parameter_names: tuple[str, ...]
    func: Any
    log_x: bool = False
    min_markers: int = 4
    positive_x: bool = False
    nonlinear: bool = True


def _linear(x: np.ndarray, intercept: float, slope: float) -> np.ndarray:
    """Ordinary straight-line model on the supplied (linear) X scale."""
    return intercept + slope * x


def _boltzmann(x: np.ndarray, bottom: float, top: float,
               midpoint: float, width: float) -> np.ndarray:
    """Decreasing Boltzmann response, with x on its original scale."""
    z = np.clip((x - midpoint) / np.maximum(width, _EPS), -700.0, 700.0)
    return bottom + (top - bottom) / (1.0 + np.exp(z))


def _four_pl(log_x: np.ndarray, bottom: float, top: float,
             log_ic50: float, hill_slope: float) -> np.ndarray:
    """Decreasing four-parameter logistic response on log10(x)."""
    z = np.clip((log_x - log_ic50) * hill_slope, -700.0, 700.0)
    return bottom + (top - bottom) / (1.0 + np.power(10.0, z))


def _definition(model: str) -> FitDefinition:
    key = model.strip().lower().replace("-", "_").replace(" ", "_")
    if key in {"linear", "line", "straight_line", "ols", "linear_regression"}:
        return FitDefinition(
            "linear_regression",
            "y = intercept + slope*x",
            ("intercept", "slope"),
            _linear,
            min_markers=2,
            nonlinear=False,
        )
    if key in {"boltzmann", "ph_sigmoid", "p_h_sigmoid", "sigmoid"}:
        return FitDefinition(
            "boltzmann_decreasing",
            "y = bottom + (top-bottom)/(1 + exp((x-midpoint)/width))",
            ("bottom", "top", "midpoint", "width"),
            _boltzmann,
            positive_x=False,
        )
    if key in {"4pl", "four_pl", "four_parameter_logistic", "dose_response_4pl", "logistic"}:
        return FitDefinition(
            "four_parameter_logistic_decreasing",
            "y = bottom + (top-bottom)/(1 + 10^((log10(x)-log10(IC50))*hill_slope))",
            ("bottom", "top", "log_ic50", "hill_slope"),
            _four_pl,
            log_x=True,
            positive_x=True,
        )
    if key in {"connected", "connect", "polyline", "step", "stairs", "piecewise"}:
        raise ValueError(
            "connected/step lines are display traces, not fitted models; omit fit_request "
            "and keep the supplied line_data or data points"
        )
    raise ValueError(f"Unsupported candidate fit model: {model!r}")


def _finite_markers(
    x: Sequence[float], y: Sequence[float], definition: FitDefinition
) -> tuple[np.ndarray, np.ndarray]:
    if len(x) != len(y):
        raise ValueError("marker x and y arrays must have the same length")
    xa = np.asarray(x, dtype=float)
    ya = np.asarray(y, dtype=float)
    finite = np.isfinite(xa) & np.isfinite(ya)
    xa, ya = xa[finite], ya[finite]
    if xa.size < definition.min_markers:
        raise ValueError(
            f"at least {definition.min_markers} finite marker observations are required "
            f"for {definition.name}"
        )
    order = np.argsort(xa, kind="mergesort")
    xa, ya = xa[order], ya[order]
    if definition.positive_x and np.any(xa <= 0):
        raise ValueError(f"marker x values must be positive for {definition.name}")
    return xa, ya


def _initial_and_bounds(x: np.ndarray, y: np.ndarray, definition: FitDefinition) -> tuple[np.ndarray, tuple[np.ndarray, np.ndarray]]:
    span_y = max(float(np.ptp(y)), 1.0)
    y_lo, y_hi = float(np.min(y)), float(np.max(y))
    x_lo, x_hi = float(np.min(x)), float(np.max(x))
    if definition.log_x:
        z = np.log10(x)
        z_lo, z_hi = float(np.min(z)), float(np.max(z))
        p0 = np.array([y_lo, y_hi, float(np.median(z)), 1.0], dtype=float)
        lower = np.array([y_lo - 2 * span_y, y_hi - span_y, z_lo - 1.0, 0.05], dtype=float)
        upper = np.array([y_lo + span_y, y_hi + 2 * span_y, z_hi + 1.0, 8.0], dtype=float)
    else:
        span_x = max(x_hi - x_lo, 1e-3)
        p0 = np.array([y_lo, y_hi, float(np.median(x)), max(span_x / 8.0, 0.02)], dtype=float)
        lower = np.array([y_lo - 2 * span_y, y_hi - span_y, x_lo - 0.5 * span_x, 1e-4], dtype=float)
        upper = np.array([y_lo + span_y, y_hi + 2 * span_y, x_hi + 0.5 * span_x, 4.0 * span_x], dtype=float)
    # Keep the initial point strictly inside curve_fit bounds.
    p0 = np.minimum(np.maximum(p0, lower + 1e-8), upper - 1e-8)
    return p0, (lower, upper)


def _fit_parameters(
    x: np.ndarray, y: np.ndarray, definition: FitDefinition
) -> tuple[np.ndarray, np.ndarray | None, bool, str]:
    if not definition.nonlinear:
        # Keep linear regression explicit and unconstrained.  In particular,
        # zero/negative X values are valid for a straight-line model.
        design = np.column_stack((np.ones_like(x), x))
        params, _, rank, _ = np.linalg.lstsq(design, y, rcond=None)
        if rank < 2:
            raise ValueError("linear regression requires at least two distinct x values")
        covariance: np.ndarray | None = None
        dof = int(x.size - design.shape[1])
        if dof > 0:
            residual = y - design @ params
            mse = float(np.sum(residual * residual) / dof)
            covariance = mse * np.linalg.pinv(design.T @ design)
        return np.asarray(params, dtype=float), covariance, True, "linear_least_squares_converged"
    p0, bounds = _initial_and_bounds(x, y, definition)
    fit_x = np.log10(x) if definition.log_x else x
    try:
        params, covariance = curve_fit(
            definition.func,
            fit_x,
            y,
            p0=p0,
            bounds=bounds,
            maxfev=100_000,
        )
        return np.asarray(params, dtype=float), np.asarray(covariance, dtype=float), True, "curve_fit_converged"
    except Exception as exc:
        # A deterministic starting curve is preferable to fabricating a pixel
        # trace when sparse markers do not identify all four parameters.
        return p0, None, False, f"curve_fit_fallback:{type(exc).__name__}"


def _json_float(value: float) -> float | None:
    """Convert non-finite numerical diagnostics to JSON-safe nulls."""
    return float(value) if math.isfinite(float(value)) else None


def _confidence_band(
    definition: FitDefinition,
    dense_x: np.ndarray,
    params: np.ndarray,
    covariance: np.ndarray | None,
    degrees_of_freedom: int,
    confidence_level: float,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]] | None:
    """Calculate a delta-method confidence band for the fitted mean curve.

    The band is intentionally a *candidate visual uncertainty* around the
    marker-derived fit, rather than a claim about the source paper's
    statistics.  It is only emitted when the fit returned a finite parameter
    covariance matrix.  This keeps sparse/fallback fits backwards compatible:
    they still have ``line_data`` but do not gain a misleading band.
    """
    if covariance is None or covariance.shape != (len(params), len(params)):
        return None
    if not (0.5 < float(confidence_level) < 1.0):
        raise ValueError("confidence_level must be between 0.5 and 1.0")
    covariance = np.asarray(covariance, dtype=float)
    if not np.all(np.isfinite(covariance)):
        return None
    coordinate = np.log10(dense_x) if definition.log_x else dense_x
    # Numerical derivatives work for both the linear and nonlinear candidate
    # models and avoid duplicating the 4PL/Boltzmann parameter algebra.
    jacobian = np.empty((dense_x.size, len(params)), dtype=float)
    for index, parameter in enumerate(params):
        step = math.sqrt(_EPS) * max(1.0, abs(float(parameter)))
        plus = params.copy()
        minus = params.copy()
        plus[index] += step
        minus[index] -= step
        jacobian[:, index] = (
            np.asarray(definition.func(coordinate, *plus), dtype=float)
            - np.asarray(definition.func(coordinate, *minus), dtype=float)
        ) / (2.0 * step)
    variance = np.einsum("ij,jk,ik->i", jacobian, covariance, jacobian)
    if not np.all(np.isfinite(variance)):
        return None
    standard_error = np.sqrt(np.maximum(variance, 0.0))
    dof = max(int(degrees_of_freedom), 1)
    critical = float(student_t.ppf((1.0 + confidence_level) / 2.0, dof))
    if not math.isfinite(critical):
        critical = 1.959963984540054
    margin = critical * standard_error
    fitted = np.asarray(definition.func(coordinate, *params), dtype=float)
    lower = fitted - margin
    upper = fitted + margin
    if not (np.all(np.isfinite(lower)) and np.all(np.isfinite(upper))):
        return None
    return lower, upper, {
        "available": True,
        "kind": "confidence",
        "level": float(confidence_level),
        "method": "delta_method_parameter_covariance",
        "degrees_of_freedom": int(degrees_of_freedom),
        "critical_value": critical,
    }


def _uncertainty_metadata(
    definition: FitDefinition, covariance: np.ndarray | None, params: np.ndarray
) -> dict[str, Any]:
    if covariance is None or covariance.shape != (len(params), len(params)):
        return {
            "available": False,
            "method": None,
            "parameter_standard_errors": {name: None for name in definition.parameter_names},
            "parameter_covariance": None,
        }
    diagonal = np.diag(covariance)
    standard_errors = np.sqrt(np.maximum(diagonal, 0.0))
    usable = bool(np.all(np.isfinite(standard_errors)) and np.all(np.isfinite(covariance)))
    return {
        "available": usable,
        "method": "ordinary_least_squares_local_covariance" if usable else None,
        "parameter_standard_errors": {
            name: _json_float(error) if usable else None
            for name, error in zip(definition.parameter_names, standard_errors)
        },
        "parameter_covariance": (
            [[_json_float(value) for value in row] for row in covariance]
            if usable else None
        ),
    }


def fit_marker_curve(
    x: Sequence[float],
    y: Sequence[float],
    *,
    model: str,
    x_domain: tuple[float, float] | None = None,
    dense_points: int = 400,
    source_label: str | None = None,
    confidence_level: float = 0.95,
) -> dict[str, Any]:
    """Fit a smooth candidate curve using visible marker observations.

    Returns ``line_data`` and ``fit_metadata`` keys.  ``fit_metadata`` keeps
    the marker relationship and residual diagnostics so downstream users can
    replace marker values and refit rather than editing a pixel-traced line.
    """
    definition = _definition(model)
    xa, ya = _finite_markers(x, y, definition)
    if dense_points < 20:
        raise ValueError("dense_points must be at least 20")
    if isinstance(confidence_level, bool) or not 0.5 < float(confidence_level) < 1.0:
        raise ValueError("confidence_level must be between 0.5 and 1.0")
    params, covariance, converged, status = _fit_parameters(xa, ya, definition)
    if x_domain is None:
        domain = (float(xa[0]), float(xa[-1]))
    else:
        domain = (float(x_domain[0]), float(x_domain[1]))
    if not all(math.isfinite(value) for value in domain) or domain[1] <= domain[0]:
        raise ValueError("x_domain must be a finite increasing interval")
    if definition.positive_x and domain[0] <= 0:
        raise ValueError(f"x_domain must be positive for {definition.name}")
    if definition.log_x:
        dense_x = np.geomspace(domain[0], domain[1], dense_points)
        fit_x = np.log10(dense_x)
        observed_fit_x = np.log10(xa)
    else:
        dense_x = np.linspace(domain[0], domain[1], dense_points)
        fit_x = dense_x
        observed_fit_x = xa
    dense_y = np.asarray(definition.func(fit_x, *params), dtype=float)
    predicted = np.asarray(definition.func(observed_fit_x, *params), dtype=float)
    residuals = ya - predicted
    ss_res = float(np.sum(residuals ** 2))
    ss_tot = float(np.sum((ya - np.mean(ya)) ** 2))
    parameters = {name: float(value) for name, value in zip(definition.parameter_names, params)}
    # Keep the human-facing IC50 in the same units as the worksheet while
    # retaining log_ic50 as the fitted coordinate used by the 4PL model.
    if definition.log_x:
        parameters["ic50"] = float(10.0 ** parameters["log_ic50"])
    metadata: dict[str, Any] = {
        "model": definition.name,
        "formula": definition.formula,
        "parameters": parameters,
        "fit_method": "numpy.linalg.lstsq" if not definition.nonlinear else "scipy.optimize.curve_fit",
        "fit_status": status,
        "fit_converged": bool(converged),
        "candidate_model_only": True,
        "model_is_original_research_model": False,
        "log_x": definition.log_x,
        "x_sampling": "log10/geometric" if definition.log_x else "linear/equispaced",
        "line_domain": [float(domain[0]), float(domain[1])],
        "line_points": int(dense_points),
        "source": "visible marker observations extracted from reference image",
        "source_label": source_label or "reference markers",
        "line_generated_from_markers": True,
        "original_research_model_recovered": False,
        "marker_relationship": {
            "x": [float(value) for value in xa],
            "y": [float(value) for value in ya],
            "predicted_y": [float(value) for value in predicted],
            "residual": [float(value) for value in residuals],
        },
        "diagnostics": {
            "n_markers": int(xa.size),
            "degrees_of_freedom": int(max(xa.size - len(params), 0)),
            "residual_sum_squares": float(ss_res),
            "rmse": float(math.sqrt(ss_res / xa.size)),
            "mae": float(np.mean(np.abs(residuals))),
            "max_abs_residual": float(np.max(np.abs(residuals))),
            "r_squared": float(1.0 - ss_res / ss_tot) if ss_tot > _EPS else None,
        },
        "uncertainty": _uncertainty_metadata(definition, covariance, params),
    }
    line_data: dict[str, list[float]] = {
        "x": [float(value) for value in dense_x],
        "y": [float(value) for value in dense_y],
    }
    band = _confidence_band(
        definition, dense_x, params, covariance,
        int(max(xa.size - len(params), 0)), float(confidence_level),
    )
    if band is None:
        metadata["confidence_band"] = {
            "available": False,
            "kind": "confidence",
            "level": float(confidence_level),
            "method": None,
        }
    else:
        lower, upper, band_metadata = band
        line_data["lower"] = [float(value) for value in lower]
        line_data["upper"] = [float(value) for value in upper]
        metadata["confidence_band"] = band_metadata
    return {"line_data": line_data, "fit_metadata": metadata}


__all__ = ["fit_marker_curve"]
