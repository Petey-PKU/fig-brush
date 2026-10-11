# Visual format-brush workflow

fig-brush removes the styling work that normally stands between a reference
image and a publication-ready Origin graph. The default result is a small,
data-free parameter pack that a researcher can apply to their existing Origin
graph. Native graph templates remain available when a completed visual
specification and Origin installation are available.

## Fast path

Only the reference PNG or JPEG is required. Run:

```powershell
python scripts\origin_plot_cli.py format-brush reference.png output
```

The same operation is exposed as the `format_brush` MCP tool. It writes two
JSON files and one short, human-facing apply sheet:

- `format_parameters.json`: the compact Origin-oriented format contract;
- `reference_analysis.json`: the image measurements and detection evidence.
- `APPLY_FORMAT.md`: the only file a user needs to read. It turns the JSON
  values into a three-step Origin checklist and a small table of values.

The parameter file remains the machine-readable source for the same values.
Its `origin_mapping` field maps the sections to Origin's page, layer, axis,
plot, legend, and annotation controls. The `review` field calls out
items that still need visual confirmation, such as graph family, panel roles,
OCR text, or low-confidence geometry. It never includes a worksheet or claims
to recover research values. Pixel measurements also include an explicit
`*_pt_96dpi` approximation for Origin's point-like length controls; preserve
the aspect ratio and visually verify the result after applying it.

## What to give the plugin

A private CSV, XLSX, or OPJU is not required. Pixels that cannot establish a
scientific value remain unresolved visual decisions.

## What the output folder contains

The default `format_brush` call writes:

- `format_parameters.json`: the compact Origin-oriented format contract;
- `reference_analysis.json`: the source measurements and confidence evidence.
- `APPLY_FORMAT.md`: a generated one-page instruction sheet. Use this as the
  starting point instead of opening the JSON files. It identifies the Origin
  menu for each setting and records the detected page ratio, margins, fonts,
  axes, and colours.

When a completed reference-only `TemplateSpec` is supplied and native
rendering is requested, the prepared folder additionally contains:

- `style_template.otpu`: an optional native format-brush artifact. Import or apply it
  to a graph built from compatible columns in the user's own Origin worksheet.
- For a multi-panel reference, one `<Panel>_style.otpu` is emitted per Origin
  graph page; the `style_templates` result field lists those files.
- `style_manifest.json`: a human-readable record of the measured canvas, frame,
  axis, text, mark, colour, spacing, and annotation choices.
- `result.opju`: a companion demo project containing synthetic visual
  placeholders. Use it to inspect the style and its editable graph structure;
  do not treat its values as experiment data. The current native render writes
  this companion alongside the template.
- `preview.png` (and optionally `preview.svg`/`preview.pdf`): quick visual
  checks against the supplied reference.

The `.otpu` is the reusable native asset. The `.opju` is an optional visual
demo. Origin is required to create native artifacts; parameter extraction does
not need it. Set `render_origin=true` only for the final export.

## No-script Origin path

For users who do not want to run a command, the current Codex bridge can apply a bundle to the graph already active in Origin. Ask Codex to “paste this `format_parameters.json` into the current Origin graph”; it applies visual settings with Origin undo support and leaves saving to the user. The planned desktop route is an optional Origin `.opx` add-in installed once. After that, right-click the layer background or a curve and choose **Fig-brush → Paste Reference Format**. See [the one-click Origin design](origin-one-click.md) for the package and version details.

If native rendering produced a reference `result.opju`, ask Codex to stage its
Origin format clipboard. Switch back to your own project and use Origin's
existing right-click **Paste Format** command. The reference project contains
only synthetic placeholders, and the clipboard is session-local; keep Origin
open until the paste is complete.

When a native reference graph is available as `.opju`/`.opj`, the bridge can also
stage Origin's own format clipboard. Ask Codex to prepare that reference graph,
then switch to your graph and use Origin's existing right-click **Paste Format**.
This keeps the familiar Origin action and avoids asking the user to open either
JSON file. The clipboard lives in the current Origin session, so Origin must
remain open until the paste is complete.
## Applying the style in Origin

1. Open `APPLY_FORMAT.md` from the output folder. `format_parameters.json` is
   the machine-readable source for the same values; `reference_analysis.json`
   is optional audit evidence and is not imported into Origin.
2. Open the user's workbook in Origin, create a graph from the user's own
   columns using the closest graph family (for example, column, scatter, line,
   or mixed column-and-marker), and save it as an `.opju` copy.
3. Run the one-command bridge from the plugin root:

   ```powershell
   python scripts\origin_plot_cli.py apply-format <your-project.opju> <format-output>\format_parameters.json
   ```

   It writes `<your-project>_formatted.opju` and keeps the input project
   unchanged. Open the new project and check data binding, plot roles, axis
   limits, and categorical order.
4. If the one-command bridge is unavailable, follow the table in
   `APPLY_FORMAT.md` and set `Format > Page`, `Format > Layer`, `Format > Axes`,
   and `Plot Details` in that order.
5. If the output includes `style_template.otpu`, you can apply it through
   Origin's graph-template or template library workflow instead of entering the
   table manually.
6. Check data binding, plot roles, axis limits, and categorical order. A mixed
   summary-plus-raw-point panel needs explicit mapping of the user's summary
   and raw-point columns to the corresponding template roles.
7. Keep the user's values, labels, axis ranges, statistics, fits, and
   uncertainty calculations in their workbook. Adjust only scientific content
   that the image cannot establish, such as a test-specific P value or the
   definition of an error bar.

Origin documents the native model in its [graph-template basics](https://docs.originlab.com/origin-help/graph-template-basics/)
and [graph-template elements](https://docs.originlab.com/origin-help/graph-template-elements/)
guides. Standard templates preserve appearance and layout; a template that
depends on a particular worksheet relationship may need matching columns or a
small local adjustment after it is applied. The `apply-format` command is the
shortest path for an existing `.opju`: it writes a new formatted copy and keeps
the input project's data, labels, ranges, and statistics unchanged.

## Why the demo values are still present

The demo project is generated from synthetic values because Origin needs plot
objects in order to render a visual check. Those values preserve marker counts,
bar positions, and visible ranges only. They do not recover the paper's raw
measurements, analysis, normalization, model, or statistical result.

## Optional data mapping

Users who explicitly want fig-brush to map local data into the demo project can
use the replacement bundle described in [`data-contract.md`](data-contract.md)
and call `refresh_reference_template`. This is an advanced convenience path;
the normal format-brush workflow ends after `APPLY_FORMAT.md` and the two JSON
files are created.

