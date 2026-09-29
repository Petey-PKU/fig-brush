# Origin error-bar style contract

`origin_bridge.error_bars.apply_error_bar_style(plot, style)` maps only
documented Origin controls:

| Style field | Origin operation | Meaning |
|---|---|---|
| `direction: "both"`, `"plus"`, or `"minus"` | `-erdy` / `-erdx` | `0` both, `1` plus, `2` minus |
| `line_width` | `-erw` | Error-bar line width |
| `cap_width` | `-erwc` | Error-bar cap width |
| `color: "#RRGGBB"` or `[r,g,b]` | `-cr color(r,g,b)` | Error-bar plot line color |
| `symbol_through` | `ErrorBar2D.ThroughSymbol` format property | Draw through the data symbol |

Use separate `y` and `x` dictionaries when the figure declares the positive
or negative direction independently:

```python
apply_error_bar_style(plot, {
    "y": {"color": "#333333", "line_width": 0.8,
          "cap_width": 5, "direction": "both", "symbol_through": False},
    "x": {"direction": "minus"},
})
```

The `-erdx`, `-erdy`, `-erw`, and `-erwc` mappings are from Origin's official
[Options for Error Bars](https://docs.originlab.com/labtalk/ref/options_for_error_bars/)
and [Set command](https://docs.originlab.com/labtalk/ref/set-cmd/) references.
The `ThroughSymbol` spelling is from the installed Origin 2023 Origin C
format tree (`OriginC/OriginLab/okThemeID.h`,
`OTID_CURVE_2DERRORBAR_THROUGH_SYMBOL`) and Origin's documented `ErrorBar2D`
format-tree examples. It has no published `set` switch, so the adapter uses
the originpro numeric property path instead of inventing a LabTalk option.

The `x` and `y` blocks both use the same associated error-bar plot. Origin's
documented controls expose direction independently, while color, line width,
and cap width are style controls on that error-bar plot; if a project requests
different widths or colors for X and Y, the last block applied is the active
style in Origin. The function records both command groups so a caller can
surface that limitation instead of silently treating them as independent
Origin objects.

When adding plots through `originpro.GLayer.add_plot`, the local source maps
`colyerr` to the third worksheet column and `colxerr` to the fourth for a
direct X/Y/YErr/XErr sheet. For panel-wide sheets it uses the generated column
map. If a sparse `marker_data` block omits error columns, the graph builder
merges the original `data` block before creating the marker plot, so the
error-bar columns remain editable in the same workbook.

For data-driven `build_graph` calls, semantic inference records candidate
columns in `statistics.error_columns` (for example
`{"sd": ["SD"]}`) and the selected `statistics.error_type` chooses that
list. One column is shared across all Y series; a list with one entry per Y
series is paired by series order. The bridge passes the resolved columns as
`colyerr`/`colxerr` and then applies `style.error_bars`, so uncertainty columns
are not accidentally rendered as independent measurement curves.
