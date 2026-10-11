---
name: fig-brush
description: Extract reusable Origin format parameters from a scientific plot screenshot, with an optional native graph template.
---

# fig-brush

Use this skill when the user supplies a scientific figure and wants its visual
appearance applied like a format brush. The primary deliverable is a compact,
data-free `format_parameters.json`, its auditable `reference_analysis.json`,
and a generated `APPLY_FORMAT.md` checklist. A native Origin graph template
(`.otpu`) and a placeholder `.opju` are optional exports. Never request or claim access to the
user's private research data. Compatibility data tools can read CSV/XLSX paths
explicitly supplied by the user, but they are not part of the default workflow.

## Required behavior

1. Run the `format_brush` workflow on one reference image. It writes the two
   core JSON artifacts and `APPLY_FORMAT.md` without starting Origin or
   requiring a dataset. Open the checklist first; it is the human entry point.
   If the user already has an `.opju`, run `apply-format` with
   `format_parameters.json` to create a formatted copy.
   When the user has Origin open, prefer `apply_active_format` so Codex can
   paste the bundle into the active graph without asking the user to run a
   script. When a native reference `.opju` is available, `stage_format_clipboard`
   can prepare Origin's own clipboard for the user's familiar right-click
   **Paste Format** action.
2. Measure and preserve the visible canvas, plot frame, axes, major/minor
   ticks, label formatting, fonts, title offsets, colours, line widths,
   symbols, marker positions, curve geometry, legend entries, and text layout.
3. If a native template is requested, create a reference-only `TemplateSpec` and keep any generated values as
   internal visual placeholders. They are only needed to make an optional
   preview project; the `.otpu` style template does not contain them.
4. Create a standard Origin graph template (`.otpu`) only when the caller
   explicitly requests native export. Keep a placeholder `.opju` only as a
   visual demonstration.
5. If a preview project is requested, use one `Reference Data` workbook.
   Put related XY series on one worksheet with one shared X column and multiple
   Y columns whenever possible. Keep a second worksheet only for a fit or
   derived trace that cannot sit beside its source markers; do not create one
   book or one sheet per Y series merely because the legend has many entries.
6. Generate values that visibly explain their source location in the image,
   using the default `placeholder_policy.mode=approximate_visual` (about three
   significant digits, the same visible marker count, and a compact derived
   curve). A value such as 6.589 can be represented as approximately 6.59 or
   6.6 when that keeps the mark in the same visual region. Do not spend time
   recovering paper precision. Label all values as visual placeholders; they
   are not original research data and must not be described as recovered
   measurements. Set `placeholder_policy.mode=exact` only when a caller
   explicitly needs full supplied precision.
7. During analysis iterations call `prepare_reference_template` with
   `render_origin=false`; this writes the spec and replacement manifest without
   starting Origin. Render once after the visual contract is settled, preferably
   with a single PNG preview. Render SVG/PDF only for the final artifact.
8. Render the native Origin project when available, then compare the output to the reference.
   Iterate on measured geometry until the overlay is aligned. `compare_reference`
   is a pixel diagnostic; it does not establish scientific or semantic identity.
   Read the figure like a researcher before styling it: identify the research
   question, axis units and transforms, raw replicates, summaries, fitted
   curves, guide/step lines, censoring marks, error bars, controls, and
   significance annotations. If markers and a smooth line coexist, generate
   the line from the marker data using an explicit interpretable candidate fit
   (currently implemented: linear least-squares, Boltzmann, or 4PL), keep the
   candidate and its evidence in the spec, and mark it for refitting after
   replacement. Other candidates such as 5PL, exponential, Gaussian, and
   polynomial remain hypotheses until their fitter is explicitly implemented;
   do not send them as a runnable `fit_request`. Do not claim the original
   paper used the selected model. Do not invent an independent line dataset,
   smooth, normalize, aggregate, or assign statistical meaning without
   evidence from the reference or user.
   For an explicit fitted curve with identifiable marker covariance, the
   candidate fitter may also emit editable `FitLower`/`FitUpper` columns and
   fill the area between them. These are delta-method confidence-band
   placeholders (default 95%), not recovered paper statistics; if covariance
   is unavailable, keep the fit line and omit the band. After replacing X/Y,
   recompute the band with the user's own model and uncertainty method.
9. Preserve scientific text as structured text: reproduce subscripts,
   superscripts, Greek symbols, units, and mixed math runs in axis titles,
   legends, and annotations. Keep major/minor tick counts, scale transforms,
   tick-label formatting, and frame geometry independent from the screenshot
   window zoom; opening a project at a different UI zoom must not change the
   page or plot-frame proportions.
   For legends outside the data frame or on a log axis, use
   `legend.coordinate_space="page"` with measured page-fraction `x`, `y`,
   `row_step`, `sample_width`, and `text_offset`; data-space anchors can clip
   when the axis transform changes. Remove empty plots carried by Origin
   templates before adding replacement series, and group columns only when
   each series shares the category grid so single-category bars keep their
   width.
10. Verify the `.otpu` and, when requested, the placeholder `.opju` and preview.
   Return links to the style template first, then the preview project, preview,
   spec, manifest, and verification report.
11. Keep the user's private values local. Applying the style template happens
   in the user's own Origin workbook; no private dataset is needed by the
   screenshot-to-style workflow.

## Tool sequence

1. `format_brush` (default path)
2. If an Origin graph is already open, apply the bundle with
   `apply_active_format`; otherwise, if an existing Origin project is available,
   apply the bundle with `apply_format` / `scripts\origin_plot_cli.py apply-format`.
3. If a native reference project is available and the user wants Origin's
   built-in right-click action, call `stage_format_clipboard` and tell them to
   switch to the target graph and choose **Paste Format**.
4. If native export is requested, complete the reference-only `TemplateSpec`
   and call `prepare_reference_template` with `render_origin=true`.
5. Optionally call `compare_reference` and `verify_reference_template` for that
   native artifact.

For release evaluation, use the synthetic examples and the ordinary test suite.
Do not require private or unlicensed paper benchmark material for installation.
A prepared file or pixel distance alone is not an acceptance pass.

## Supported inputs

- PNG, JPG, or JPEG scientific plot screenshots.
- Origin 2021 or newer on Windows.

The current 0.3.3 workflow is screenshot-only. Existing data-inspection code is
kept only where it is needed for compatibility with older MCP calls; it is not
part of the reference reconstruction flow.

The spec recognizes column/grouped column, scatter, line and regression,
box/violin, histogram, heatmap/matrix, flat pie/doughnut, and explicit
perspective pie3d/doughnut3d families. Native fidelity is strongest for the
Cartesian, matrix, and pie families; box/violin/histogram remain template-
dependent declarations. The 0.3.3 bridge records native pie view-angle and
rotation controls while retaining editable worksheet values.

Fast preparation is the default during iteration: it rounds visual
placeholders and keeps fit traces compact. Native Origin export remains a
separate validation step. Pie and matrix rendering depends on the local
Origin template, so record a template limitation (for example a 3-D pie
default or colourbar placement) instead of claiming pixel-perfect support for
that family.
