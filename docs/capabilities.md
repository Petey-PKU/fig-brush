# Capabilities and limits

fig-brush turns a visual reading of a reference figure into an Origin visual
format brush. The primary artifacts are a data-free `format_parameters.json`
bundle, its `reference_analysis.json` evidence file, and a generated
`APPLY_FORMAT.md` checklist. A native `.otpu` graph
template is optional; the reference image supplies visible evidence for
appearance, but it does not contain enough information to recover the author's
private measurements or analysis choices.

## Supported workflow

| Area | Current behavior |
| --- | --- |
| Reference input | PNG and JPEG images supplied to `format_brush` |
| Visual structure | Canvas, plot frame, axes, major/minor ticks, labels, legend, colours, symbols, and line geometry |
| Editable output | `APPLY_FORMAT.md` plus `format_parameters.json` and `reference_analysis.json` by default; `apply-format` can create a new styled `.opju`; `apply_active_format` can paste into the graph currently open in Origin; a native `.opju` reference can seed Origin's built-in Paste Format clipboard; optional native `.otpu`, `style_manifest.json`, and previews |
| Common graph families | Line, scatter, column/grouped column, histogram, box/violin, heatmap/matrix, pie/doughnut, and regression |
| Candidate fits | Explicit linear, Boltzmann, and 4PL requests; fit traces are derived placeholders |
| Text | Structured rich text for Greek letters, units, superscripts, subscripts, and mixed labels |
| Iteration | Preview comparison reports pixel distances for visual adjustment |

The user does not need to provide a private dataset to receive the parameter
bundle. Native Origin is required only to emit the `.otpu` and its optional
`.opju` demo; the demo uses clearly labelled synthetic visual placeholders so
the graph can be inspected before the template is applied to the user's
workbook. Conventional CSV/XLSX replacement tables remain an optional local
mapping path, not a prerequisite for the format-brush workflow.

When the user already has an editable `.opju`, the `apply-format` CLI/MCP
operation reads `format_parameters.json`, writes a new formatted copy, and
preserves the input project's data and labels. The generated checklist remains
the fallback when Origin automation is unavailable.

When the user already has Origin open, `apply_active_format` applies the bundle
to the active graph and leaves saving to Origin. `stage_format_clipboard` opens
a native reference `.opju`/`.opj`, runs Origin's own `FmtsCopy*` section, and
leaves the session open so the user can switch graphs and choose the native
right-click Paste Format command.

The exact Origin rendering available depends on the installed Origin version,
local templates, and the `originpro` version. Specialized graph options may
need a local Origin template or manual adjustment.

The `apply-format` command opens a copy of an existing `.opju`, applies the
measured page, layer, axis, and typography settings, and writes a new
`*_formatted.opju`. It preserves the source project, data, labels, axis ranges,
and series colours. The exported `.otpu` remains useful when a reusable Origin
template is preferred, but it is built from a compatible placeholder graph
structure and is not a universal formatting paste for every existing graph.

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

The screenshot-only format-brush path does not upload or require a private
dataset. The Codex host/model may process the image and tool results according
to its host policies. Legacy compatibility/data-inspection utilities and the
optional replacement bundle can read a local CSV or XLSX only when the user
explicitly supplies that path. Keep such files out of the public repository.
