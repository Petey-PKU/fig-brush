"""Geometry-first placement for Origin text labels.

Origin labels are not positioned by their visible text baseline.  They have an
invisible rectangle, and Origin exposes its measured ``dx``/``dy`` dimensions
after the text (including rich text, superscripts, and line breaks) is set.
This module keeps the placement calculation independent from graph creation so
callers can choose data or page coordinates explicitly and avoid hand-tuned
offsets for each label.

The functions deliberately accept a small Origin-like protocol instead of
opening Origin themselves.  This makes the geometry testable without COM and
lets callers pass ``originpro.graph.Label`` objects directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import re
from typing import Any, Literal


HAnchor = Literal["left", "center", "right"]
VAnchor = Literal["top", "middle", "bottom"]
CoordinateSpace = Literal["data", "page"]
ParagraphAlign = Literal["left", "center", "right"]


# Origin's rich-text parser is much more reliable than a raster-sized font
# approximation for scientific labels.  OCR/model output often contains the
# Unicode superscript/subscript glyphs directly, while hand-authored specs
# use Origin's ``\\+(...)``/``\\-(...)`` notation.  Keep the conversion small
# and conservative: only already-superscripted/subscripted Unicode runs are
# rewritten, so ordinary labels such as ``T-DM1`` keep their baseline text.
_SUPERSCRIPT = {
    "⁺": "+", "⁻": "-", "⁰": "0", "¹": "1", "²": "2", "³": "3",
    "⁴": "4", "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9",
    "ⁿ": "n", "ᵃ": "a", "ᵇ": "b", "ᶜ": "c",
    "ᵈ": "d", "ᵉ": "e", "ᶠ": "f", "ᵍ": "g", "ʰ": "h", "ⁱ": "i",
    "ʲ": "j", "ᵏ": "k", "ˡ": "l", "ᵐ": "m", "ⁿ": "n", "ᵒ": "o",
    "ᵖ": "p", "ʳ": "r", "ˢ": "s", "ᵗ": "t", "ᵘ": "u", "ᵛ": "v",
    "ʷ": "w", "ˣ": "x", "ʸ": "y", "ᶻ": "z",
}
_SUBSCRIPT = {
    "₊": "+", "₋": "-", "₀": "0", "₁": "1", "₂": "2", "₃": "3",
    "₄": "4", "₅": "5", "₆": "6", "₇": "7", "₈": "8", "₉": "9",
    "ₐ": "a", "ₑ": "e", "ₕ": "h", "ᵢ": "i",
    "ⱼ": "j", "ₖ": "k", "ₗ": "l", "ₘ": "m", "ₙ": "n", "ₒ": "o",
    "ₚ": "p", "ᵣ": "r", "ₛ": "s", "ₜ": "t", "ᵤ": "u", "ᵥ": "v",
    "ₓ": "x",
}


def normalize_origin_markup(value: Any) -> str:
    """Return text that Origin can render with scientific rich text.

    Explicit Origin markup is preserved.  Unicode superscript/subscript runs
    are converted to one markup run each, which keeps label width and baseline
    geometry consistent across Origin installations and export resolutions.
    Newlines are retained because Origin uses them for multi-line labels.
    """

    text = str(value if value is not None else "")
    if not text:
        return text
    # Parenthesized Unicode runs are a common OCR representation of a
    # subscript/superscript group (for example ``₍EE₎``).  Consume the group
    # first so its parentheses become Origin's markup delimiters instead of
    # nested literal glyphs.
    def _group(match: re.Match[str], table: dict[str, str], prefix: str) -> str:
        body = "".join(table.get(char, char) for char in match.group(1))
        return prefix + "(" + body + ")"

    text = re.sub(r"⁽([^⁾]*)⁾", lambda match: _group(match, _SUPERSCRIPT, "\\+"), text)
    text = re.sub(r"₍([^₎]*)₎", lambda match: _group(match, _SUBSCRIPT, "\\-"), text)
    out: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        mapping = _SUPERSCRIPT if char in _SUPERSCRIPT else _SUBSCRIPT if char in _SUBSCRIPT else None
        if mapping is None:
            out.append(char)
            index += 1
            continue
        table = _SUPERSCRIPT if char in _SUPERSCRIPT else _SUBSCRIPT
        run: list[str] = []
        while index < len(text) and text[index] in table:
            run.append(table[text[index]])
            index += 1
        prefix = "\\+" if table is _SUPERSCRIPT else "\\-"
        out.append(prefix + "(" + "".join(run) + ")")
    return "".join(out)


def text_value(spec: dict[str, Any] | None, *, default: Any = "") -> str:
    """Read the structured text field used by labels and annotations.

    ``text_markup``/``markup`` are explicit rich-text fields.  Plain ``text``
    still receives conservative Unicode normalization so an OCR result can be
    used without a second manual pass.
    """

    item = spec or {}
    value = item.get("text_markup", item.get("markup", item.get("text", default)))
    return normalize_origin_markup(value)


@dataclass(frozen=True)
class AxisGeometry:
    """One plotted axis, used to convert data extents to page fractions."""

    minimum: float
    maximum: float
    log: bool = False

    def _transform(self, value: float) -> float:
        if self.log:
            if value <= 0:
                raise ValueError("log axis values must be positive")
            return math.log10(value)
        return value

    def fraction(self, value: float) -> float:
        lo = self._transform(float(self.minimum))
        hi = self._transform(float(self.maximum))
        if hi == lo:
            raise ValueError("axis range must not be zero")
        return (self._transform(float(value)) - lo) / (hi - lo)


@dataclass(frozen=True)
class FrameGeometry:
    """Page-fraction frame and axes used by a page-attached label.

    ``left/top/width/height`` are fractions of the full graph page.  The
    frame is the plotted layer, so a data extent can be measured in data
    units and converted to the correct physical text size even on log axes.
    """

    left: float
    top: float
    width: float
    height: float
    x_axis: AxisGeometry
    y_axis: AxisGeometry


@dataclass(frozen=True)
class TextLayout:
    """Requested text anchor and style.

    ``x`` and ``y`` are data coordinates when ``coordinate_space='data'`` and
    page fractions (origin at top-left) when ``coordinate_space='page'``.
    """

    x: float
    y: float
    coordinate_space: CoordinateSpace = "data"
    h_anchor: HAnchor = "left"
    v_anchor: VAnchor = "top"
    paragraph_align: ParagraphAlign | None = None
    rotation: float | None = None
    font_size_pt: float | None = None


@dataclass
class LayoutResult:
    """What was applied and the measured object geometry."""

    coordinate_space: CoordinateSpace
    attach: int | None = None
    x1: float | None = None
    y1: float | None = None
    measured_dx: float | None = None
    measured_dy: float | None = None
    page_width: float | None = None
    page_height: float | None = None
    applied: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _get_float(label: Any, name: str) -> float:
    getter = getattr(label, "get_float", None)
    if callable(getter):
        return float(getter(name))
    value = getattr(label, name)
    return float(value)


def _set_float(label: Any, name: str, value: float) -> None:
    setter = getattr(label, "set_float", None)
    if callable(setter):
        setter(name, float(value))
    else:
        setattr(label, name, float(value))


def _set_int(label: Any, name: str, value: int) -> None:
    setter = getattr(label, "set_int", None)
    if callable(setter):
        setter(name, int(value))
    else:
        setattr(label, name, int(value))


def _set_str(label: Any, name: str, value: str) -> None:
    setter = getattr(label, "set_str", None)
    if callable(setter):
        setter(name, value)
    else:
        setattr(label, name, value)


def _set_attach(label: Any, attach: int, result: LayoutResult) -> None:
    _set_int(label, "attach", attach)
    result.attach = attach
    result.applied.append(f"attach={attach}")


def _anchor_x(x: float, width: float, anchor: HAnchor) -> float:
    return {"left": x, "center": x - width / 2.0, "right": x - width}[anchor]


def _anchor_y(y: float, height: float, anchor: VAnchor) -> float:
    # Origin's y1 is the top edge of the invisible rectangle.  Data y grows
    # upward, so the lower edge is numerically larger in data coordinates.
    return {"top": y, "middle": y + height / 2.0, "bottom": y + height}[anchor]


def _anchor_page_y(y: float, height: float, anchor: VAnchor) -> float:
    """Top-left page coordinates grow downward (unlike data y)."""

    return {"top": y, "middle": y - height / 2.0, "bottom": y - height}[anchor]


def _apply_style(label: Any, layout: TextLayout, result: LayoutResult) -> None:
    if layout.font_size_pt is not None:
        try:
            _set_float(label, "fsize", float(layout.font_size_pt))
            result.applied.append("fsize")
        except (AttributeError, TypeError, ValueError, RuntimeError, OSError) as exc:
            result.warnings.append(f"Origin label font size unavailable: {exc}")
    if layout.rotation is not None:
        try:
            _set_float(label, "rotate", float(layout.rotation))
            result.applied.append("rotate")
        except (AttributeError, TypeError, ValueError, RuntimeError, OSError) as exc:
            result.warnings.append(f"Origin label rotation unavailable: {exc}")
    if layout.paragraph_align is None:
        return
    align_value = {"left": 0, "center": 1, "right": 2}[layout.paragraph_align]
    # ``justify`` is the LabTalk GObject property behind label -j.  A few
    # Origin versions expose the equivalent as ``align``; keep the fallback
    # explicit and report it, rather than changing the user's rich text.
    last_error: Exception | None = None
    for prop, value in (("justify", align_value), ("align", layout.paragraph_align)):
        try:
            if isinstance(value, int):
                _set_int(label, prop, value)
            else:
                _set_str(label, prop, value)
            result.applied.append(f"paragraph_align={layout.paragraph_align}")
            return
        except (AttributeError, TypeError, ValueError, RuntimeError, OSError) as exc:
            last_error = exc
    result.warnings.append(f"Origin label paragraph alignment unavailable: {last_error}")


def _measure(label: Any, result: LayoutResult) -> tuple[float, float, float, float]:
    """Read Origin's rendered center and invisible-rectangle dimensions."""

    cx = _get_float(label, "x")
    cy = _get_float(label, "y")
    dx = _get_float(label, "dx")
    dy = _get_float(label, "dy")
    if not all(math.isfinite(v) for v in (cx, cy, dx, dy)) or dx < 0 or dy < 0:
        raise ValueError("Origin returned invalid label x/y/dx/dy geometry")
    result.measured_dx = dx
    result.measured_dy = dy
    return cx, cy, dx, dy


def _data_position(label: Any, layout: TextLayout, result: LayoutResult) -> LayoutResult:
    _set_attach(label, 2, result)  # axes/data coordinates
    _cx, _cy, dx, dy = _measure(label, result)
    x1 = _anchor_x(layout.x, dx, layout.h_anchor)
    y1 = _anchor_y(layout.y, dy, layout.v_anchor)
    _set_float(label, "x1", x1)
    _set_float(label, "y1", y1)
    result.x1, result.y1 = x1, y1
    result.applied.extend(["x1", "y1"])
    return result


def _page_size_from_data(cx: float, cy: float, dx: float, dy: float, frame: FrameGeometry) -> tuple[float, float]:
    """Convert a measured data-unit rectangle to page fractions."""

    x0 = frame.x_axis.fraction(cx - dx / 2.0)
    x1 = frame.x_axis.fraction(cx + dx / 2.0)
    # Axis fraction 0 is the bottom for y; page fraction 0 is the top.
    y0 = frame.y_axis.fraction(cy - dy / 2.0)
    y1 = frame.y_axis.fraction(cy + dy / 2.0)
    return abs(x1 - x0) * frame.width, abs(y1 - y0) * frame.height


def _page_position(
    label: Any,
    layout: TextLayout,
    result: LayoutResult,
    *,
    frame: FrameGeometry | None,
    size_fraction: tuple[float, float] | None,
) -> LayoutResult:
    # Measure in axes coordinates before switching to page attachment.  This
    # preserves the rendered dimensions for rich text and multiple lines.
    _set_attach(label, 2, result)
    cx, cy, dx, dy = _measure(label, result)
    if size_fraction is not None:
        page_width, page_height = (float(size_fraction[0]), float(size_fraction[1]))
    elif frame is not None:
        page_width, page_height = _page_size_from_data(cx, cy, dx, dy, frame)
    else:
        raise ValueError("page text placement requires frame geometry or size_fraction")
    if page_width < 0 or page_height < 0:
        raise ValueError("page label dimensions must be non-negative")
    left = _anchor_x(layout.x, page_width, layout.h_anchor)
    top = _anchor_page_y(layout.y, page_height, layout.v_anchor)
    _set_attach(label, 1, result)  # page fractions, top-left origin
    _set_float(label, "x1", left)
    _set_float(label, "y1", top)
    result.x1, result.y1 = left, top
    result.page_width, result.page_height = page_width, page_height
    result.applied.extend(["x1", "y1"])
    return result


def layout_text_label(
    label: Any,
    layout: TextLayout,
    *,
    frame: FrameGeometry | None = None,
    size_fraction: tuple[float, float] | None = None,
) -> LayoutResult:
    """Apply style and geometry to an existing Origin label.

    ``coordinate_space='data'`` requires no frame and writes ``attach=2``
    plus data-unit ``x1/y1``.  ``coordinate_space='page'`` writes
    ``attach=1`` plus page-fraction ``x1/y1`` and requires either
    ``size_fraction`` or a measured ``FrameGeometry``.  Errors are explicit so
    a caller cannot silently fall back to guessed offsets.
    """

    if layout.coordinate_space not in ("data", "page"):
        raise ValueError("coordinate_space must be 'data' or 'page'")
    if layout.h_anchor not in ("left", "center", "right"):
        raise ValueError("h_anchor must be 'left', 'center', or 'right'")
    if layout.v_anchor not in ("top", "middle", "bottom"):
        raise ValueError("v_anchor must be 'top', 'middle', or 'bottom'")
    if layout.paragraph_align is not None and layout.paragraph_align not in ("left", "center", "right"):
        raise ValueError("paragraph_align must be 'left', 'center', or 'right'")
    result = LayoutResult(coordinate_space=layout.coordinate_space)
    _apply_style(label, layout, result)
    if layout.coordinate_space == "data":
        return _data_position(label, layout, result)
    return _page_position(label, layout, result, frame=frame, size_fraction=size_fraction)


__all__ = [
    "AxisGeometry",
    "FrameGeometry",
    "LayoutResult",
    "TextLayout",
    "layout_text_label",
    "normalize_origin_markup",
    "text_value",
]
