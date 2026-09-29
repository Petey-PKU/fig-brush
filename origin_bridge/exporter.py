from __future__ import annotations

from pathlib import Path
from typing import Any

from .connection import OriginBridgeError, OriginSession, open_origin_project
from .graph_builder import build_graph, build_reference_template
from .workbook import choose_table


def render_project(
    data_path: str,
    plot_spec: dict[str, Any],
    output_dir: str | Path,
    table_name: str | None = None,
    show_origin: bool = False,
) -> dict[str, Any]:
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    project_path = output / "result.opju"
    frame = choose_table(data_path, table_name)
    family = plot_spec.get("graph_family", "unknown")
    with OriginSession(show=show_origin) as op:
        _, graph, _ = build_graph(op, frame, plot_spec, workbook_name="Source Data")
        save = getattr(op, "save", None)
        if not callable(save):
            raise OriginBridgeError("originpro does not expose project.save().")
        if not save(str(project_path)):
            raise OriginBridgeError(f"Origin failed to save the project: {project_path}")
        previews: dict[str, str] = {}
        for extension in plot_spec.get("output", {}).get("preview_formats", ["png", "svg"]):
            if extension not in {"png", "svg", "pdf"}:
                continue
            preview_path = output / f"preview.{extension}"
            save_fig = getattr(graph, "save_fig", None)
            if not callable(save_fig):
                continue
            preview_width = int(plot_spec.get("style", {}).get("preview_width_px", 1600))
            result = save_fig(str(preview_path), type=extension, replace=True, width=preview_width)
            if result:
                previews[extension] = str(preview_path)
    return {
        "status": "rendered",
        "graph_family": family,
        "project": str(project_path),
        "previews": previews,
    }


def render_reference_template(spec: dict[str, Any], output_dir: str | Path, show_origin: bool = False) -> dict[str, Any]:
    """Create an editable OPJU from screenshot-derived placeholder data."""
    from mcp_server.template import validate_template
    validate_template(spec)
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    project_path = output / "result.opju"
    previous_signature = None
    if project_path.is_file():
        stat = project_path.stat()
        previous_signature = (stat.st_size, stat.st_mtime_ns)
    previews: dict[str, str] = {}
    with OriginSession(show=show_origin) as op:
        graphs, _ = build_reference_template(op, spec)
        save = getattr(op, "save", None)
        saved = callable(save) and save(str(project_path))
        # Some Origin builds return False after a successful COM save when the
        # active project is replaced.  Accept that case only when the file was
        # actually created or changed; otherwise an old, locked OPJU would be
        # reported as a successful render and silently ship stale graphics.
        current_signature = None
        if project_path.is_file():
            stat = project_path.stat()
            current_signature = (stat.st_size, stat.st_mtime_ns)
        changed = current_signature is not None and current_signature != previous_signature
        if not saved and not changed:
            raise OriginBridgeError(f"Origin failed to create a fresh project: {project_path}")
        graph = graphs[0] if graphs else None
        for extension in spec.get("output", {}).get("preview_formats", ["png", "svg"]):
            if extension not in {"png", "svg", "pdf"} or graph is None:
                continue
            target = output / f"preview.{extension}"
            save_fig = getattr(graph, "save_fig", None)
            if callable(save_fig) and save_fig(str(target), type=extension, replace=True, width=int(spec.get("output", {}).get("preview_width_px", 1600))):
                previews[extension] = str(target)
    return {"status": "rendered", "project": str(project_path), "previews": previews,
            "panels": [panel["id"] for panel in spec["panels"]]}


def export_preview(project_path: str, output_dir: str | Path, formats: list[str] | None = None) -> dict[str, Any]:
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    formats = formats or ["png", "svg"]
    op = open_origin_project(project_path, show=False)
    graphs = getattr(op, "graph_list", None)
    if not callable(graphs):
        raise OriginBridgeError("originpro does not expose graph_list().")
    graph_pages = list(graphs("p"))
    if not graph_pages:
        raise OriginBridgeError("The Origin project contains no graph page to export.")
    graph = graph_pages[0]
    previews: dict[str, str] = {}
    for extension in formats:
        if extension not in {"png", "svg", "pdf"}:
            continue
        target = output / f"preview.{extension}"
        result = graph.save_fig(str(target), type=extension, replace=True, width=1600)
        if result:
            previews[extension] = str(target)
    return {"status": "exported", "previews": previews}
