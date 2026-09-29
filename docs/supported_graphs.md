# Supported graph families

Version 0.3.1 selects the Origin graph family from the visible screenshot and
builds the editable worksheet mapping from the detected objects. The user
does not need to provide a dataset.

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
is a labelled visual placeholder; it is intended to make the Origin project
recognizable until the user pastes private values into the matching worksheet.
