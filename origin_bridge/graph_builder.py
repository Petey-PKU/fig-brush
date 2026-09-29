from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
from mcp_server.annotations import resolve_annotations
from mcp_server.layout import resolve_layout

from .plot_styling import apply_plot_border
from .error_bars import apply_error_bar_style
from .styles import apply_annotations, apply_layer_style, apply_page_style, apply_plot_style
from .text_layout import AxisGeometry, FrameGeometry, TextLayout, layout_text_label, normalize_origin_markup, text_value
from .workbook import add_dataframe


PIE_FAMILIES = {"pie", "doughnut", "pie3d", "doughnut3d"}


def _legend_text(series: dict[str, Any]) -> str:
    """Return Origin markup for a legend label, preserving math text.

    ``legend_display`` remains a human-readable fallback for older specs, but
    new screenshot readers can supply ``legend_markup`` (for example
    ``ANPS\\-(5.3)``) so Origin renders subscripts/superscripts instead of
    flattening them into ordinary baseline text.
    """
    return normalize_origin_markup(
        series.get("legend_markup")
        or series.get("legend_display")
        or series.get("legend_name")
        or series.get("name", series.get("id", "Series"))
    )


def _add_template_sheet(op: Any, series: dict[str, Any], data_override: dict[str, Any] | None = None,
                        worksheet_name: str | None = None, book: Any | None = None) -> Any:
    """Create a named, self-describing worksheet for one reference series."""
    import pandas as pd
    data = dict(series.get("data", {}) or {})
    data.update(data_override or {})
    frame = pd.DataFrame({key: list(data[key]) for key in (
        "x", "y", "y_error", "x_error", "color_rgb", "lower", "upper"
    ) if key in data})
    # ``worksheet`` is optional in a model-authored TemplateSpec.  Older
    # benchmark specs happened to provide it, while a single-series reference
    # should remain renderable with only the required ``id`` field.  Keep the
    # user-facing sheet name deterministic without making the schema carry a
    # redundant field.
    sheet_name = worksheet_name or series.get("worksheet") or f"{series.get('id', 'Series')}_Data"
    sheet = add_dataframe(op, frame, str(sheet_name), book=book)
    labels = ["X (replace locally)", "Y (replace locally)"]
    if "y_error" in data:
        labels.append("Y error (reference-visible magnitude)")
    if "x_error" in data:
        labels.append("X error (reference-visible magnitude)")
    if "color_rgb" in data:
        labels.append("Wedge color (Origin RGB integer)")
    if "lower" in data:
        labels.append("Fit lower bound (candidate confidence band)")
    if "upper" in data:
        labels.append("Fit upper bound (candidate confidence band)")
    try:
        sheet.set_labels(labels)
        sheet.set_label(0, "X", "S")
        # Origin's default legend uses the short-name label row. Keep the
        # visible series name here while the long-name/comment rows explain
        # that the values are placeholders.
        sheet.set_label(1, str(series.get("name", series["id"])), "S")
    except Exception:
        pass
    return sheet


def _wide_columns(series: dict[str, Any]) -> dict[str, str]:
    """Return deterministic headers for a panel-wide replacement worksheet."""
    prefix = str(series["id"])
    columns = {
        "x": f"{prefix}_X",
        "y": f"{prefix}_Y",
    }
    source = dict(series.get("data", {}) or {})
    source.update(series.get("marker_data", {}) or {})
    for key, suffix in (("y_error", "YErr"), ("x_error", "XErr"), ("color_rgb", "ColorRGB")):
        if key in source:
            columns[key] = f"{prefix}_{suffix}"
    if series.get("line_data"):
        columns["fit_x"] = f"{prefix}_FitX"
        columns["fit_y"] = f"{prefix}_FitY"
        if "lower" in series["line_data"]:
            columns["fit_lower"] = f"{prefix}_FitLower"
        if "upper" in series["line_data"]:
            columns["fit_upper"] = f"{prefix}_FitUpper"
    return columns


def _column_letter(index: int) -> str:
    """Convert a zero-based Origin column index to an A1 column name."""
    value = int(index) + 1
    result = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _template_data_column_index(source: dict[str, Any], key: str) -> int:
    """Return the zero-based column index used by ``_add_template_sheet``."""
    order = ("x", "y", "y_error", "x_error", "color_rgb", "lower", "upper")
    present = [name for name in order if name in source]
    try:
        return present.index(key)
    except ValueError:
        return -1


def _add_confidence_band(
    layer: Any,
    worksheet: Any,
    x_column: int,
    lower_column: int,
    upper_column: int,
    plot_style: dict[str, Any],
) -> list[Any]:
    """Add editable lower/upper traces and fill the area between them.

    Origin's line-plot ``Fill to next data plot`` mode keeps the band linked to
    worksheet columns, so users can replace marker/fit values without losing
    the visual uncertainty object.  This helper is deliberately isolated from
    the marker and fit line code; old specs without ``lower``/``upper`` take
    the unchanged path.
    """
    lower_plot = layer.add_plot(worksheet, coly=lower_column, colx=x_column, type="l")
    upper_plot = layer.add_plot(worksheet, coly=upper_column, colx=x_column, type="l")
    band_style = plot_style.get(
        "confidence_band",
        plot_style.get("fit_band", plot_style.get("band", {})),
    ) or {}
    if not isinstance(band_style, dict):
        band_style = {}
    line_color = band_style.get("edge_color", plot_style.get("color", "#808080"))
    fill_color = band_style.get("fill_color", band_style.get("color", line_color))
    edge_width = band_style.get("edge_width", 0.0)
    transparency = band_style.get("transparency", 72)
    line_type = band_style.get("line_type", band_style.get("linetype"))
    for plot in (lower_plot, upper_plot):
        try:
            plot.color = line_color
            plot.symbol_kind = 0
            plot.set_float("line.width", float(edge_width))
            if line_type is not None:
                plot.set_int("linetype", int(line_type))
            plot.transparency = int(transparency)
        except Exception:
            pass
    try:
        from originpro.utils import ocolor
        if band_style.get("visible", True) is not False:
            fill_value = ocolor(fill_color)
            fill_type = int(band_style.get("fill_type", 9))
            lower_plot.set_fill_area(above=fill_value, type=fill_type)
    except Exception:
        # Rendering the two editable boundary lines is still useful on Origin
        # versions whose template does not expose fill-to-next support.
        pass
    return [lower_plot, upper_plot]


def _apply_pie_geometry(plot: Any, family: str, style: dict[str, Any]) -> list[str]:
    """Apply Origin's native pie view parameters without rasterising wedges.

    Origin stores pie perspective in the plot's ``-pgpva`` command tree. A
    plain ``pie``/``doughnut`` therefore defaults to the flat Pie2D template,
    while callers can request a perspective view with ``pie3d`` or an
    explicit ``pie_geometry: 3d`` style. Unknown options are ignored by older
    Origin versions; the editable categorical plot remains usable.
    """
    applied: list[str] = []
    style = style or {}
    geometry = str(style.get("pie_geometry", "")).strip().lower().replace("-", "_")
    view_angle = style.get("view_angle", style.get("pie_view_angle"))
    if view_angle is None:
        view_angle = 45.0 if family in {"pie3d", "doughnut3d"} or geometry in {"3d", "perspective"} else 90.0
    try:
        angle = max(0.0, min(90.0, float(view_angle)))
        # Origin's documented LabTalk form is ``set rr -pgpva 90`` where the
        # argument is the view angle in degrees (90 is the flat view).  The
        # named ``viewAngle:=`` spelling is not accepted by Pie2D/Pie plots.
        plot.set_cmd(f"-pgpva {angle:g}")
        applied.append("view_angle")
    except (AttributeError, TypeError, ValueError, RuntimeError, OSError):
        pass

    # These names mirror the Origin Pie Plot View dialog. They are optional
    # because the 2-D template does not expose all of them.
    option_aliases = (
        ("start_azimuth", "-pgpa"),
        ("horizontal_offset", "-pgpho"),
        ("doughnut_hole", "-pgpdh"),
    )
    for key, option in option_aliases:
        value = style.get(key)
        if value is None:
            continue
        try:
            plot.set_cmd(f"{option} {float(value):g}")
            applied.append(key)
        except (AttributeError, TypeError, ValueError, RuntimeError, OSError):
            continue
    # Thickness is a template-specific 3-D property. Keep it in the style
    # contract for future Origin builds, but do not emit an undocumented
    # command that can invalidate a saved graph on older versions.
    return applied


def _category_key(value: Any) -> tuple[str, Any]:
    """Canonical key used to align grouped-column rows across series."""
    if isinstance(value, bool):
        return ("text", str(value))
    try:
        number = float(value)
        if number == number and abs(number) != float("inf"):
            return ("number", number)
    except (TypeError, ValueError):
        pass
    return ("text", str(value))


def _shared_column_categories(series_list: list[dict[str, Any]]) -> list[Any]:
    """Collect first-seen categorical X labels for a panel-wide column sheet.

    Older code assumed categories were the consecutive numeric values 1..N;
    that produced an empty X column for normal string labels and misaligned
    sparse numeric categories.  Keeping the reference order works for both
    cases and remains stable when another series omits a category.
    """
    result: list[Any] = []
    seen: set[tuple[str, Any]] = set()
    for series in series_list:
        source = series.get("marker_data") or series.get("data", {})
        for value in source.get("x", []) or []:
            key = _category_key(value)
            if key in seen:
                continue
            seen.add(key)
            result.append(value)
    return result


def _text_frame_geometry(panel: dict[str, Any], style: dict[str, Any]) -> FrameGeometry | None:
    """Build the page/data conversion context used by measured text labels."""
    frame = panel.get("frame_percent") or style.get("pie_frame") or style.get("plot_frame") or {}
    axes = panel.get("axes", {}) or {}
    x_axis, y_axis = axes.get("x", {}) or {}, axes.get("y", {}) or {}
    if not all(key in frame for key in ("left", "top", "right", "bottom")):
        return None
    try:
        left, top = float(frame["left"]) / 100.0, float(frame["top"]) / 100.0
        width = (100.0 - float(frame["left"]) - float(frame["right"])) / 100.0
        height = (100.0 - float(frame["top"]) - float(frame["bottom"])) / 100.0
        return FrameGeometry(
            left=left, top=top, width=width, height=height,
            x_axis=AxisGeometry(float(x_axis["min"]), float(x_axis["max"]), x_axis.get("scale") == "log10"),
            y_axis=AxisGeometry(float(y_axis["min"]), float(y_axis["max"]), y_axis.get("scale") == "log10"),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _panel_wide_sheet(op: Any, panel: dict[str, Any], book: Any | None = None) -> tuple[Any, dict[str, dict[str, int]]]:
    """Create one worksheet containing all series as multiple X/Y pairs.

    Marker observations, error magnitudes, and fitted/derived traces remain
    separate columns, but the user sees one compact replacement surface for a
    panel instead of one worksheet per curve and one more per fit.
    """
    frame_data: dict[str, list[Any]] = {}
    column_maps: dict[str, dict[str, int]] = {}
    headers: list[str] = []
    header_index: dict[str, int] = {}
    panel_series = panel.get("series", [])
    shared_x_header = panel.get("shared_x_header")
    column_series = [series for series in panel_series if series.get("kind") == "column"]
    shared_x_series = [series for series in panel_series if series.get("kind") != "column"]
    shared_x_values: list[float] = []
    if shared_x_header and column_series:
        shared_x_values = _shared_column_categories(column_series)
        header_index[shared_x_header] = len(headers)
        headers.append(shared_x_header)
        frame_data[shared_x_header] = shared_x_values
    elif shared_x_header and shared_x_series:
        source = shared_x_series[0].get("marker_data") or shared_x_series[0].get("data", {})
        shared_x_values = list(source.get("x", []))
        header_index[shared_x_header] = len(headers)
        headers.append(shared_x_header)
        frame_data[shared_x_header] = shared_x_values

    shared_x_index = {_category_key(value): index for index, value in enumerate(shared_x_values)}

    def add_column(header: str, values: list[Any]) -> int:
        if header in header_index:
            # The shared categorical X column is intentionally reused by all
            # bars in a panel-wide column plot.
            return header_index[header]
        index = len(headers)
        header_index[header] = index
        headers.append(header)
        frame_data[header] = values
        return index

    for series in panel_series:
        mapping = _wide_columns(series)
        mapping.update(series.get("wide_columns", {}) or {})
        series["wide_columns"] = mapping
        marker = dict(series.get("data", {}) or {})
        marker.update(series.get("marker_data", {}) or {})
        line = series.get("line_data") or {}
        ordered = ["x", "y", "y_error", "x_error", "color_rgb"]
        actual: dict[str, int] = {}
        for key in ordered:
            if key not in mapping:
                continue
            header = mapping[key]
            if shared_x_header:
                if key == "x":
                    actual[key] = header_index[shared_x_header]
                    continue
                if series.get("kind") != "column":
                    if key not in marker:
                        continue
                    actual[key] = add_column(header, list(marker[key]))
                    continue
                if key not in marker:
                    continue
                padded = [float("nan")] * len(shared_x_values)
                for value_x, value_y in zip(marker.get("x", []), marker[key]):
                    row = shared_x_index.get(_category_key(value_x))
                    if row is not None:
                        padded[row] = value_y
                actual[key] = add_column(header, padded)
                continue
            if key not in marker:
                continue
            actual[key] = add_column(header, list(marker[key]))
        for key in ("fit_x", "fit_y", "fit_lower", "fit_upper"):
            source_key = {
                "fit_x": "x", "fit_y": "y",
                "fit_lower": "lower", "fit_upper": "upper",
            }[key]
            if key not in mapping or source_key not in line:
                continue
            header = mapping[key]
            actual[key] = add_column(header, list(line[source_key]))
        column_maps[series["id"]] = actual
    # Fit traces are intentionally denser than marker observations.  Build
    # each column as a Series so pandas pads shorter X/Y pairs independently
    # instead of rejecting the compact wide table for unequal lengths.
    frame = pd.DataFrame({key: pd.Series(values) for key, values in frame_data.items()})
    sheet_name = str(panel.get("data_worksheet", f"{panel['id']}_Data"))
    sheet = add_dataframe(op, frame, sheet_name, book=book)
    try:
        sheet.set_labels(headers)
        for index, header in enumerate(headers):
            # Short names are deliberately compact and readable in Origin's
            # column tabs; long names retain the complete series/role header.
            sheet.set_label(index, header, "S")
    except Exception:
        pass
    return sheet, column_maps


def build_reference_template(op: Any, spec: dict[str, Any]) -> tuple[list[Any], list[Any]]:
    """Render a screenshot-only PlotSpec with only replaceable Origin-native data."""
    graphs: list[Any] = []
    sheets: list[Any] = []
    # Keep all XY replacement worksheets for this reference project in one
    # Origin workbook. Matrix plots still use their required native matrix
    # book, but do not create a new worksheet book for every curve.
    data_book = None
    data_book_name = str(spec.get("data_book_name", "Reference Data"))
    for panel in spec["panels"]:
        style = dict(spec.get("style", {}))
        style.update(panel.get("style", {}))
        family = panel.get("graph_family", "scatter")
        graph = _new_graph(op, family, style)
        try:
            graph.name = str(panel["id"])
        except Exception:
            pass
        # Freeze automatic legend reconstruction while the editable line and
        # marker plots are added.  Otherwise Origin appends every dense helper
        # trace to a hand-authored legend as it is created.
        try:
            # The LabTalk page property is available across Origin builds;
            # it is the Python equivalent of GraphPage::SetLegendsUpdateMode.
            graph.lt_exec("page.legendupdatemode=2;")  # LEGEND_UPDATE_MODE_NO
        except Exception:
            try:
                graph.set_int("legendupdatemode", 2)
            except Exception:
                pass
        # page style is applied before the layer style so axis extents remain stable.
        apply_page_style(graph, style)
        if any(series.get("kind") == "column" for series in panel.get("series", [])):
            # In a panel-wide column sheet each bar has one finite Y and NaN
            # placeholders at the other category rows.  Include those X
            # spacings when Origin computes the bar width.
            try:
                graph.lt_exec("page.barWidthNoMissing=0;")
            except Exception:
                pass
        layer = graph[0]
        special_polar = family in PIE_FAMILIES
        special_heatmap = family == "heatmap"
        frame = panel.get("frame_percent") or (
            style.get("pie_frame") if special_polar else style.get("plot_frame")
        )
        local_spec = {"style": {**style, "plot_frame": frame}, "axes": panel.get("axes", {}),
                      "legend": panel.get("legend", {}), "annotations": panel.get("annotations", {})}
        # Built-in Origin templates can carry placeholder plots (the column
        # template commonly starts with five empty plots).  Leaving them in
        # the layer makes a replacement bar series become a ten-plot grouped
        # chart with narrow, recoloured bars.  Remove template data plots
        # before attaching the screenshot-derived editable series; specialized
        # pie/heatmap templates keep their native objects.
        if not special_polar and not special_heatmap:
            try:
                for existing_plot in list(layer.plot_list()):
                    layer.remove_plot(existing_plot)
            except Exception:
                pass
        if special_polar:
            # Pie-family templates have no Cartesian scale to configure, but
            # their layer rectangle still controls the doughnut's centre and
            # radius. Apply only the measured frame geometry.
            apply_layer_style(layer, {"style": local_spec["style"], "axes": {}})
        elif special_heatmap:
            # Heat_Map.otpu carries a matrix-specific coordinate transform;
            # applying Cartesian min/max from a screenshot clips the matrix
            # on current Origin builds.  Keep the template transform and
            # control only the frame here; labels are supplied explicitly
            # below so the visual coordinates remain screenshot-driven.
            apply_layer_style(layer, {"style": local_spec["style"], "axes": {}})
            for axis_name in ("x", "y"):
                try:
                    layer.axis(axis_name).title = ""
                    layer.set_int(f"{axis_name}.showLabels", 0)
                    layer.set_int(f"{axis_name}.ticks", 0)
                except Exception:
                    pass
        else:
            apply_layer_style(layer, local_spec)
        # Axis titles are part of the reference geometry.  Allow the
        # screenshot reader to pin their data-attached anchors instead of
        # relying on Origin's template-dependent defaults.
        title_positions = style.get("axis_title_positions", {}) or {}
        for axis_label, position in title_positions.items():
            if not isinstance(position, dict):
                continue
            try:
                title_obj = layer.label(str(axis_label))
                if title_obj is not None:
                    title_obj.set_int("attach", 2)
                    if position.get("x1") is not None:
                        title_obj.set_float("x1", float(position["x1"]))
                    if position.get("y1") is not None:
                        title_obj.set_float("y1", float(position["y1"]))
                    if position.get("x") is not None:
                        title_obj.set_float("x", float(position["x"]))
                    if position.get("y") is not None:
                        title_obj.set_float("y", float(position["y"]))
            except Exception:
                pass
        plots = []
        column_plots = []
        # Keep the actual pie/doughnut plot objects separate from any helper
        # line plots.  A panel may contain more than one polar series and the
        # generic ``plots`` list also contains fitted traces.
        polar_plots = []
        legend_plot_indices: list[int] = []
        # Pie labels drawn inside coloured wedges are centred in the source
        # figures. If the reader did not resolve an explicit anchor, use the
        # white in-wedge colour as a conservative cue; external labels keep
        # their requested left/right anchor and leader-line geometry.
        if special_polar:
            for item in panel.get("labels", []):
                if (item.get("attach", 2) == 1 and item.get("color")
                        and "h_anchor" not in item):
                    item["h_anchor"] = "center"
                    item.setdefault("v_anchor", "middle")
        # A panel-wide sheet is the replacement surface for multi-series
        # panels.  Each curve receives its own X/Y pair (and optional error,
        # colour, and fit columns) in one worksheet, which is much easier to
        # audit and replace than a tab per curve.
        panel_wide_sheet = None
        panel_wide_maps: dict[str, dict[str, int]] = {}
        if not special_heatmap and panel.get("data_layout") == "panel_wide" and panel.get("series"):
            panel_wide_sheet, panel_wide_maps = _panel_wide_sheet(op, panel, data_book)
            if data_book is None:
                data_book = panel_wide_sheet.get_book()
                try:
                    data_book.lname = data_book_name
                except Exception:
                    pass
            sheets.append(panel_wide_sheet)
        if special_heatmap:
            # Heat_Map.otpu is a native matrix plot.  Keep its Z values in an
            # editable matrix sheet instead of approximating the cells with
            # raster rectangles or a dense XY trace.
            import numpy as np

            matrix = panel.get("matrix", {}) or {}
            values = np.asarray(matrix.get("values", []), dtype=float)
            matrix_sheet = op.new_sheet("m", str(matrix.get("worksheet", panel["id"] + " Matrix")))
            matrix_sheet.from_np(values)
            if data_book is None:
                data_book = matrix_sheet.get_book()
                try:
                    data_book.lname = data_book_name
                except Exception:
                    pass
            heat_plot = layer.add_mplot(matrix_sheet, 0, type=105)
            try:
                layer.rescale()
            except Exception:
                pass
            sheets.append(matrix_sheet)
            try:
                palette = matrix.get("colormap") or style.get("colormap")
                if palette:
                    heat_plot.colormap = str(palette)
            except Exception:
                pass
            try:
                # Suppress Heat_Map.otpu's localized placeholder title.  The
                # screenshot reader can add the actual colourbar title as a
                # normal editable page label below.
                for obj in layer.obj.GetGraphObjects():
                    if obj.GetName() == "SPECTRUM1":
                        obj.SetNumProp("title.text", 0)
                        break
            except Exception:
                pass
            colorbar_frame = matrix.get("colorbar_frame") or style.get("colorbar_frame")
            if isinstance(colorbar_frame, dict):
                try:
                    # Heat_Map.otpu exposes its native colour scale as the
                    # SPECTRUM1 graph object.  These coordinates are in the
                    # object's page units (not pixels); keeping them in the
                    # screenshot spec lets a reader calibrate the bar without
                    # replacing the editable matrix plot.
                    for obj in layer.obj.GetGraphObjects():
                        if obj.GetName() != "SPECTRUM1":
                            continue
                        for key in ("x", "y", "width", "height"):
                            if colorbar_frame.get(key) is not None:
                                obj.SetNumProp(key, float(colorbar_frame[key]))
                        break
                except Exception:
                    pass
            plots.append(heat_plot)
        for series in panel.get("series", []):
            kind = series.get("kind", "scatter")
            plot_style = series.get("style", {}) or {}
            data = series.get("data", {})
            marker_data = series.get("marker_data")
            marker_source = dict(data or {})
            marker_source.update(marker_data or {})
            # Put the marker-and-line plot first.  The explicit legend refers
            # to this plot so its sample contains the same line + symbol as
            # the reference.  A dense trace is then overlaid without adding a
            # second legend entry.
            wide_map = panel_wide_maps.get(series.get("id", ""), {})
            if panel_wide_sheet is not None and wide_map:
                marker_sheet = panel_wide_sheet
                marker_cols = wide_map
            else:
                marker_cols = {}
                marker_sheet = _add_template_sheet(
                    op, series, marker_data, series.get("marker_worksheet"), data_book
                )
                if data_book is None:
                    data_book = marker_sheet.get_book()
                    try:
                        data_book.lname = data_book_name
                    except Exception:
                        pass
                sheets.append(marker_sheet)
            plot_type = {"line": "l", "line_symbol": "y", "column": "c", "scatter": "s"}.get(kind)
            yerr = marker_cols.get("y_error", -1) if marker_cols else (2 if "y_error" in marker_source else -1)
            xerr = marker_cols.get("x_error", -1) if marker_cols else (3 if "x_error" in marker_source else -1)
            if kind in PIE_FAMILIES:
                # Pie-family templates infer the categorical slice geometry
                # from the first two worksheet columns and reject a Cartesian
                # plot-type code.
                marker_plot = layer.add_plot(
                    marker_sheet,
                    # Origin's native 2-D/3-D pie plot consumes one Y
                    # dataset; the adjacent categorical X column remains in
                    # the worksheet for replacement labels but must not be
                    # passed as an XY range (that silently creates bars with
                    # PIE2D.OTP on some Origin builds).
                    coly=marker_cols.get("y", 1) if marker_cols else 1,
                    colx=-1,
                )
                # Native pie templates often enable percentage labels and a
                # total label by default.  Reference templates provide their
                # own page-attached labels, so disable the generated labels
                # unless the screenshot reader explicitly asks for them.
                if plot_style.get("show_data_labels", False) is not True:
                    try:
                        # Pie templates expose the label switch as a graph
                        # property rather than the Cartesian ``-q`` option.
                        layer.set_int(f"plot{marker_plot.index() + 1}.label.show", 0)
                    except Exception:
                        pass
                # The Doughnut.OTP template also contains a static total
                # object named ``Text``.  It is a template artefact, not part
                # of the screenshot unless the reference explicitly shows a
                # total, so remove it before adding the measured centre text.
                try:
                    if layer.label("Text") is not None:
                        layer.remove_label("Text")
                except Exception:
                    pass
                # A pie/doughnut uses the fill colour of each wedge.  When a
                # screenshot provides explicit RGB values, keep those values
                # in an editable helper column and bind the plot's RGB source
                # to it.  Origin accepts the same BGR integer returned by its
                # ``color(r,g,b)`` LabTalk function.
                if "color_rgb" in data or "color_rgb" in marker_cols:
                    try:
                        # Pie/doughnut wedges use the symbol-fill RGB
                        # selector; ``-cr`` only changes the outline/line.
                        # Keep both bindings so the wedge border follows the
                        # same editable colour column when the plot exposes it.
                        rgb_index = marker_cols.get("color_rgb", -1) if marker_cols else _template_data_column_index(marker_source, "color_rgb")
                        if rgb_index < 0:
                            raise ValueError("pie colour source column is unavailable")
                        rgb_range = f"{marker_sheet.lt_range()}!{_column_letter(rgb_index)}"
                        marker_plot.set_cmd(f"-csfr {rgb_range}")
                        marker_plot.set_cmd(f"-cr {rgb_range}")
                    except Exception:
                        pass
                if plot_style.get("colors"):
                    try:
                        # Pie/doughnut plots consume a colour-list string
                        # rather than the single-series ``color`` property.
                        # Keep the list in the spec so each wedge remains
                        # visually tied to its editable category row.
                        # Origin's one-Y pie range follows worksheet row order
                        # for its categorical wedges.  Keep the user-facing
                        # colour list in that same order so the first value in
                        # the replacement sheet retains the first reference
                        # colour after save/reopen.
                        color_list = list(plot_style["colors"])
                        expressions = []
                        for color in color_list:
                            value = str(color).lstrip("#")
                            if len(value) == 6:
                                expressions.append(
                                    f"color({int(value[0:2], 16)},{int(value[2:4], 16)},{int(value[4:6], 16)})"
                                )
                            else:
                                expressions.append(str(color))
                        # Keep the palette expression on the editable plot;
                        # Origin builds differ in whether they accept a
                        # pattern-fill increment list for native pie plots.
                        try:
                            from originpro.utils import ocolor
                            numeric_colors = [str(int(ocolor(str(color)))) for color in color_list]
                            marker_plot.set_cmd("-cue 1", "-cuf " + " ".join(numeric_colors))
                        except Exception:
                            pass
                        marker_plot.colormap = "{" + ",".join(expressions) + "}"
                        # Setting a colormap can reset the point-colour mode
                        # on some Origin builds; reapply the direct RGB data
                        # binding after the palette assignment.
                        if "color_rgb" in data or "color_rgb" in marker_cols:
                            rgb_index = marker_cols.get("color_rgb", -1) if marker_cols else _template_data_column_index(marker_source, "color_rgb")
                            if rgb_index < 0:
                                raise ValueError("pie colour source column is unavailable")
                            rgb_range = f"{marker_sheet.lt_range()}!{_column_letter(rgb_index)}"
                            marker_plot.set_cmd(f"-csfr {rgb_range}")
                            marker_plot.set_cmd(f"-cr {rgb_range}")
                    except Exception:
                        pass
                # Keep the native Pie Plot View parameters attached to the
                # editable plot. This is applied after colour assignment so
                # Origin's template does not overwrite the requested view.
                _apply_pie_geometry(marker_plot, family, plot_style)
            else:
                marker_plot = layer.add_plot(marker_sheet,
                                             coly=marker_cols.get("y", 1) if marker_cols else 1,
                                             colx=marker_cols.get("x", 0) if marker_cols else 0,
                                             type=("s" if marker_data else plot_type),
                                             colyerr=yerr, colxerr=xerr)
            try:
                if plot_style.get("color"):
                    marker_plot.color = plot_style["color"]
                if plot_style.get("symbol") is not None:
                    marker_plot.symbol_kind = int(plot_style["symbol"])
                if plot_style.get("symbol_size") is not None:
                    marker_plot.symbol_size = float(plot_style["symbol_size"])
                if plot_style.get("symbol_interior") is not None:
                    marker_plot.symbol_interior = int(plot_style["symbol_interior"])
                if plot_style.get("transparency") is not None:
                    marker_plot.transparency = int(plot_style["transparency"])
                if plot_style.get("line_width") is not None:
                    marker_plot.set_float("line.width", float(plot_style["line_width"]))
                apply_plot_border(marker_plot, plot_style, kind=kind)
                error_style = plot_style.get("error_bars", plot_style.get("error_bar"))
                if error_style and (yerr >= 0 or xerr >= 0):
                    apply_error_bar_style(marker_plot, error_style)
            except Exception:
                pass
            plots.append(marker_plot)
            if kind in {"column", "grouped_column", "bar"}:
                column_plots.append(marker_plot)
            if special_polar:
                polar_plots.append(marker_plot)
            # Origin's legend notation is one-based, while Plot.index() is
            # zero-based.  Record the marker plot even when a dense line plot
            # is also present for this series.
            try:
                legend_plot_indices.append(int(marker_plot.index()) + 1)
            except Exception:
                legend_plot_indices.append(len(plots))
            if "line_data" in series:
                if panel_wide_sheet is not None and wide_map.get("fit_x") is not None and wide_map.get("fit_y") is not None:
                    line_sheet = panel_wide_sheet
                    line_x, line_y = wide_map["fit_x"], wide_map["fit_y"]
                else:
                    line_sheet = _add_template_sheet(op, series, series["line_data"],
                                                      series.get("line_worksheet"), data_book)
                    sheets.append(line_sheet)
                    line_x, line_y = 0, 1
                band_plots: list[Any] = []
                lower_column = wide_map.get("fit_lower") if panel_wide_sheet is not None else (2 if "lower" in series["line_data"] else None)
                upper_column = wide_map.get("fit_upper") if panel_wide_sheet is not None else (3 if "upper" in series["line_data"] else None)
                # A fit can retain candidate lower/upper columns for audit and
                # replacement without drawing a confidence band on every fit.
                # Render it only when the reference spec explicitly opts in
                # through confidence_band, fit_band, or band style metadata.
                band_style = plot_style.get(
                    "confidence_band",
                    plot_style.get("fit_band", plot_style.get("band")),
                )
                band_enabled = isinstance(band_style, dict) and band_style.get("visible", True) is not False
                if lower_column is not None and upper_column is not None and band_enabled:
                    band_plots = _add_confidence_band(
                        layer, line_sheet, line_x, int(lower_column), int(upper_column), plot_style
                    )
                    plots.extend(band_plots)
                line_plot = layer.add_plot(line_sheet, coly=line_y, colx=line_x, type="l")
                try:
                    if plot_style.get("color"):
                        line_plot.color = plot_style["color"]
                    line_plot.symbol_kind = 0
                    if plot_style.get("line_width") is not None:
                        line_plot.set_float("line.width", float(plot_style["line_width"]))
                except Exception:
                    pass
                plots.append(line_plot)
        # Native column plots need an explicit grouped layer after all series
        # are attached.  Without this Origin keeps later bar plots overlaid on
        # the first bar, which hides the colour/group structure in compact
        # grouped-column references.
        column_series_have_shared_categories = all(
            len((series.get("marker_data") or series.get("data", {})).get("x", []) or []) > 1
            for series in panel.get("series", []) if series.get("kind") in {"column", "grouped_column"}
        )
        if (family in {"column", "grouped_column"} and len(column_plots) > 1
                and len(plots) == len(column_plots)
                and (family == "grouped_column" or column_series_have_shared_categories)):
            try:
                layer.group()
            except Exception:
                pass
            # Grouping applies the template's palette and can overwrite the
            # screenshot-derived per-series fills.  Restore explicit colors
            # after the group operation so a researcher's replacement bars
            # retain the reference encoding.
            for plot_obj, series_obj in zip(column_plots, panel.get("series", [])):
                try:
                    color = (series_obj.get("style", {}) or {}).get("color")
                    if color:
                        plot_obj.color = color
                except Exception:
                    pass
        # Do not rescale: the displayed limits are part of the reference style.
        for label in panel.get("labels", []):
            try:
                # ``text_markup`` is preferred when the reader has already
                # recovered Origin's rich text.  Plain OCR labels still pass
                # through conservative Unicode sub/superscript conversion.
                text = layer.add_label(text_value(label), label.get("x"), label.get("y"))
                if text and label.get("color"):
                    text.color = label["color"]
                if text and label.get("attach") is not None:
                    attach = int(label["attach"])
                    coordinate_space = "page" if attach == 1 else "data"
                    x = label.get("x1", label.get("x")) if attach == 1 else label.get("x")
                    y = label.get("y1", label.get("y")) if attach == 1 else label.get("y")
                    if x is None or y is None:
                        raise ValueError("attached text label needs x/y coordinates")
                    frame_geometry = _text_frame_geometry(panel, style) if coordinate_space == "page" else None
                    if coordinate_space == "page" and frame_geometry is None:
                        # Preserve the explicit page anchor on older/minimal
                        # specs that do not carry frame calibration.
                        text.set_int("attach", 1)
                        text.set_float("x1", float(x))
                        text.set_float("y1", float(y))
                        if label.get("font_size_pt") is not None:
                            text.set_float("fsize", float(label["font_size_pt"]))
                        if label.get("rotate") is not None:
                            text.set_float("rotate", float(label["rotate"]))
                        # Origin exposes page-attached ``dx``/``dy`` on the
                        # label object in this branch.  Use them when an
                        # explicit center/right or middle/bottom anchor is
                        # requested instead of silently treating x1/y1 as a
                        # top-left corner.
                        try:
                            anchor_name = str(label.get("anchor", label.get("text_anchor", ""))).lower()
                            anchor_map = {
                                "center": ("center", "middle"), "middle": ("center", "middle"),
                                "top_left": ("left", "top"), "top_center": ("center", "top"),
                                "top_right": ("right", "top"), "bottom_left": ("left", "bottom"),
                                "bottom_center": ("center", "bottom"), "bottom_right": ("right", "bottom"),
                            }
                            mapped_h, mapped_v = anchor_map.get(anchor_name, (None, None))
                            h_anchor = label.get("h_anchor", mapped_h or ("center" if label.get("rotate") is not None else "left"))
                            v_anchor = label.get("v_anchor", mapped_v or "top")
                            dx = float(text.get_float("dx"))
                            dy = float(text.get_float("dy"))
                            text.set_float("x1", float(x) - (dx / 2 if h_anchor == "center" else dx if h_anchor == "right" else 0.0))
                            text.set_float("y1", float(y) - (dy / 2 if v_anchor == "middle" else dy if v_anchor == "bottom" else 0.0))
                        except (AttributeError, TypeError, ValueError, RuntimeError, OSError):
                            pass
                        continue
                    # Categorical labels are anchored on their marker, so a
                    # rotated label defaults to centre alignment.  Scientific
                    # callouts keep the historical left/top default unless
                    # the reader specifies an explicit anchor.
                    anchor_name = str(label.get("anchor", label.get("text_anchor", ""))).lower()
                    anchor_map = {
                        "center": ("center", "middle"),
                        "middle": ("center", "middle"),
                        "top_left": ("left", "top"),
                        "top_center": ("center", "top"),
                        "top_right": ("right", "top"),
                        "bottom_left": ("left", "bottom"),
                        "bottom_center": ("center", "bottom"),
                        "bottom_right": ("right", "bottom"),
                    }
                    mapped_h, mapped_v = anchor_map.get(anchor_name, (None, None))
                    default_h = "center" if label.get("rotate") is not None else "left"
                    h_anchor = label.get("h_anchor", mapped_h or default_h)
                    v_anchor = label.get("v_anchor", mapped_v or "top")
                    layout_text_label(
                        text,
                        TextLayout(
                            x=float(x), y=float(y), coordinate_space=coordinate_space,
                            h_anchor=h_anchor,
                            v_anchor=v_anchor,
                            paragraph_align=label.get("paragraph_align"),
                            rotation=label.get("rotate"),
                            font_size_pt=label.get("font_size_pt"),
                        ),
                        frame=frame_geometry,
                    )
                elif text and label.get("font_size_pt"):
                    text.set_float("fsize", label["font_size_pt"])
            except Exception:
                pass
        # Reference templates may carry data-attached significance bars and
        # callouts in addition to page-attached labels.
        apply_annotations(layer, panel.get("annotations", {}) or {})
        try:
            legend = layer.label("Legend")
            legend_spec = panel.get("legend", {}) or {}
            visible = bool(legend_spec.get("visible", True))
            manual_legend = bool(legend_spec.get("manual_text", True))
            # Origin's native Legend is the object that survives save/reopen;
            # use it deliberately, but write an explicit entry list so dense
            # helper traces never become extra rows.  Its sample length is
            # controlled by page.legendsymbolwidth, rather than ``\\l(n)``
            # text-object geometry, which avoids the reopen-time long tails.
            if legend is not None:
                legend.show = visible
                try:
                    legend.set_int("show", int(visible))
                    legend.set_int("visible", int(visible))
                except Exception:
                    pass
                if visible and panel.get("series"):
                    try:
                        # Write the visible series explicitly. The update mode
                        # is disabled, so Origin will not append the dense
                        # helper line plots; plain names avoid template-specific
                        # subscript syntax when the OPJU is reopened.
                        entries = [
                            f"\\l({plot_index}) {_legend_text(series)}"
                            for plot_index, series in zip(legend_plot_indices, panel["series"])
                        ]
                        legend.text = "\r".join(entries)
                        symbol_width = float(legend_spec.get("symbol_width_percent", 36))
                        graph.lt_exec(f"page.legendsymbolwidth={symbol_width};")
                        # Origin's native legend samples are tied to the
                        # actual dataplot marker.  Position the object in
                        # layer coordinates from the screenshot spec before
                        # deciding whether a manual fallback is needed.
                        if legend_spec.get("x") is not None:
                            legend.set_float("x1", float(legend_spec["x"]))
                        if legend_spec.get("y") is not None:
                            legend.set_float("y1", float(legend_spec["y"]))
                        if legend_spec.get("font_size_pt") is not None:
                            legend.set_float("fsize", float(legend_spec["font_size_pt"]))
                        if legend_spec.get("border") is False:
                            legend.set_int("border", 0)
                        if legend_spec.get("fill") is False:
                            legend.set_int("fill", 0)
                        if legend_spec.get("border") is False or legend_spec.get("fill") is False:
                            # ``background`` is the Origin property for the
                            # surrounding legend box (border/fill are color
                            # properties and do not disable that box).
                            legend.set_int("background", 0)
                            graph.lt_exec("legend.background=0;")
                        if (not legend_spec.get("manual_fallback", True)
                                and legend_spec.get("x") is None
                                and legend_spec.get("y") is None
                                and legend_spec.get("native_right_align", True)):
                            # Origin defines Legend.x/y as the object centre;
                            # using its own dx/dy keeps every native marker
                            # sample inside the measured layer rectangle,
                            # independent of font metrics on this machine.
                            graph.lt_exec("legend.x=layer.x.to-legend.dx/2; legend.y=layer.y.to-legend.dy/2;")
                        # Native Legends are template-owned objects.  Some
                        # Origin builds recreate them on reopen even after
                        # ``show=0`` or an update-mode change, which leaves a
                        # second, displaced legend over the calibrated one.
                        # Once the explicit entries have been captured, remove
                        # the native object when the persistent fallback is
                        # requested.  The fallback rows below are ordinary
                        # editable graph objects and therefore remain stable
                        # across save/reopen.
                        if legend_spec.get("manual_fallback", True):
                            try:
                                layer.remove_label("Legend")
                                legend = None
                            except Exception:
                                pass
                        # Add a stable, data-attached fallback legend at the
                        # measured coordinates. Origin may reposition its
                        # native Legend while reopening a template; these
                        # ordinary labels/lines keep the visual key visible
                        # and editable in that case.
                        if legend_spec.get("manual_fallback", True):
                            # Page-attached fallback rows are the stable way
                            # to place legends outside the plot frame (and on
                            # log axes).  Data coordinates cannot express a
                            # legend to the right of a log plot without
                            # clipping or wildly changing row spacing.
                            if str(legend_spec.get("coordinate_space", "data")).lower() == "page":
                                lx = float(legend_spec.get("x", 0.72))
                                ly = float(legend_spec.get("y", 0.18))
                                row_step = float(legend_spec.get("row_step", 0.065))
                                sample_width = float(legend_spec.get("sample_width", 0.045))
                                text_offset = float(legend_spec.get("text_offset", sample_width + 0.018))
                                show_sample_line = bool(legend_spec.get("sample_line", True))
                                # Origin's symbol_kind numbering used by the
                                # bridge: square, circle, up-triangle,
                                # down-triangle, diamond.  Keep the fallback
                                # key visually consistent with native plots.
                                symbol_chars = {1: "■", 2: "●", 3: "▲", 4: "▼", 5: "◆", 15: "◀", 16: "▶", 17: "⬢", 19: "⬟"}
                                legend_font_size = float(legend_spec.get("native_font_size_pt", legend_spec.get("font_size_pt", 11.5)))
                                for i, series in enumerate(panel["series"]):
                                    label_y = ly + i * row_step
                                    color = series.get("style", {}).get("color")
                                    try:
                                        line = layer.add_line(0, 0, 0, 0) if show_sample_line else None
                                        if line:
                                            line.set_int("attach", 1)
                                            line.set_float("x1", lx)
                                            line.set_float("x2", lx + sample_width)
                                            line.set_float("y1", label_y)
                                            line.set_float("y2", label_y)
                                            if series.get("style", {}).get("line_width") is not None:
                                                line.width = float(series["style"]["line_width"])
                                            if color:
                                                line.color = color
                                        marker = layer.add_label(symbol_chars.get(int(series.get("style", {}).get("symbol", 0)), "●"), lx, label_y)
                                        text_obj = layer.add_label(_legend_text(series), lx + text_offset, label_y)
                                        for obj in (marker, text_obj):
                                            if obj:
                                                obj.set_int("attach", 1)
                                                target_x = float(obj is text_obj and lx + text_offset or lx)
                                                obj.set_float("x1", target_x)
                                                obj.set_float("y1", label_y)
                                                obj.set_float("fsize", legend_font_size)
                                                # Page-attached label dimensions
                                                # are available after the font is
                                                # set.  Center the symbol and
                                                # vertically center both objects
                                                # on the legend row; this avoids
                                                # the template-dependent
                                                # baseline drift seen after
                                                # save/reopen.
                                                try:
                                                    dx = float(obj.get_float("dx"))
                                                    dy = float(obj.get_float("dy"))
                                                    if obj is marker:
                                                        obj.set_float("x1", target_x - dx / 2.0)
                                                    obj.set_float("y1", float(label_y) - dy / 2.0)
                                                except (AttributeError, TypeError, ValueError, RuntimeError, OSError):
                                                    pass
                                        if marker and color:
                                            marker.color = color
                                    except Exception:
                                        pass
                                # The native template legend was removed above;
                                # page rows are already in the requested space.
                                # Do not ``continue`` here: this block is
                                # inside the panel loop, and skipping the
                                # final graph registration would leave an
                                # apparently saved but unopenable OPJU.  Mark
                                # this fallback complete so the legacy
                                # data-space branch below does not duplicate
                                # the rows.
                                legend_spec["manual_fallback"] = False
                                try:
                                    graph.lt_exec("legend.show=0; legend.visible=0;")
                                except Exception:
                                    pass
                            if legend_spec.get("manual_fallback", True):
                                xaxis, yaxis = panel.get("axes", {}).get("x", {}), panel.get("axes", {}).get("y", {})
                                xmin, xmax = float(xaxis.get("min", 0)), float(xaxis.get("max", 1))
                                ymin, ymax = float(yaxis.get("min", 0)), float(yaxis.get("max", 1))
                                ly = float(legend_spec.get("y", ymax - .04 * (ymax - ymin)))
                                sample_x = float(legend_spec.get("sample_x", legend_spec.get("x", xmin) + .04 * (xmax - xmin)))
                                text_x = float(legend_spec.get("text_x", sample_x + .3 * (xmax - xmin)))
                                row_step = float(legend_spec.get("row_step_data", .06 * (ymax - ymin)))
                                sample_width = float(legend_spec.get("sample_width_data", max(.12, (text_x - sample_x) * .72)))
                                show_sample_line = bool(legend_spec.get("sample_line", True))
                                symbol_chars = {1: "■", 2: "●", 3: "▲", 4: "▼", 5: "◆", 15: "◀", 16: "▶", 17: "⬢", 19: "⬟"}
                                # Cover the template's auto-regenerated Legend
                                # before drawing the calibrated fallback rows.
                                # The native object is not reliably hideable on
                                # reopen, while a white graph rectangle is.
                                try:
                                    from originpro.base import GObject
                                    from originpro.utils import ocolor
                                    raw_rect = layer.obj.GraphObjects.Add(3)
                                    cover = GObject(raw_rect, layer.obj)
                                    cover.set_int("attach", 2)
                                    cover.set_float("x1", sample_x - .08)
                                    cover.set_float("x2", text_x + .55)
                                    cover.set_float("y1", ly + row_step * .55)
                                    cover.set_float("y2", ly - row_step * (len(panel["series"]) - .45))
                                    cover.set_int("fill", 1)
                                    cover.set_int("fillcolor", ocolor("white"))
                                    cover.set_int("color", ocolor("black"))
                                    cover.set_int("border", 1)
                                except Exception:
                                    pass
                            for i, series in enumerate(panel["series"]):
                                label_y = ly - i * row_step
                                color = series.get("style", {}).get("color")
                                legend_font_size = float(
                                    legend_spec.get("native_font_size_pt", legend_spec.get("font_size_pt", 11.5))
                                )
                                try:
                                    line = layer.add_line(sample_x, label_y, sample_x + sample_width, label_y) if show_sample_line else None
                                    if line:
                                        if series.get("style", {}).get("line_width") is not None:
                                            line.width = float(series["style"]["line_width"])
                                        if color:
                                            line.color = color
                                    marker = layer.add_label(symbol_chars.get(int(series.get("style", {}).get("symbol", 0)), "●"), sample_x, label_y)
                                    display_name = _legend_text(series)
                                    text_obj = layer.add_label(display_name, text_x, label_y)
                                    if marker:
                                        layout_text_label(
                                            marker,
                                            TextLayout(x=float(sample_x), y=float(label_y), coordinate_space="data",
                                                       h_anchor="center", v_anchor="middle", font_size_pt=legend_font_size),
                                        )
                                    if text_obj:
                                        layout_text_label(
                                            text_obj,
                                            TextLayout(x=float(text_x), y=float(label_y), coordinate_space="data",
                                                       h_anchor="left", v_anchor="middle", font_size_pt=legend_font_size),
                                        )
                                    if marker and color:
                                        marker.color = color
                                except Exception:
                                    pass
                    except Exception:
                        pass
        except Exception:
            pass
        # Origin can restore template typography when the first plot is added.
        # Reapply all axis and title settings after the complete plot list is
        # present, which makes the saved OPJU deterministic across templates.
        if special_polar:
            apply_layer_style(layer, {"style": local_spec["style"], "axes": {}})
        elif special_heatmap:
            apply_layer_style(layer, {"style": local_spec["style"], "axes": {}})
            for axis_name in ("x", "y"):
                try:
                    layer.axis(axis_name).title = ""
                    layer.set_int(f"{axis_name}.showLabels", 0)
                    layer.set_int(f"{axis_name}.ticks", 0)
                except Exception:
                    pass
        else:
            apply_layer_style(layer, local_spec)
        for axis_label, position in (style.get("axis_title_positions", {}) or {}).items():
            if not isinstance(position, dict):
                continue
            try:
                title_obj = layer.label(str(axis_label))
                if title_obj is not None:
                    title_obj.set_int("attach", 2)
                    if position.get("x1") is not None:
                        title_obj.set_float("x1", float(position["x1"]))
                    if position.get("y1") is not None:
                        title_obj.set_float("y1", float(position["y1"]))
                    if position.get("x") is not None:
                        title_obj.set_float("x", float(position["x"]))
                    if position.get("y") is not None:
                        title_obj.set_float("y", float(position["y"]))
                    if style.get("axis_title_font_pt") is not None:
                        title_obj.set_float("fsize", float(style["axis_title_font_pt"]))
            except Exception:
                pass
        # Applying layer/axis style after labels can make Origin templates
        # restore graph-object attachment to data coordinates.  Reapply the
        # screenshot-authored label geometry by matching the existing object
        # text; this avoids creating duplicate labels while preserving rich
        # text, subscripts, rotation, and page anchors on save/reopen.
        try:
            from originpro.base import GObject
            existing = list(layer.obj.GetGraphObjects())
            for label in panel.get("labels", []):
                target_text = str(label.get("text", ""))
                for raw in existing:
                    try:
                        if str(raw.GetText()) != target_text:
                            continue
                        obj = GObject(raw, layer.obj)
                        attach = int(label.get("attach", 2))
                        coordinate_space = "page" if attach == 1 else "data"
                        x = label.get("x1", label.get("x"))
                        y = label.get("y1", label.get("y"))
                        if x is None or y is None:
                            break
                        layout_text_label(
                            obj,
                            TextLayout(x=float(x), y=float(y), coordinate_space=coordinate_space,
                                       h_anchor=label.get("h_anchor", "left"),
                                       v_anchor=label.get("v_anchor", "top"),
                                       paragraph_align=label.get("paragraph_align"),
                                       rotation=label.get("rotate"),
                                       font_size_pt=label.get("font_size_pt")),
                            frame=_text_frame_geometry(panel, style) if coordinate_space == "page" else None,
                        )
                        break
                    except Exception:
                        continue
        except Exception:
            pass
        # Reapply the page-level legend settings after style operations; the
        # graph template may reset them when its first plot is attached.
        try:
            graph.lt_exec("page.legendupdatemode=2;")
            if manual_legend:
                graph.lt_exec(f"page.legendsymbolwidth={float((panel.get('legend', {}) or {}).get('symbol_width_percent', 36))};")
            # Plot templates can restore their own UI zoom after the first
            # plot is attached. Reapply the measured/opening zoom last so the
            # graph is visible at a useful scale when the OPJU is reopened.
            graph.lt_exec(f"page.zoom={float(style.get('open_zoom_percent', 100))};")
        except Exception:
            try:
                graph.set_int("legendupdatemode", 2)
            except Exception:
                pass
        # A final LabTalk zoom/legend update can restore graph-object
        # attachment once more.  Write page-attached reference labels after
        # that command so heatmap row/column labels and panel letters remain
        # in their measured positions on reopen.
        try:
            if any(int(label.get("attach", 2)) == 1 for label in panel.get("labels", [])):
                targets: dict[str, dict[str, Any]] = {}
                for label in panel.get("labels", []):
                    if int(label.get("attach", 2)) != 1:
                        continue
                    # The object stores normalized Origin markup while the
                    # spec may retain the OCR Unicode spelling.  Index both
                    # forms so the final save/reopen anchor pass still finds
                    # the intended label.
                    targets.setdefault(str(label.get("text", "")), label)
                    targets.setdefault(text_value(label), label)
                for raw in list(layer.obj.GetGraphObjects()):
                    raw_text = str(raw.GetText())
                    label = targets.get(raw_text)
                    if not label:
                        continue
                    raw.SetNumProp("attach", 1)
                    raw.SetNumProp("x1", float(label.get("x1", label.get("x", 0))))
                    raw.SetNumProp("y1", float(label.get("y1", label.get("y", 0))))
                    if label.get("rotate") is not None:
                        raw.SetNumProp("rotate", float(label["rotate"]))
                    if label.get("font_size_pt") is not None:
                        raw.SetNumProp("fsize", float(label["font_size_pt"]))
        except Exception:
            pass
        # Final pass for doughnut/pie wedge colours.  Numeric Origin colour
        # values work with the native pattern-fill increment list; inline
        # color(...) expressions do not persist reliably in that command.
        if special_polar:
            for series, plot in zip(panel.get("series", []), polar_plots):
                colors = (series.get("style", {}) or {}).get("colors", [])
                try:
                    from originpro.utils import ocolor
                    color_values = [str(int(ocolor(str(color)))) for color in colors]
                    if color_values:
                        plot.set_cmd("-cue 1", "-cuf " + " ".join(color_values))
                except Exception:
                    pass
        graphs.append(graph)
    return graphs, sheets


class GraphBuildError(RuntimeError):
    """Raised when a PlotSpec cannot be rendered by the installed Origin API."""


DEFAULT_TEMPLATE_BY_FAMILY = {
    "column": "column",
    "grouped_column": "column",
    "scatter": "scatter",
    "line": "line",
    "box": "box",
    "violin": "violin",
    "histogram": "histogram",
    "heatmap": "Heat_Map.otpu",
    "regression": "scatter",
    # Origin's generic PIE template is perspective/3-D by default. The build
    # path applies ``-pgpva 90`` to ordinary pie references, producing the
    # native flat view while retaining one editable plot; explicit pie3d keeps
    # the perspective path.
    "pie": "pie",
    "doughnut": "doughnut",
    "pie3d": "PIE.otpu",
    "doughnut3d": "DoughnutofPie.otpu",
}


def template_by_family() -> dict[str, str]:
    config = Path(__file__).resolve().parents[1] / "templates" / "origin" / "default_templates.json"
    try:
        loaded = json.loads(config.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            return {str(key): str(value) for key, value in loaded.items()}
    except (OSError, json.JSONDecodeError):
        pass
    return dict(DEFAULT_TEMPLATE_BY_FAMILY)


def _column_index(frame: pd.DataFrame, name: str | None, default: int = 0) -> int:
    if name and name in frame.columns:
        return int(frame.columns.get_loc(name))
    return default


def _error_column_index(
    frame: pd.DataFrame,
    spec: dict[str, Any],
    mapping: dict[str, Any],
    axis: str,
    series_position: int,
) -> int:
    """Resolve one X/Y error column from semantic mapping evidence.

    The compact inference result stores SD/SEM/CI columns under
    ``statistics.error_columns``.  Treat a single error column as shared by
    all Y series, and pair equal-length lists by series order.  Returning -1
    keeps Origin's normal no-error-bar behaviour when no evidence exists.
    """
    direct_keys = (f"{axis}_error", f"{axis}err", f"{axis}_err")
    names: list[str] = []
    for key in direct_keys:
        value = mapping.get(key)
        if isinstance(value, str):
            names.append(value)
        elif isinstance(value, list):
            names.extend(str(item) for item in value)
    statistics = spec.get("statistics", {}) or {}
    error_columns = statistics.get("error_columns", {}) or {}
    if not names and isinstance(error_columns, dict):
        values: list[Any] = []
        error_type = str(statistics.get("error_type", "")).lower()
        if error_type and isinstance(error_columns.get(error_type), list):
            values = error_columns[error_type]
        if not values:
            for candidate in ("sd", "sem", "ci"):
                if isinstance(error_columns.get(candidate), list):
                    values.extend(error_columns[candidate])
        names = [str(item) for item in values]
    names = [name for name in names if name in frame.columns]
    if not names:
        return -1
    selected = names[series_position] if len(names) > 1 and series_position < len(names) else names[0]
    return _column_index(frame, selected, -1)


def _new_graph(op: Any, family: str, style: dict[str, Any]) -> Any:
    new_graph = getattr(op, "new_graph", None)
    if not callable(new_graph):
        raise GraphBuildError("originpro does not expose project.new_graph().")
    template = style.get("origin_template") or template_by_family().get(family, "")
    try:
        return new_graph(template=template) if template else new_graph()
    except Exception as exc:
        if style.get("origin_template"):
            raise GraphBuildError(
                f"The requested Origin template {style['origin_template']!r} could not be loaded: {exc}"
            ) from exc
        try:
            return new_graph()
        except Exception as fallback_exc:
            raise GraphBuildError(f"Origin could not create a graph page: {fallback_exc}") from fallback_exc


def _add_standard_plots(graph: Any, worksheet: Any, frame: pd.DataFrame, spec: dict[str, Any]) -> list[Any]:
    layer = graph[0]
    mapping = spec.get("data_mapping", {}) or {}
    family = spec["graph_family"]
    numeric_columns = mapping.get("numeric_columns") or [str(c) for c in frame.select_dtypes(include="number").columns]
    if not numeric_columns:
        raise GraphBuildError("No numeric columns are available for the selected plot.")
    x_index = _column_index(frame, mapping.get("x"), 0)
    y_indices = [_column_index(frame, name, index) for index, name in enumerate(numeric_columns)]
    plot_type = {
        "scatter": "s",
        "line": "l",
        "regression": "s",
        "column": "c",
        "grouped_column": "c",
        "box": "?",
        "violin": "?",
        "histogram": "?",
    }.get(family, "?")
    plots: list[Any] = []
    style = spec.get("style", {}) or {}
    for series_position, y_index in enumerate(y_indices):
        yerr = _error_column_index(frame, spec, mapping, "y", series_position)
        xerr = _error_column_index(frame, spec, mapping, "x", series_position)
        try:
            plot = layer.add_plot(worksheet, coly=y_index, colx=x_index, type=plot_type,
                                  colyerr=yerr, colxerr=xerr)
        except Exception as exc:
            raise GraphBuildError(
                f"Origin could not add the {family} plot for column {y_index}: {exc}"
            ) from exc
        plots.append(plot)
        error_style = style.get("error_bars", style.get("error_bar"))
        if error_style and (yerr >= 0 or xerr >= 0):
            try:
                apply_error_bar_style(plot, error_style)
            except (AttributeError, TypeError, ValueError, RuntimeError, OSError) as exc:
                raise GraphBuildError(f"Could not apply error-bar style: {exc}") from exc
    # Group only homogeneous layers.  A fit/guide trace added to a grouped
    # column panel must not be absorbed into Origin's bar grouping state.
    if hasattr(layer, "group") and family in {"line", "grouped_column"} and len(plots) > 1:
        layer.group()
    if hasattr(layer, "rescale"):
        layer.rescale()
    apply_layer_style(layer, spec)
    apply_annotations(layer, spec.get("annotations", {}) or {})
    for plot in plots:
        apply_plot_style(plot, style)
    return plots


def _add_heatmap(graph: Any, op: Any, frame: pd.DataFrame, spec: dict[str, Any]) -> list[Any]:
    import numpy as np

    numeric = frame.select_dtypes(include="number")
    if numeric.empty:
        raise GraphBuildError("A heatmap requires a numeric matrix.")
    matrix_sheet = op.new_sheet("m", "Heatmap Matrix")
    matrix_sheet.from_np(np.asarray(numeric, dtype=float))
    layer = graph[0]
    plot = layer.add_mplot(matrix_sheet, 0, type=105)
    if hasattr(layer, "rescale"):
        layer.rescale()
    apply_layer_style(layer, spec)
    apply_annotations(layer, spec.get("annotations", {}) or {})
    return [plot]


def build_graph(op: Any, frame: pd.DataFrame, spec: dict[str, Any], workbook_name: str = "Source Data") -> tuple[Any, Any, list[Any]]:
    spec = resolve_layout(spec)
    spec = resolve_annotations(spec, frame)
    family = spec.get("graph_family")
    if not family:
        raise GraphBuildError("PlotSpec is missing graph_family.")
    worksheet = add_dataframe(op, frame, workbook_name)
    graph = _new_graph(op, family, spec.get("style", {}) or {})
    apply_page_style(graph, spec.get("style", {}) or {})
    if family == "heatmap":
        plots = _add_heatmap(graph, op, frame, spec)
    else:
        plots = _add_standard_plots(graph, worksheet, frame, spec)
    return worksheet, graph, plots
