"""Probe the installed fig-brush MCP server through the real stdio protocol.

This check deliberately exercises initialize, tools/list, and one harmless
tool call. It does not start Origin or read a user dataset, so it is suitable
for release smoke tests on machines that only need screenshot preparation.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


EXPECTED_TOOLS = {
    "inspect_reference_tool",
    "inspect_dataset_tool",
    "infer_plot_spec_tool",
    "render_origin_project_tool",
    "verify_origin_project_tool",
    "export_origin_preview_tool",
    "origin_status_tool",
    "prepare_reference_template_tool",
    "compare_reference_tool",
    "verify_reference_template_tool",
}


async def probe(plugin_root: Path, python: str) -> dict[str, object]:
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    server = StdioServerParameters(
        command=python,
        args=["-m", "fig_brush"],
        cwd=str(plugin_root),
        env=environment,
    )
    async with stdio_client(server) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            listed = await session.list_tools()
            names = {tool.name for tool in listed.tools}
            missing = sorted(EXPECTED_TOOLS - names)
            unexpected = sorted(names - EXPECTED_TOOLS)
            if missing:
                raise RuntimeError(f"MCP tools/list is missing: {', '.join(missing)}")
            status = await session.call_tool("origin_status_tool", arguments={})
            if getattr(status, "isError", False):
                raise RuntimeError("origin_status_tool returned an MCP error")
            return {
                "status": "ok",
                "tool_count": len(names),
                "tools": sorted(names),
                "unexpected_tools": unexpected,
                "origin_status_called": True,
            }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--plugin-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="installed plugin directory (default: this checkout)",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python executable containing the installed fig-brush dependencies",
    )
    args = parser.parse_args(argv)
    try:
        result = asyncio.run(probe(args.plugin_root.resolve(), args.python))
    except Exception as exc:
        result = {"status": "error", "error_type": type(exc).__name__, "error": str(exc)}
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
