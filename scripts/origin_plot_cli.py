from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from mcp_server.data_inspector import inspect_dataset
from mcp_server.inference import infer_plot_spec
from mcp_server.reference import inspect_reference
from mcp_server.server import render_origin_project_tool
from mcp_server.server import apply_active_format, apply_format_tool, stage_format_clipboard
from mcp_server.server import (
    compare_reference_tool,
    format_brush_tool,
    prepare_reference_template_tool,
    verify_reference_template_tool,
)
from origin_bridge.connection import origin_status


def main() -> int:
    # Windows consoles often default to a GBK code page.  Scientific labels
    # commonly contain μ, superscripts, and Greek symbols; keep the CLI
    # machine-readable instead of failing after a successful Origin render.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    parser = argparse.ArgumentParser(description="Offline helpers for fig-brush")
    subparsers = parser.add_subparsers(dest="command", required=True)

    data_parser = subparsers.add_parser("inspect-data")
    data_parser.add_argument("path")

    reference_parser = subparsers.add_parser("inspect-reference")
    reference_parser.add_argument("path")
    reference_parser.add_argument("--notes", default="")

    brush_parser = subparsers.add_parser(
        "format-brush",
        help="analyze a reference image and write reusable Origin format parameters",
    )
    brush_parser.add_argument("reference_path")
    brush_parser.add_argument(
        "output_dir",
        nargs="?",
        default=None,
        help="output folder (default: <reference-stem>_format_brush beside the image)",
    )
    brush_parser.add_argument("--notes", default="")
    brush_parser.add_argument(
        "--template-spec-json",
        help="optional completed TemplateSpec; enables the existing native template export",
    )
    brush_parser.add_argument(
        "--render-origin",
        action="store_true",
        help="with --template-spec-json, also export native .otpu/.opju files",
    )

    infer_parser = subparsers.add_parser("infer")
    infer_parser.add_argument("data_path")
    infer_parser.add_argument("--reference-json")
    infer_parser.add_argument("--notes", default="")

    render_parser = subparsers.add_parser("render")
    render_parser.add_argument("data_path")
    render_parser.add_argument("plot_spec_json")
    render_parser.add_argument("output_dir")

    template_parser = subparsers.add_parser("prepare-template")
    template_parser.add_argument("reference_path")
    template_parser.add_argument("template_spec_json")
    template_parser.add_argument("output_dir")
    template_parser.add_argument("--render-origin", action="store_true",
                                 help="start Origin and write the native .otpu/.opju artifacts")

    compare_parser = subparsers.add_parser("compare-reference")
    compare_parser.add_argument("reference_path")
    compare_parser.add_argument("preview_path")
    compare_parser.add_argument("output_dir")

    verify_parser = subparsers.add_parser("verify-template")
    verify_parser.add_argument("output_dir")

    subparsers.add_parser("origin-status")

    apply_parser = subparsers.add_parser(
        "apply-format",
        help="apply format_parameters.json to an existing Origin project",
    )
    apply_parser.add_argument("project_path")
    apply_parser.add_argument("format_parameters_path")
    apply_parser.add_argument(
        "output_path",
        nargs="?",
        default=None,
        help="output OPJU (default: <project-stem>_formatted.opju)",
    )
    apply_parser.add_argument("--graph-name", default=None)
    apply_parser.add_argument("--show-origin", action="store_true")

    active_parser = subparsers.add_parser(
        "apply-active-format",
        help="apply format_parameters.json to the graph currently active in Origin",
    )
    active_parser.add_argument("format_parameters_path")
    active_parser.add_argument("--graph-name", default=None)
    active_parser.add_argument("--layer-index", type=int, default=None)
    active_parser.add_argument("--preview-path", default=None)

    clipboard_parser = subparsers.add_parser(
        "stage-format-clipboard",
        help="stage a reference OPJU's native Origin format clipboard",
    )
    clipboard_parser.add_argument("reference_project_path")
    clipboard_parser.add_argument("--graph-name", default=None)
    clipboard_parser.add_argument("--scope", default="all")
    clipboard_parser.add_argument("--hide-origin", action="store_true")
    args = parser.parse_args()

    if args.command == "format-brush":
        spec = None
        if args.template_spec_json:
            spec = json.loads(Path(args.template_spec_json).read_text(encoding="utf-8"))
        result = format_brush_tool(
            args.reference_path,
            args.output_dir,
            user_notes=args.notes,
            template_spec=spec,
            render_origin=args.render_origin,
        )
    elif args.command == "inspect-data":
        result = inspect_dataset(args.path)
    elif args.command == "inspect-reference":
        result = inspect_reference(args.path, args.notes)
    elif args.command == "infer":
        inventory = inspect_dataset(args.data_path)
        reference = None
        if args.reference_json:
            reference = json.loads(Path(args.reference_json).read_text(encoding="utf-8"))
        result = infer_plot_spec(reference, inventory, args.notes)
    elif args.command == "render":
        spec = json.loads(Path(args.plot_spec_json).read_text(encoding="utf-8"))
        result = render_origin_project_tool(args.data_path, spec, args.output_dir)
    elif args.command == "prepare-template":
        spec = json.loads(Path(args.template_spec_json).read_text(encoding="utf-8"))
        result = prepare_reference_template_tool(
            args.reference_path, spec, args.output_dir, render_origin=args.render_origin
        )
    elif args.command == "compare-reference":
        result = compare_reference_tool(args.reference_path, args.preview_path, args.output_dir)
    elif args.command == "verify-template":
        result = verify_reference_template_tool(args.output_dir)
    elif args.command == "apply-format":
        result = apply_format_tool(
            args.project_path,
            args.format_parameters_path,
            args.output_path,
            graph_name=args.graph_name,
            show_origin=args.show_origin,
        )
    elif args.command == "apply-active-format":
        result = apply_active_format(
            args.format_parameters_path,
            graph_name=args.graph_name,
            layer_index=args.layer_index,
            preview_path=args.preview_path,
        )
    elif args.command == "stage-format-clipboard":
        result = stage_format_clipboard(
            args.reference_project_path,
            graph_name=args.graph_name,
            scope=args.scope,
            show_origin=not args.hide_origin,
        )
    else:
        result = origin_status()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
