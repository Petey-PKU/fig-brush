---
name: fig-brush
description: Reconstruct an editable Origin project from a scientific plot screenshot using transparent placeholder values and measured visual geometry.
---

# fig-brush

Use this skill when the user supplies a scientific figure and wants an
editable Origin project that matches the figure's visual structure. The
reference screenshot is the only source for placeholder values. Never request
or claim access to the user's private research data. The screenshot workflow
does not upload files from the local MCP process. Compatibility data tools can
read CSV/XLSX paths explicitly supplied by the user. Version 0.3.1 adds a
scientific reconstruction contract: read what the figure is arguing before
choosing how to draw it.

## Required behavior

1. Inspect the reference image before rendering. Work one reference image at a
   time when fidelity matters.
2. Measure and preserve the visible canvas, plot frame, axes, major/minor
   ticks, label formatting, fonts, title offsets, colours, line widths,
   symbols, marker positions, curve geometry, legend entries, and text layout.
3. Create a reference-only `TemplateSpec` with one `Reference Data` workbook.
   Put related XY series on one worksheet with one shared X column and multiple
   Y columns whenever possible. Keep a second worksheet only for a fit or
   derived trace that cannot sit beside its source markers; do not create one
   book or one sheet per Y series merely because the legend has many entries.
4. Generate values that visibly explain their source location in the image,
   using the default `placeholder_policy.mode=approximate_visual` (about three
   significant digits, the same visible marker count, and a compact derived
   curve). A value such as 6.589 can be represented as approximately 6.59 or
   6.6 when that keeps the mark in the same visual region. Do not spend time
   recovering paper precision. Label all values as visual placeholders; they
   are not original research data and must not be described as recovered
   measurements. Set `placeholder_policy.mode=exact` only when a caller
   explicitly needs full supplied precision.
5. During analysis iterations call `prepare_reference_template` with
   `render_origin=false`; this writes the spec and replacement manifest without
   starting Origin. Render once after the visual contract is settled, preferably
   with a single PNG preview. Render SVG/PDF only for the final artifact.
6. Render the native Origin project, then compare the output to the reference.
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
7. Preserve scientific text as structured text: reproduce subscripts,
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
8. Verify that every worksheet, preview, manifest, and Origin project exists
   and that the project opens. Return links to the project, preview, spec,
   manifest, replacement instructions, and verification report.
9. Keep the user's private values local. The user replaces the generated
   worksheet values after receiving the editable project.

## Tool sequence

1. `inspect_reference`
2. Complete the reference-only `TemplateSpec`.
3. `prepare_reference_template`
4. `compare_reference` and iterate on the same image.
5. Verify the completed project and the data replacement path.

For release evaluation, use the synthetic examples and the ordinary test suite.
Do not require private or unlicensed paper benchmark material for installation.
A prepared file or pixel distance alone is not an acceptance pass.

## Supported inputs

- PNG, JPG, or JPEG scientific plot screenshots.
- Origin 2021 or newer on Windows.

The current 0.3.1 workflow is screenshot-only. Existing data-inspection code is
kept only where it is needed for compatibility with older MCP calls; it is not
part of the reference reconstruction flow.

The spec recognizes column/grouped column, scatter, line and regression,
box/violin, histogram, heatmap/matrix, flat pie/doughnut, and explicit
perspective pie3d/doughnut3d families. Native fidelity is strongest for the
Cartesian, matrix, and pie families; box/violin/histogram remain template-
dependent declarations. The 0.3.1 bridge records native pie view-angle and
rotation controls while retaining editable worksheet values.

Fast preparation is the default during iteration: it rounds visual
placeholders and keeps fit traces compact. Native Origin export remains a
separate validation step. Pie and matrix rendering depends on the local
Origin template, so record a template limitation (for example a 3-D pie
default or colourbar placement) instead of claiming pixel-perfect support for
that family.

