# Scientific reconstruction contract (0.3.2)

The screenshot is evidence of a figure's visible argument, not a source of
the author's private measurements. Pixels may be sampled to estimate geometry,
visible labels, and synthetic placeholder coordinates. The reconstruction
layer must label those estimates as placeholders and separate what can be
observed from what must be inferred; it must never call them the original
measurements.

## Read the figure before selecting a plot

Record the likely question, the experimental unit if it is visible, axis
units and transforms, and the role of every visual mark. A point can be a raw
replicate, a summary, a censoring mark, or a fitted-model anchor. A line can
be a fit, a guide, a step function, a baseline, or a connection of observed
points. An error bar can be SD, SEM, CI, range, or an unresolved uncertainty.
These are separate fields in `scientific_context.reference`; unknown fields
remain unresolved instead of being filled by visual guesswork.

The `placeholder_policy` explicitly marks generated coordinates as
`synthetic_visual_reference`: pixel estimates are allowed for reconstruction,
but the values are not original research data and require user replacement.
For interactive iteration the default `mode: "approximate_visual"` keeps
three significant digits and generates a fit trace with 120 points. It keeps
the axis limits and visible marker count unchanged, which is enough to show
the visual style while avoiding a long precision-first data pass. Set
`{"placeholder_policy": {"mode": "exact"}}` when a caller needs the
previous full-precision placeholders and the 400-point fit default. An
explicit `fit_request` `dense_points` value always wins, so a model can choose
its own sampling density when the trace itself is important.

## Markers and fitted curves

If a reference contains markers and a smooth curve, store the marker
coordinates as the editable visual placeholder data. Store the curve as a
derived role with an explicit candidate model and evidence, for example:

```json
{
  "source_role": "marker_observations",
  "derived_role": "candidate_fit",
  "candidate_fit_models": ["logistic_4pl", "logistic_5pl"],
  "fit_parameters": {},
  "fit_is_reproducible_from_markers": true,
  "fit_should_be_regenerated_after_replacement": true
}
```

The candidate is a transparent reconstruction hypothesis. It must not be
described as the original paper's algorithm unless the caption or user
supplies that evidence. Once the user replaces the marker values, the derived
curve should be refit; a stale placeholder curve would misrepresent the new
data.

In a reusable `TemplateSpec`, request this derivation explicitly on the
series. `prepare_template` does not infer a fit merely because a series has
markers or a line:

```json
{
  "id": "DoseResponse",
  "kind": "line_symbol",
  "data": {"x": [0.03, 0.1, 1, 10, 100], "y": [98, 94, 72, 28, 4]},
  "marker_data": {"x": [0.03, 0.1, 1, 10, 100], "y": [98, 94, 72, 28, 4]},
  "fit_request": {
    "model": "4pl",
    "points": "marker_data",
    "options": {"x_range": [0.03, 100]}
  }
}
```

Supported candidate names include `linear` (ordinary least-squares straight
line on a linear X axis), `boltzmann` (linear-X pH-like response), and `4pl`
(log10-X dose response). Linear regression accepts zero and negative X values;
the 4PL model requires positive X values because it is defined on log10(X).
The generated series receives editable `line_data` and `fit_metadata`; the
latter records the formula, fitted parameters, marker residual diagnostics,
parameter covariance/standard errors when identifiable, and the fact that no
original research model was recovered. A fit with insufficient information
reports unavailable uncertainty rather than inventing error bars. After
replacement, rerun the same request or refit the derived columns in Origin.

Connected-point, step, staircase, guide, and baseline traces must remain
explicit `data`/`line_data`; they are not silently converted to statistical
fits. A series with `marker_data` but no `fit_request` remains unchanged.

## Editable data layout

Use one `Reference Data` workbook for an image. For ordinary XY figures,
prefer one worksheet with a shared `X` column followed by `Y` columns for all
series. Keep fit, uncertainty, or other derived columns adjacent to their
source columns where Origin permits it. Use a second worksheet only when a
different Origin plot type or a matrix page requires it. This layout lets a
researcher see which Y column maps to each legend entry and replace values
without hunting through a book per series.

## Text and geometry

Carry labels as structured text runs so `IC₅₀`, `CD8⁺`, units, Greek letters,
and mixed superscript/subscript notation survive into legends and annotations.
Measure major and minor tick strokes near the axes, retain the scale type and
tick-label format, and store page/frame proportions independently from the
Origin window zoom. A project that opens at a different UI zoom should retain
the same page and plot-frame geometry.

`compare_reference` remains a pixel-level iteration aid. It cannot prove that
the original data or the paper's scientific method has been recovered.


