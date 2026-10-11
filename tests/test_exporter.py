from pathlib import Path

from origin_bridge.exporter import _save_graph_template


class _FakeGraph:
    name = "Panel1"

    def __init__(self, target: Path):
        self.target = target
        self.commands: list[str] = []

    def lt_exec(self, command: str) -> None:
        self.commands.append(command)
        self.target.write_bytes(b"Origin graph template")


def test_save_graph_template_uses_labtalk_and_removes_stale_file(workspace_tmp: Path):
    target = workspace_tmp / "style_template.otpu"
    target.write_bytes(b"stale")
    graph = _FakeGraph(target)

    assert _save_graph_template(graph, target) is True
    assert target.read_bytes() == b"Origin graph template"
    assert graph.commands[0].startswith('save -TX Panel1')
    assert str(target.resolve()).replace("\\", "/") in graph.commands[0]


def test_save_graph_template_reports_missing_labtalk_bridge(workspace_tmp: Path):
    target = workspace_tmp / "style_template.otpu"

    assert _save_graph_template(object(), target) is False
    assert not target.exists()
