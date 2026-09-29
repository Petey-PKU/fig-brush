from __future__ import annotations

from pathlib import Path
from statistics import median
from typing import Any

from .paths import InputValidationError, resolve_input, sha256_file


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}


def _longest_run(values: list[bool]) -> tuple[int, int, int]:
    """Return (length, start, end) for the longest true run in a row/column."""
    best = (0, 0, 0)
    start: int | None = None
    for index, value in enumerate(values + [False]):
        if value and start is None:
            start = index
        elif not value and start is not None:
            candidate = (index - start, start, index - 1)
            if candidate[0] > best[0]:
                best = candidate
            start = None
    return best


def _line_candidates(mask: Any, axis: str) -> list[tuple[int, int, int, int]]:
    """Find long dark horizontal/vertical runs in a binary image mask."""
    height, width = mask.shape
    candidates: list[tuple[int, int, int, int]] = []
    def close_short_gaps(values: list[bool], maximum_gap: int) -> list[bool]:
        """Join tiny raster gaps caused by coloured traces crossing a frame."""
        result = list(values)
        index = 0
        while index < len(result):
            if result[index]:
                index += 1
                continue
            start = index
            while index < len(result) and not result[index]:
                index += 1
            gap = index - start
            if start > 0 and index < len(result) and gap <= maximum_gap:
                result[start:index] = [True] * gap
        return result
    if axis == "horizontal":
        for y in range(height):
            values = close_short_gaps(mask[y, :].tolist(), max(2, min(8, int(width * 0.01))))
            length, start, end = _longest_run(values)
            if length >= max(20, int(width * 0.35)):
                candidates.append((length, y, start, end))
    else:
        for x in range(width):
            values = close_short_gaps(mask[:, x].tolist(), max(2, min(8, int(height * 0.01))))
            length, start, end = _longest_run(values)
            if length >= max(20, int(height * 0.35)):
                candidates.append((length, x, start, end))
    return sorted(candidates, reverse=True)


def _choose_pair(
    candidates: list[tuple[int, int, int, int]],
    axis: str,
    image_size: int,
) -> tuple[tuple[int, int, int, int] | None, tuple[int, int, int, int] | None]:
    """Choose two frame sides with overlapping spans, if visible."""
    if not candidates:
        return None, None
    first = candidates[0]
    minimum_separation = max(12, int(image_size * 0.20))
    for second in candidates[1:]:
        if abs(first[1] - second[1]) < minimum_separation:
            continue
        overlap = max(0, min(first[3], second[3]) - max(first[2], second[2]) + 1)
        span = max(1, min(first[0], second[0]))
        if overlap / span >= 0.55:
            return (first, second) if first[1] < second[1] else (second, first)
    return first, None


def _cluster_count(values: list[int], threshold: int = 2) -> int:
    groups = 0
    active = False
    for value in values + [0]:
        if value >= threshold and not active:
            groups += 1
            active = True
        elif value < threshold:
            active = False
    return groups


def _major_tick_hint(values: list[int], band_height: int) -> int:
    """Estimate major ticks while filtering out thin text/trace fragments."""
    if not values:
        return 0
    # A major tick normally occupies a substantial part of the narrow sampling
    # band.  The adaptive threshold keeps labels and anti-aliased noise from
    # being counted as ticks on high resolution figures.
    threshold = max(4, int(max(1, band_height) * 0.4))
    count = _cluster_count(values, threshold=threshold)
    return count if count >= 2 else _cluster_count(values, threshold=max(2, threshold // 2))


def _tick_positions(values: list[int], threshold: int = 1) -> list[tuple[int, int, int]]:
    """Return (start, end, strength) clusters in a near-axis tick profile.

    The old detector sampled far enough into the label row that the glyphs in
    labels such as ``150000`` were counted as ticks.  A profile taken just
    outside the frame contains the actual tick strokes and is much more stable
    across export sizes.
    """
    positions: list[tuple[int, int, int]] = []
    start: int | None = None
    for index, value in enumerate(values + [0]):
        if value >= threshold and start is None:
            start = index
        elif value < threshold and start is not None:
            end = index - 1
            positions.append((start, end, max(values[start : end + 1], default=0)))
            start = None
    return positions


def _tick_summary(
    mask: Any,
    axis_start: int,
    axis_end: int,
    fixed_coord: int,
    axis: str,
    outward_depth: int,
) -> tuple[int, int, list[float], float | None, float | None]:
    """Estimate major/minor ticks from the short strip immediately outside a frame.

    ``major`` is the number of long/regular ticks.  ``minor`` is the median
    number of short ticks between adjacent major ticks.  When the image is too
    small to distinguish lengths, the function reports all detected ticks as
    major and leaves minor at zero; the multimodal model can then refine it.
    """
    height, width = mask.shape
    depth = max(1, min(int(outward_depth), 12))
    if axis == "x":
        # Skip the anti-aliased frame row.  Text labels begin farther away.
        start = min(height, fixed_coord + 1)
        stop = min(height, start + depth)
        profile = mask[start:stop, max(0, axis_start) : min(width, axis_end + 1)]
    else:
        start = max(0, fixed_coord - depth)
        stop = max(0, fixed_coord)
        profile = mask[max(0, axis_start) : min(height, axis_end + 1), start:stop]
        # The Y-axis profile is sampled along rows, so transpose the same way
        # as the X profile before summing.
        profile = profile.T
    if profile.size == 0:
        return 0, 0, [], None, None
    values = profile.sum(axis=0).astype(int).tolist()
    clusters = _tick_positions(values, threshold=1)
    if not clusters:
        return 0, 0, [], None, None
    centers = [round((left + right) / 2, 6) for left, right, _ in clusters]
    strengths = [strength for _, _, strength in clusters]
    # A long tick normally reaches several pixels into the outward strip. If
    # all strokes are one pixel after rasterisation, regularity cannot tell
    # major and minor apart reliably, so do not invent minor ticks.
    # Major marks occupy most of the sampled strip; minor marks are usually
    # about half as long.  A low threshold classifies both as major and loses
    # the minor-length measurement, especially on a high-resolution image.
    strong_threshold = max(2, int(round(depth * 0.65)))
    major = [center for center, strength in zip(centers, strengths) if strength >= strong_threshold]
    if len(major) < 2:
        return len(clusters), 0, centers, float(median(strengths)), None
    minor_counts: list[int] = []
    for left, right in zip(major, major[1:]):
        interior = sum(left < center < right for center in centers)
        minor_counts.append(interior)
    minor = round(sorted(minor_counts)[len(minor_counts) // 2]) if minor_counts else 0
    major_strengths = [strength for center, strength in zip(centers, strengths) if center in major]
    minor_strengths = [
        strength for center, strength in zip(centers, strengths) if center not in major
    ]
    return (
        len(major),
        max(0, minor),
        centers,
        float(median(major_strengths)) if major_strengths else None,
        float(median(minor_strengths)) if minor_strengths else None,
    )


def _nonempty_run(values: list[bool]) -> int:
    longest = 0
    current = 0
    for value in values + [False]:
        if value:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def _geometry_hints(image: Any) -> dict[str, Any]:
    """Extract scale-independent layout hints from a mostly white figure."""
    import numpy as np

    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    gray = (0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2])
    mask = gray < 120
    height, width = mask.shape
    horizontal = _line_candidates(mask, "horizontal")
    vertical = _line_candidates(mask, "vertical")
    top_line, bottom_line = _choose_pair(horizontal, "horizontal", height)
    left_line, right_line = _choose_pair(vertical, "vertical", width)

    # ``_choose_pair`` returns the only candidate as its first item.  For a
    # conventional Cartesian plot that candidate is usually the *bottom*
    # x-axis (the top/right frame is often intentionally hidden).  Treating
    # it as ``top_line`` used to make every one-sided reference reopen with a
    # spurious top frame and shifted layer geometry.  Use the candidate's
    # position to assign the visible side while retaining the two-sided case
    # handled above.  The same rule applies to a single vertical y-axis.
    if top_line is not None and bottom_line is None:
        if top_line[1] >= height * 0.55:
            bottom_line, top_line = top_line, None
    if left_line is not None and right_line is None:
        if left_line[1] >= width * 0.55:
            right_line, left_line = left_line, None
    # Bar/scatter panels often have no uninterrupted horizontal baseline:
    # filled bars, brackets, and labels break it into short runs.  In that
    # case choose the farthest long vertical run that overlaps the y-axis
    # span as the right plot edge instead of treating an interior bar edge as
    # the frame.  This preserves the wide editable layer for grouped bars.
    if not horizontal and left_line is not None and vertical:
        plausible = []
        for candidate in vertical:
            if candidate[1] <= left_line[1] + width * 0.20:
                continue
            overlap = max(0, min(left_line[3], candidate[3]) - max(left_line[2], candidate[2]) + 1)
            span = max(1, min(left_line[0], candidate[0]))
            if overlap / span >= 0.45:
                plausible.append(candidate)
        if plausible:
            right_line = max(plausible, key=lambda item: item[1])
    elif horizontal and right_line is not None:
        horizontal_end = max(line[3] for line in horizontal)
        # A short vertical bar edge can be mistaken for the right frame even
        # when the uninterrupted baseline already gives the true extent.
        if right_line[1] < horizontal_end - width * 0.12:
            right_line = None

    def stroke_thickness(axis: str, candidate: tuple[int, int, int, int] | None) -> int | None:
        """Estimate a frame stroke's raster thickness near its longest run."""
        if not candidate:
            return None
        _, coordinate, start, end = candidate
        span = max(1, end - start + 1)
        threshold = max(4, int(span * 0.70))
        positions: list[int] = []
        if axis == "horizontal":
            for row in range(max(0, coordinate - 8), min(height, coordinate + 9)):
                length, run_start, run_end = _longest_run(mask[row, :].tolist())
                overlap = max(0, min(end, run_end) - max(start, run_start) + 1)
                if length >= threshold and overlap >= threshold:
                    positions.append(row)
        else:
            for column in range(max(0, coordinate - 8), min(width, coordinate + 9)):
                length, run_start, run_end = _longest_run(mask[:, column].tolist())
                overlap = max(0, min(end, run_end) - max(start, run_start) + 1)
                if length >= threshold and overlap >= threshold:
                    positions.append(column)
        return max(1, len(positions)) if positions else None

    horizontal_widths = [value for value in (stroke_thickness("horizontal", top_line), stroke_thickness("horizontal", bottom_line)) if value]
    vertical_widths = [value for value in (stroke_thickness("vertical", left_line), stroke_thickness("vertical", right_line)) if value]

    x_candidates = [line for line in (top_line, bottom_line) if line]
    y_candidates = [line for line in (left_line, right_line) if line]
    x1 = left_line[1] if left_line else min((line[2] for line in x_candidates), default=int(width * 0.15))
    x2 = right_line[1] if right_line else max((line[3] for line in x_candidates), default=int(width * 0.85))
    y1 = top_line[1] if top_line else min((line[2] for line in y_candidates), default=int(height * 0.12))
    y2 = bottom_line[1] if bottom_line else max((line[3] for line in y_candidates), default=int(height * 0.82))
    if left_line:
        y1 = min(y1, left_line[2])
        y2 = max(y2, left_line[3]) if not bottom_line else y2
    if right_line:
        y1 = min(y1, right_line[2])
        y2 = max(y2, right_line[3]) if not bottom_line else y2
    frame_width = max(1, x2 - x1)
    frame_height = max(1, y2 - y1)

    # Sample only the first few pixels beyond each frame side.  Sampling the
    # whole label row turns the digits in ``150000`` into dozens of fake ticks.
    # Keep enough of the near-axis strip to measure the actual stroke length.
    # A four-pixel strip was enough to count marks, but clipped long major
    # ticks and made the rendered lengths systematically too short.
    tick_depth = max(4, min(12, int(round(min(height, width) * 0.02))))
    (
        x_major,
        x_minor,
        x_tick_positions,
        x_major_length,
        x_minor_length,
    ) = _tick_summary(mask, x1, x2, y2, "x", tick_depth)
    (
        y_major,
        y_minor,
        y_tick_positions,
        y_major_length,
        y_minor_length,
    ) = _tick_summary(mask, y1, y2, x1, "y", tick_depth)
    # These bands are still used for text-size estimation, but never for tick
    # counting because they include labels and sometimes the data trace.
    bottom_band = mask[min(height, y2) : min(height, y2 + max(8, int(height * 0.035))), :]
    left_band = mask[:, max(0, x1 - max(8, int(width * 0.012))) : max(0, x1)]
    legacy_x_profile = bottom_band.sum(axis=0).astype(int).tolist() if bottom_band.size else []
    legacy_y_band = left_band[max(0, y1) : min(height, y2 + 1), :]
    legacy_y_profile = legacy_y_band.sum(axis=1).astype(int).tolist() if legacy_y_band.size else []
    legacy_x_major = _major_tick_hint(legacy_x_profile, bottom_band.shape[0] if bottom_band.size else 0)
    legacy_y_major = _major_tick_hint(legacy_y_profile, left_band.shape[1] if left_band.size else 0)
    # The broad profile is useful when a rasterised reference contains both
    # major and minor ticks, but it is rejected when label glyphs inflate the
    # count.  A sensible major count is normally in the 2..12 range.
    if 2 <= legacy_x_major <= 12 and len(x_tick_positions) >= legacy_x_major:
        x_major = legacy_x_major
    if 2 <= legacy_y_major <= 12 and len(y_tick_positions) >= legacy_y_major:
        y_major = legacy_y_major
    x_minor = max(0, round((len(x_tick_positions) - x_major) / max(1, x_major - 1)))
    y_minor = max(0, round((len(y_tick_positions) - y_major) / max(1, y_major - 1)))
    bottom_text = mask[min(height, y2 + 4) :, max(0, x1 - 4) : min(width, x2 + 4)]
    left_text = mask[max(0, y1 - 4) : min(height, y2 + 4), : max(0, x1 - 4)]
    text_height = max(
        _nonempty_run(bottom_text.any(axis=1).tolist()) if bottom_text.size else 0,
        _nonempty_run(left_text.any(axis=0).tolist()) if left_text.size else 0,
    )
    # Tick numbers form a broad row below the frame. Thin ticks and a short
    # axis title occupy few pixels per row; exclude them before measuring the
    # glyph height. This remains a model-correctable hint for simple 2D plots.
    tick_text_height = _nonempty_run(
        (bottom_text.sum(axis=1) >= max(8, frame_width * 0.04)).tolist()
    ) if bottom_text.size else 0

    frame = {
        "left": round(x1 / width * 100, 2),
        "top": round(y1 / height * 100, 2),
        "right": round((width - 1 - x2) / width * 100, 2),
        "bottom": round((height - 1 - y2) / height * 100, 2),
        "width_px": frame_width,
        "height_px": frame_height,
        "aspect_ratio": round(frame_width / frame_height, 4),
    }
    sides = {
        "top": bool(top_line),
        "right": bool(right_line),
        "bottom": bool(bottom_line or horizontal),
        "left": bool(left_line or vertical),
    }
    return {
        "plot_frame": frame,
        "frame_sides": sides,
        "page_aspect_ratio": round(width / height, 4),
        "x_major_tick_count_hint": x_major,
        "x_minor_tick_count_hint": x_minor,
        "y_major_tick_count_hint": y_major,
        "y_minor_tick_count_hint": y_minor,
        "x_tick_positions_hint": x_tick_positions,
        "y_tick_positions_hint": y_tick_positions,
        "x_major_tick_length_px_hint": x_major_length,
        "x_minor_tick_length_px_hint": x_minor_length,
        "y_major_tick_length_px_hint": y_major_length,
        "y_minor_tick_length_px_hint": y_minor_length,
        "x_frame_line_width_px_hint": round(float(median(horizontal_widths)), 2) if horizontal_widths else None,
        "y_frame_line_width_px_hint": round(float(median(vertical_widths)), 2) if vertical_widths else None,
        "estimated_text_height_px": text_height,
        "estimated_text_height_ratio": round(text_height / frame_height, 4),
        "tick_label_height_px": tick_text_height,
        "tick_label_height_ratio": round(tick_text_height / frame_height, 6) if tick_text_height >= 3 else None,
        "detection_confidence": round(
            min(0.99, 0.35 + 0.15 * sum(bool(value) for value in sides.values())), 2
        ),
    }


def inspect_reference(path: str | Path, user_notes: str = "") -> dict[str, Any]:
    image_path = resolve_input(path, IMAGE_SUFFIXES)
    try:
        from PIL import Image

        with Image.open(image_path) as image:
            width, height = image.size
            mode = image.mode
            geometry = _geometry_hints(image)
            palette: list[str] = []
            try:
                quantized = image.convert("RGB").resize((64, 64)).quantize(colors=8)
                rgb_palette = quantized.convert("RGB").getcolors(maxcolors=256) or []
                for _, color in sorted(rgb_palette, reverse=True):
                    hex_color = "#%02X%02X%02X" % color
                    if hex_color not in palette and hex_color not in {"#FFFFFF", "#000000"}:
                        palette.append(hex_color)
            except Exception:
                palette = []
    except ImportError as exc:
        raise InputValidationError("Pillow is required to inspect reference images.") from exc
    except Exception as exc:  # pragma: no cover - Pillow supplies format-specific errors
        raise InputValidationError(f"Could not read reference image: {exc}") from exc

    return {
        "file": str(image_path),
        "sha256": sha256_file(image_path),
        "image": {
            "width": width,
            "height": height,
            "mode": mode,
            "aspect_ratio": round(width / max(1, height), 4),
            "palette": palette[:6],
            "geometry_hints": geometry,
        },
        "user_notes": user_notes,
        # Geometry is measurable from a screenshot, but scientific meaning is
        # deliberately kept as a model-led contract.  A renderer must not
        # turn this placeholder into an assertion about the paper's analysis.
        "analysis_version": "0.3.1",
        "analysis_status": "geometry_and_scientific_contract_requires_model_interpretation",
        "reference_spec": {
            "graph_family": None,
            "graph_family_hint": None,
            "data_model": None,
            "style": {
                "page_aspect_ratio": geometry["page_aspect_ratio"],
                "plot_frame": geometry["plot_frame"],
                "frame_sides": geometry["frame_sides"],
                "estimated_text_height_ratio": geometry["estimated_text_height_ratio"],
                "tick_label_height_ratio": geometry["tick_label_height_ratio"],
                "base_font_pt": 12,
                "x_major_tick_count_hint": geometry["x_major_tick_count_hint"],
                "x_minor_tick_count_hint": geometry["x_minor_tick_count_hint"],
                "y_major_tick_count_hint": geometry["y_major_tick_count_hint"],
                "y_minor_tick_count_hint": geometry["y_minor_tick_count_hint"],
                "x_tick_positions_hint": geometry["x_tick_positions_hint"],
                "y_tick_positions_hint": geometry["y_tick_positions_hint"],
                "x_major_tick_length_px_hint": geometry["x_major_tick_length_px_hint"],
                "x_minor_tick_length_px_hint": geometry["x_minor_tick_length_px_hint"],
                "y_major_tick_length_px_hint": geometry["y_major_tick_length_px_hint"],
                "y_minor_tick_length_px_hint": geometry["y_minor_tick_length_px_hint"],
                "x_frame_line_width_px_hint": geometry["x_frame_line_width_px_hint"],
                "y_frame_line_width_px_hint": geometry["y_frame_line_width_px_hint"],
            },
            "axes": {
                "x": {
                    "major_tick_count_hint": geometry["x_major_tick_count_hint"],
                    "minor_tick_count_hint": geometry["x_minor_tick_count_hint"],
                    "major_tick_length_px_hint": geometry["x_major_tick_length_px_hint"],
                    "minor_tick_length_px_hint": geometry["x_minor_tick_length_px_hint"],
                },
                "y": {
                    "major_tick_count_hint": geometry["y_major_tick_count_hint"],
                    "minor_tick_count_hint": geometry["y_minor_tick_count_hint"],
                    "major_tick_length_px_hint": geometry["y_major_tick_length_px_hint"],
                    "minor_tick_length_px_hint": geometry["y_minor_tick_length_px_hint"],
                },
            },
            "legend": {},
            "annotations": {},
            "confidence": 0.0,
            "geometry_confidence": geometry["detection_confidence"],
            "scientific_context": {
                "contract_version": "0.3.1",
                "reference": {
                    "research_question": None,
                    "plot_intent": None,
                    "axes": {
                        "x": {
                            "role": None,
                            "unit": None,
                            "scale_type": "unknown",
                            "transform": None,
                            "range": None,
                            "tick_label_format": None,
                        },
                        "y": {
                            "role": None,
                            "unit": None,
                            "scale_type": "unknown",
                            "transform": None,
                            "range": None,
                            "tick_label_format": None,
                        },
                    },
                    "encodings": [],
                    "mark_roles": [],
                    "series_roles": [],
                    "line_semantics": {
                        "has_line": None,
                        "relationship_to_markers": "unknown",
                        "candidate_fit_models": [],
                        "fit_parameters": {},
                        "fit_is_reproducible_from_markers": None,
                        "fit_should_be_regenerated_after_replacement": True,
                    },
                    "uncertainty": {
                        "present": None,
                        "representation": None,
                        "source": None,
                    },
                    "annotations": [],
                    "typography": {
                        "subscripts": [],
                        "superscripts": [],
                        "math_text_runs": [],
                    },
                    "data_layout_plan": {
                        "book_name": "Reference Data",
                        "max_books": 1,
                        "preferred_sheet_count": "1-2",
                        "preferred_xy_layout": "one shared X column plus multiple Y columns",
                        "preferred_fit_layout": "fit/derived columns beside their source marker columns when possible",
                        "preserve_raw_and_derived_roles": True,
                    },
                    "placeholder_policy": {
                        "status": "synthetic_visual_reference",
                        "pixel_estimates_allowed": True,
                        "source_description": "visible marks and geometry from the reference image",
                        "is_original_research_data": False,
                        "requires_user_replacement": True,
                    },
                    "evidence": [],
                    "unresolved": [],
                },
            },
        },
        "model_instruction": (
            "Visually inspect the actual image and any caption. Geometry detection does not understand science. "
            "This is a screenshot-only workflow: never request or claim access to private research data. "
            "Pixels may be sampled to estimate visual placeholder coordinates and to recover visible labels, "
            "but those estimates must be labelled synthetic reference placeholders rather than recovered "
            "measurements. First complete scientific_context.reference "
            "as a researcher's reading of the figure: state the likely research question and what each axis/unit, "
            "scale transform, colour, marker, line, panel, and error mark encodes. Distinguish raw observations "
            "or replicates from summaries, fitted curves, guide lines, and censoring marks. When markers and a "
            "smooth line coexist, treat the markers as the editable source observations and record an explicit, "
            "interpretable candidate fit (for example linear, logistic 4PL/5PL, exponential, Gaussian, or "
            "polynomial) with its evidence and unresolved alternatives; do not invent an independent sequence of "
            "line values and do not claim to know the paper's original algorithm. The line must be regenerated "
            "from the marker data after the user replaces placeholders. For each annotation record observed text, "
            "meaning, evidence, and transfer_rule (recalculate, retain contextual label, omit, or ask). Preserve "
            "subscripts, superscripts, Greek letters, and other math text as structured text runs, not only as a "
            "flattened legend string. A peak label might be an apex coordinate, centroid, species assignment, or "
            "derived mass; do not equate them. Stars/brackets need tests and comparisons; error bars need a stated "
            "role (SD, SEM, CI, range, or unknown). Read the image evidence, then pass scientific_context to "
            "infer_plot_spec with the research question, data_mapping, experimental_unit, representation, mark "
            "roles, fit candidates, evidence, and unresolved_questions. Prefer the user's research purpose and "
            "data validity when the reference cannot be transferred. Use the image as a visual reference and "
            "complete reference_spec. Extract every reproducible visual parameter: graph family, "
            "axis labels and approximate limits, major/minor tick increments, frame sides, "
            "tick direction and length, page aspect ratio, plot-frame margins as percentages, "
            "font family and approximate point sizes relative to the canvas, title offsets, "
            "line width, colors, legend placement, and whether opposite frame axes carry tick "
            "marks. For minor ticks, count the short marks between two adjacent major ticks; "
            "do not mistake digit strokes in tick labels for ticks. For a peak value callout, "
            "describe it semantically while using screenshot pixels only as an approximate visual anchor: use "
            "an annotation with role=peak_marker, anchor_x tied to the nearest peak in the generated/reference "
            "placeholder data, "
            "a horizontal line span expressed as a fraction of the X range, and a label with "
            "align=center placed above that line. If the screenshot visibly contains a number, preserve its "
            "displayed text and mark any pixel-derived coordinate as a synthetic placeholder; after replacement, "
            "the user's data or an explicitly requested calculation takes precedence. Preserve geometry_hints as a starting "
            "point, but correct them if the image contains panels or an inset. Use 12 pt tick "
            "labels as the physical size anchor; measure tick glyph height / plot-frame height "
            "and preserve relative text sizes. Page millimeters are derived from this ratio, "
            "not from screenshot pixel size or DPI."
        ),
    }

