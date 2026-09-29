from pathlib import Path

import origin_bridge.connection as origin_connection
from mcp_server.server import render_origin_project_tool
from mcp_server.verification import validate_plot_spec, verify_origin_project


def _spec():
    return {
        "schema_version": "1.0",
        "graph_family": "scatter",
        "data_mapping": {"x": "X", "y": "Y"},
        "statistics": {},
        "axes": {},
        "style": {},
        "output": {"project_format": "opju", "preview_formats": ["png", "svg"]},
    }


def test_plot_spec_schema_is_valid():
    assert validate_plot_spec(_spec()) == []


def test_missing_project_is_reported(workspace_tmp: Path):
    report = verify_origin_project(str(workspace_tmp / "missing.opju"), _spec())

    assert report["status"] == "failed"
    assert any(check["name"] == "project_exists" and not check["passed"] for check in report["checks"])


def test_render_refuses_to_fake_project_without_origin(workspace_tmp: Path, monkeypatch):
    data = workspace_tmp / "data.csv"
    data.write_text("X,Y\n1,2\n2,4\n", encoding="utf-8")

    def unavailable_origin():
        raise origin_connection.OriginUnavailableError("Origin unavailable for test")

    # Keep this test deterministic even on a developer machine that has Origin.
    monkeypatch.setattr(origin_connection, "_import_originpro", unavailable_origin)

    result = render_origin_project_tool(str(data), _spec(), str(workspace_tmp / "output"))

    # The important behavior is an explicit failure rather than a fabricated .opju file.
    assert result["status"] == "error"
    assert result.get("error_type") == "origin_unavailable"
