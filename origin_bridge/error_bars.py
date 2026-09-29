"""Origin 2D error-bar formatting primitives.

The command names in this module are documented Origin LabTalk options.  The
single format-tree property is used only for the GUI's ``Through Symbol``
checkbox, for which Origin documents the ``ErrorBar2D.ThroughSymbol`` tree
member rather than a ``set`` option.
"""
from __future__ import annotations

from numbers import Real
from typing import Any


_DIRECTION_CODES = {
    "both": 0,
    "plus": 1,
    "positive": 1,
    "pos": 1,
    "minus": 2,
    "negative": 2,
    "neg": 2,
}


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"error-bar {field} must be numeric")
    number = float(value)
    if number < 0:
        raise ValueError(f"error-bar {field} must be nonnegative")
    return number


def _direction(value: Any, field: str) -> int:
    if isinstance(value, str):
        key = value.strip().lower().replace("+", "plus").replace("-", "minus")
        if key not in _DIRECTION_CODES:
            raise ValueError(f"error-bar {field} must be both, plus/positive, or minus/negative")
        return _DIRECTION_CODES[key]
    if isinstance(value, bool) or not isinstance(value, int) or value not in (0, 1, 2):
        raise ValueError(f"error-bar {field} must be both, plus/positive, or minus/negative")
    return int(value)


def _direction_from_sides(style: dict[str, Any], field: str) -> int | None:
    if "direction" in style:
        if "plus" in style or "minus" in style:
            raise ValueError(f"error-bar {field} cannot combine direction with plus/minus")
        return _direction(style["direction"], field)
    has_plus, has_minus = "plus" in style, "minus" in style
    if not (has_plus or has_minus):
        return None
    plus = bool(style.get("plus", False))
    minus = bool(style.get("minus", False))
    if not plus and not minus:
        raise ValueError(f"error-bar {field} cannot disable both plus and minus with a single bar")
    return 0 if plus and minus else 1 if plus else 2


def _color_expression(value: Any) -> str:
    """Return the documented LabTalk RGB expression for ``-cr``."""
    if isinstance(value, str):
        text = value.strip()
        if text.lower().startswith("color(") and text.endswith(")"):
            return text
        if text.startswith("#"):
            text = text[1:]
        if len(text) == 6:
            try:
                red, green, blue = (int(text[offset:offset + 2], 16) for offset in (0, 2, 4))
            except ValueError as exc:
                raise ValueError("error-bar color must be #RRGGBB or color(r,g,b)") from exc
            return f"color({red},{green},{blue})"
        raise ValueError("error-bar color must be #RRGGBB or color(r,g,b)")
    if isinstance(value, (tuple, list)) and len(value) == 3:
        channels = []
        for channel in value:
            if isinstance(channel, bool) or not isinstance(channel, Real) or not 0 <= float(channel) <= 255:
                raise ValueError("error-bar RGB channels must be between 0 and 255")
            channels.append(str(int(channel)))
        return f"color({','.join(channels)})"
    raise ValueError("error-bar color must be #RRGGBB or an RGB triplet")


def _axis_style(plot: Any, axis: str, style: dict[str, Any], applied: list[str], commands: list[list[str]]) -> None:
    """Apply one documented X/Y direction group to an Origin Plot object."""
    if not isinstance(style, dict):
        raise ValueError(f"error-bar {axis} style must be an object")
    options: list[str] = []
    direction = _direction_from_sides(style, axis)
    if direction is not None:
        options.append(f"-erd{axis} {direction}")
        applied.append(f"{axis}.direction")
    if "line_width" in style:
        options.append(f"-erw {_number(style['line_width'], axis + '.line_width'):g}")
        applied.append(f"{axis}.line_width")
    if "cap_width" in style:
        options.append(f"-erwc {_number(style['cap_width'], axis + '.cap_width'):g}")
        applied.append(f"{axis}.cap_width")
    if "color" in style:
        options.append(f"-cr {_color_expression(style['color'])}")
        applied.append(f"{axis}.color")
    if options:
        # originpro.Plot.set_cmd expands this into a documented LabTalk
        # ``set range ...`` command without requiring COM calls here.
        plot.set_cmd(*options)
        commands.append(options)
    if "symbol_through" in style:
        value = style["symbol_through"]
        if not isinstance(value, bool):
            raise ValueError(f"error-bar {axis}.symbol_through must be boolean")
        # Origin C's 2D error-bar format tree calls this member
        # ErrorBar2D.ThroughSymbol. originpro exposes graph object numeric
        # members through the corresponding lowercase dotted property path.
        plot.set_int("errorbar2d.throughsymbol", int(value))
        applied.append(f"{axis}.symbol_through")


def apply_error_bar_style(plot: Any, style: dict[str, Any] | None) -> list[str]:
    """Apply documented Origin error-bar styles to an originpro ``Plot``.

    ``style`` may contain ``y`` and/or ``x`` dictionaries.  A flat dictionary
    is treated as a Y-error style for backwards-friendly single-axis use.  The
    returned list names fields that were emitted.  LabTalk direction codes are
    ``0=both``, ``1=plus``, and ``2=minus``.
    """
    if not style:
        return []
    if not isinstance(style, dict):
        raise ValueError("error-bar style must be an object")
    if "x" in style or "y" in style:
        unknown = set(style) - {"x", "y"}
        if unknown:
            raise ValueError(f"error-bar style has unsupported fields: {sorted(unknown)}")
        axis_styles = [(axis, style[axis]) for axis in ("y", "x") if axis in style]
    else:
        axis_styles = [("y", style)]
    applied: list[str] = []
    commands: list[list[str]] = []
    for axis, axis_style in axis_styles:
        _axis_style(plot, axis, axis_style, applied, commands)
    # Useful for callers that inspect the fake/real object after the call;
    # originpro itself ignores this private attribute.
    try:
        plot._last_error_bar_commands = commands
    except Exception:
        pass
    return applied


__all__ = ["apply_error_bar_style"]
