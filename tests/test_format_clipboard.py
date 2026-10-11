from __future__ import annotations

import pytest

from origin_bridge.format_clipboard import normalize_format_scope, stage_format_clipboard


class _Graph:
    name = "ReferenceGraph"

    def __init__(self):
        self.activated = False

    def activate(self):
        self.activated = True


class _Origin:
    def __init__(self):
        self.graph = _Graph()
        self.scripts: list[str] = []

    def find_graph(self, name=""):
        assert name in {"", "ReferenceGraph"}
        return self.graph

    def lt_exec(self, script):
        self.scripts.append(script)
        return True


def test_normalize_format_scope_supports_aliases():
    assert normalize_format_scope("all styles") == ("all_styles", "FmtsCopyAllStyles")
    assert normalize_format_scope("colourmap") == ("colormap", "FmtsCopyColormap")


def test_normalize_format_scope_rejects_unknown_scope():
    with pytest.raises(ValueError, match="unsupported format clipboard scope"):
        normalize_format_scope("everything")


def test_stage_format_clipboard_runs_origin_native_section(workspace_tmp, monkeypatch):
    import origin_bridge.format_clipboard as module

    source = workspace_tmp / "reference.opju"
    source.write_bytes(b"origin")
    origin = _Origin()
    monkeypatch.setattr(module, "open_origin_project", lambda *_args, **_kwargs: origin)
    result = stage_format_clipboard(str(source), scope="fonts")
    assert result["status"] == "staged"
    assert result["scope"] == "fonts"
    assert result["origin_section"] == "FmtsCopyFonts"
    assert result["clipboard"] == "origin_format"
    assert result["saved"] is False
    assert result["origin_closed"] is False
    assert origin.graph.activated is True
    assert origin.scripts == ["run.section(,FmtsCopyFonts);"]
    assert any("session-local" in warning for warning in result["warnings"])


def test_stage_format_clipboard_requires_origin_project(workspace_tmp):
    image = workspace_tmp / "reference.png"
    image.write_bytes(b"not an Origin project")
    with pytest.raises(ValueError, match="must be an .opju or .opj"):
        stage_format_clipboard(str(image))
