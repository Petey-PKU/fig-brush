from __future__ import annotations

from pathlib import Path
from typing import Any

from .connection import OriginBridgeError, OriginSession, open_origin_project
from .graph_builder import build_graph, build_reference_template
from .workbook import choose_table


def _save_graph_template(graph: Any, target: str | Path) -> bool:
    """Save an Origin graph page as a native ``.otpu`` template.

    ``originpro`` does not expose a stable Python method for graph-template
    export across Origin releases.  The documented LabTalk ``save -TX`` command
    is therefore used through the graph page.  The first form supplies the
    page name (required by current Origin releases); the second uses the
    active-page ``-tx`` form as a compatibility fallback.  The file is removed
    before saving so a stale template can never be reported as a successful
    export.
    """
    destination = Path(target).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        destination.unlink(missing_ok=True)
    except OSError:
        return False
    lt_exec = getattr(graph, "lt_exec", None)
    if not callable(lt_exec):
        return False
    page_name = getattr(graph, "name", None)
    path_text = str(destination).replace("\\", "/")
    commands: list[str] = []
    if page_name:
        # Origin's documented ``-TX`` form requires the graph window name as
        # an explicit positional argument.  On Origin 2023, quoting the short
        # name or using ``-t`` can return without an error while producing no
        # file, so keep the short name unquoted and let the full path carry
        # quoting instead.
        safe_page_name = str(page_name).strip().replace('"', '')
        if safe_page_name:
            commands.append(f'save -TX {safe_page_name} "{path_text}";')
    # ``-tx`` saves the active graph page and determines the template type
    # from the supplied extension, so it is the safest fallback when an
    # Origin build does not expose a usable page short name through originpro.
    commands.append(f'save -tx "{path_text}";')
    for command in commands:
        try:
            lt_exec(command)
        except Exception:
            continue
        try:
            if destination.is_file() and destination.stat().st_size > 0:
                return True
        except OSError:
            continue
    return False


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
    """Create a demo OPJU and native style templates from a reference image.

    The OPJU is useful for previewing the reconstruction with placeholder
    values.  The ``.otpu`` output is the format-brush artifact: it stores the
    graph page and plot styling without requiring the user's scientific data.
    """
    from mcp_server.template import build_style_manifest, validate_template
    from mcp_server.paths import write_json
    validate_template(spec)
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    # Keep the data-free style sidecar available for direct refresh calls too;
    # those calls receive a saved TemplateSpec and do not pass through
    # ``prepare_template`` (which normally writes this manifest).
    style_manifest_path = output / "style_manifest.json"
    write_json(style_manifest_path, build_style_manifest(spec))
    project_path = output / "result.opju"
    previous_signature = None
    if project_path.is_file():
        stat = project_path.stat()
        previous_signature = (stat.st_size, stat.st_mtime_ns)
    previews: dict[str, str] = {}
    style_templates: dict[str, str] = {}
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
        # Export one graph template per page.  Origin graph templates are
        # page-scoped, so a multi-panel reference keeps each panel's measured
        # frame, axes, annotations, and plot styles independently reusable.
        panel_ids = [str(panel["id"]) for panel in spec["panels"]]
        for index, graph in enumerate(graphs):
            panel_id = panel_ids[index] if index < len(panel_ids) else f"Panel{index + 1}"
            filename = "style_template.otpu" if len(graphs) == 1 else f"{panel_id}_style.otpu"
            target = output / filename
            if _save_graph_template(graph, target):
                style_templates[panel_id] = str(target)
    result: dict[str, Any] = {
        "status": "rendered",
        "project": str(project_path),
        "previews": previews,
        "panels": [panel["id"] for panel in spec["panels"]],
        "style_templates": style_templates,
        "style_manifest": str(style_manifest_path),
        "style_template_status": "saved" if style_templates else "unavailable",
    }
    if len(style_templates) == 1:
        result["style_template"] = next(iter(style_templates.values()))
    elif not style_templates:
        result["style_template_error"] = (
            "Origin created the preview project but did not save a native .otpu "
            "graph template. Check Origin startup/UFF configuration and rerun."
        )
    return result


def export_preview(project_path: str, output_dir: str | Path, formats: list[str] | None = None) -> dict[str, Any]:
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    formats = formats or ["png", "svg"]
    op = open_origin_project(project_path, show=False)
    try:
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
    finally:
        # Opening a project for preview export starts a separate Origin COM
        # session. Close it deterministically so repeated exports do not leave
        # a hidden process holding the UFF or project file open.
        exit_origin = getattr(op, "exit", None)
        if callable(exit_origin):
            try:
                exit_origin()
            except Exception:
                pass
