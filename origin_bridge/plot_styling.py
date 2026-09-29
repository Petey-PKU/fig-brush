"""Small, explicit mappings for plot-level outlines.

Origin uses different LabTalk switches for column borders and symbol edges.
Keeping this mapping separate from graph construction makes a screenshot
reader's ``border_width`` and ``border_color`` fields reusable across plot
families without silently relying on a template default.
"""
from __future__ import annotations

from typing import Any


def _color_expression(value: Any) -> str:
    text = str(value).strip()
    if text.startswith("#") and len(text) == 7:
        red, green, blue = (int(text[offset:offset + 2], 16) for offset in (1, 3, 5))
        return f"color({red},{green},{blue})"
    return text


def apply_plot_border(plot: Any, style: dict[str, Any] | None, *, kind: str = "scatter") -> list[str]:
    """Apply an explicitly requested data-object outline.

    Returns the switches that were attempted.  A missing style field leaves
    Origin's native default untouched; this matters for figures whose symbols
    are intentionally open or whose bars have no outline.
    """
    style = style or {}
    width = style.get("border_width", style.get("outline_width"))
    color = style.get("border_color", style.get("outline_color"))
    line_style = style.get("border_style", style.get("outline_style"))
    if width is None and color is None and line_style is None:
        return []
    commands: list[str] = []
    is_column = kind in {"column", "grouped_column", "bar"}
    if width is not None:
        commands.append(f"{'-pbw' if is_column else '-kh'} {float(width)}")
    if color is not None:
        commands.append(f"{'-pbc' if is_column else '-c'} {_color_expression(color)}")
    if line_style is not None and is_column:
        commands.append(f"-pbs {int(line_style)}")
    if not commands:
        return []
    try:
        plot.set_cmd(*commands)
    except (AttributeError, TypeError, ValueError, RuntimeError, OSError):
        return []
    return commands


__all__ = ["apply_plot_border"]
