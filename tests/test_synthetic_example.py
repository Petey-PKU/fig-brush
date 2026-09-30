"""Checks for the public, synthetic-only example."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from mcp_server.template import validate_template


EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "synthetic"


def test_synthetic_reference_and_template_are_self_contained() -> None:
    reference = EXAMPLE / "reference.png"
    spec_path = EXAMPLE / "template_spec.json"
    assert reference.is_file()
    assert spec_path.is_file()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    validate_template(spec)
    assert spec["canvas"] == {"width_px": 1200, "height_px": 760, "font_reference_px": 17, "font_anchor_pt": 10}
    assert spec["example"]["not_research_data"] is True
    assert spec["example"]["version"] == "0.3.2"
    assert spec["example"]["author"] == "Petey Yu"
    assert len(spec["panels"][0]["series"]) == 2
    assert "not research data" in spec["scientific_context"]["description"]


def test_run_example_works_from_an_arbitrary_working_directory(workspace_tmp: Path) -> None:
    output = workspace_tmp / "synthetic-output"
    command = [sys.executable, str(EXAMPLE / "run_example.py"), "--output-dir", str(output)]
    result = subprocess.run(command, cwd=workspace_tmp, text=True, capture_output=True, timeout=60)
    assert result.returncode == 0, result.stderr
    prepared = json.loads((output / "template_spec.json").read_text(encoding="utf-8"))
    assert prepared["data_policy"]["original_data_recovered"] is False
    assert (output / "data_manifest.json").is_file()
    assert (output / "替换数据说明.md").is_file()
