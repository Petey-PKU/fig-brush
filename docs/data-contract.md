# Optional replacement data contract

The visual format-brush workflow does not require a data file. Its default
outputs are `format_parameters.json`, `reference_analysis.json`, and the
human-facing `APPLY_FORMAT.md` checklist; a native `style_template.otpu` is
optional. This document describes an advanced
convenience path for researchers who explicitly want fig-brush to map local
values into the synthetic demo project.

The screenshot does not contain the original experiment table. When this
optional path is selected, fig-brush creates two kinds of values:

- `Raw_Data.csv`, `Summary_Data.csv`, or `XY_Data.csv` are user-facing input
  tables with conventional scientific columns.
- Origin's `Reference Data` worksheet is derived plot data. It contains the
  numeric category positions, marker jitter, sparse bar rows, and other
  helper columns required by the graph binding.

The generated input rows are synthetic visual placeholders. They preserve the
number and approximate position of visible marks so the demo project can be
rendered without private data. They do not establish that a bar is a mean,
that an error bar is SD/SEM/CI, or that a displayed P value came from a
particular test.

For a categorical summary with raw points, replace:

| File | Columns | Meaning |
| --- | --- | --- |
| `Raw_Data.csv` | `Group`, `Replicate`, `Value` | one row per raw observation |
| `Summary_Data.csv` | `Group`, `Center`, `ErrorPlus`, `ErrorMinus`, `ErrorType` | explicit summary values and uncertainty supplied by the researcher |

For ordinary XY figures, replace `XY_Data.csv` with `Series`, `X`, `Y`,
`YError`, and `XError`. Keep `ErrorType` as `unknown` when the source data do
not define the statistic. Reference annotations such as P values remain
separate text until the researcher supplies a replacement result.

The `refresh_reference_template` tool reads these local files, maps them into
the existing visual roles, and rebuilds the optional Origin demo project with
the measured style. It copies explicit summary and uncertainty values but
never chooses a statistical method from placeholder data. For most users,
applying the JSON parameters to their existing workbook is the shorter path.

The current Cartesian renderer applies the symmetric `ErrorPlus` value to the
reference-style error bar. `ErrorMinus` is retained in the input contract for
future asymmetric-error support; it is not silently treated as a statistic.
P-value text is also left as an explicit annotation until the researcher
supplies a replacement result.

This separation follows Origin's template model: a graph template stores page,
layer, and plot style, while a cloneable template additionally stores the
relationship between graph plots and a matching worksheet structure. An
analysis template is appropriate only when the researcher has explicitly
chosen the analysis and recalculation rules.
