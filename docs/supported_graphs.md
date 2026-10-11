# Supported graph families

Version 0.3.3 selects the Origin graph family from the visible screenshot and
builds a visual format brush from the detected objects. The user does not need
to provide a dataset: the reusable `.otpu` carries the measured style, while
the optional `.opju` uses synthetic placeholders for visual review.

| Family | Screenshot cues |
| --- | --- |
| column / grouped column | bars, category labels, grouped colours |
| scatter | independent markers or marker-plus-line series |
| line | continuous traces with or without symbols |
| box / violin | distribution outlines and quartile or density marks; specialized native templates may require local adjustment |
| histogram | binned bars and numeric distribution axis; verify the native result in the installed Origin version |
| heatmap / matrix | coloured rectangular cells with row/column scales |
| pie / doughnut | categorical composition slices with editable category/value columns; ordinary pie is forced to the flat native view (`-pgpva 90`) |
| pie3d / doughnut3d | explicit perspective pie family using Origin's native view-angle path; set `style.view_angle`, `start_azimuth`, `horizontal_offset`, and `doughnut_hole` when the screenshot exposes them. Native template thickness is preserved; explicit thickness override is not yet verified across Origin versions. |
| regression | point cloud with a fitted or reference line |

The reference-only `TemplateSpec` records the visible limits, ticks, frame,
labels, legend, colours, symbols, and worksheet mapping. Every generated value
in the optional demo is a labelled visual placeholder; it is intended to make
the Origin project recognizable while the user applies the `.otpu` to their
own workbook.

For measured column spacing, set `style.bar_gap_percent` in the template. The
value is the native Origin gap between adjacent bars (0 to 100); it controls
bar separation independently from border width. In a mixed column and marker
panel, column series share the categorical X grid while marker or line series
keep their own X columns, so nearby points remain editable at their measured
positions. Page-attached labels belong in `panel.labels` with normalized `x1`
and `y1` anchors when the screenshot provides their location.
