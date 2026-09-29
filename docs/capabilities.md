# Capabilities and limits

fig-brush turns a visual reading of a reference figure into an editable
Origin template. The reference image supplies visible evidence; it does not
contain enough information to recover the author's private measurements or
analysis choices.

## Supported workflow

| Area | Current behavior |
| --- | --- |
| Reference input | PNG and JPEG images supplied to the reference-inspection tool |
| Visual structure | Canvas, plot frame, axes, major/minor ticks, labels, legend, colours, symbols, and line geometry |
| Editable output | `TemplateSpec`, data manifest, replacement workbook, previews, and optional native `.opju` |
| Common graph families | Line, scatter, column/grouped column, histogram, box/violin, heatmap/matrix, pie/doughnut, and regression |
| Candidate fits | Explicit linear, Boltzmann, and 4PL requests; fit traces are derived placeholders |
| Text | Structured rich text for Greek letters, units, superscripts, subscripts, and mixed labels |
| Iteration | Preview comparison reports pixel distances for visual adjustment |

The exact Origin rendering available depends on the installed Origin version,
local templates, and the `originpro` version. Specialized graph options may
need a local Origin template or manual adjustment.

## Interpretation boundary

The generated values are labelled `synthetic_visual_reference` (or the
equivalent placeholder policy in the manifest). They are not original
research data. A line that looks like a fit is not evidence of the paper's
model, and a confidence band is not the paper's reported interval. Replace
placeholder columns and recompute derived traces with the user's data, model,
replicates, and uncertainty method.

The renderer does not silently invent a statistical test, smoothing method,
normalization, censoring rule, or domain identity. Uncertain mark roles remain
explicitly unresolved in the reconstruction contract.

## Known gaps

Screenshot inspection alone does not currently provide reliable automatic
OCR, marker/legend segmentation, fit-model selection, or reconstruction of
arbitrary 3-D, contour, survival, broken-axis, dark-theme, or complex
multi-panel figures. A model or user must provide a sufficiently detailed
`TemplateSpec` for those cases, and the result remains a visual template until
the user verifies it.

## Data boundary

The screenshot-only path does not upload or require a private dataset. The
Codex host/model may process the image and tool results according to its host
policies. Legacy compatibility/data-inspection utilities can read a local CSV
or XLSX only when the user explicitly supplies that path. Keep such files out
of the public repository.
