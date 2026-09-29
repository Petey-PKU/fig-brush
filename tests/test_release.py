from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

from scripts.package_plugin import build_package
from scripts.validate_release import scan_release_tree, validate_metadata


ROOT = Path(__file__).resolve().parents[1]


def test_release_metadata_uses_fig_brush_contract() -> None:
    errors = validate_metadata(ROOT)
    assert not errors, "release metadata errors: " + "; ".join(errors)


def test_package_allowlist_excludes_private_and_unknown_assets(workspace_tmp: Path) -> None:
    tmp_path = workspace_tmp
    root = tmp_path / "plugin"
    (root / ".codex-plugin").mkdir(parents=True)
    (root / ".codex-plugin" / "plugin.json").write_text(
        json.dumps({"name": "fig-brush", "version": "0.3.1"}), encoding="utf-8"
    )
    (root / "README.md").write_text("public", encoding="utf-8")
    (root / "fig_brush").mkdir()
    (root / "fig_brush" / "__init__.py").write_text("", encoding="utf-8")
    (root / "examples" / "synthetic").mkdir(parents=True)
    (root / "examples" / "synthetic" / "reference.png").write_bytes(b"synthetic")
    (root / "examples" / "synthetic" / "other.png").write_bytes(b"private")
    (root / "examples" / "synthetic" / "values.csv").write_text("x,y\n1,2\n", encoding="utf-8")
    (root / "private").mkdir()
    (root / "private" / "research.csv").write_text("secret", encoding="utf-8")
    (root / "untracked.png").write_bytes(b"private")
    (root / "untracked.csv").write_text("private", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "fixture.txt").write_text("not shipped", encoding="utf-8")

    archive, checksum = build_package(root, tmp_path / "dist")
    with zipfile.ZipFile(archive) as bundle:
        members = set(bundle.namelist())
    assert "fig-brush/README.md" in members
    assert "fig-brush/fig_brush/__init__.py" in members
    assert "fig-brush/examples/synthetic/reference.png" in members
    assert "fig-brush/examples/synthetic/values.csv" in members
    assert "fig-brush/examples/synthetic/other.png" not in members
    assert all("private" not in member for member in members)
    assert all(not member.endswith((".csv", ".png")) or "examples/synthetic/" in member for member in members)
    expected = hashlib.sha256(archive.read_bytes()).hexdigest()
    assert checksum.read_text(encoding="ascii") == f"{expected}  {archive.name}\n"


def test_release_scan_reports_private_paths_secrets_and_stale_names(workspace_tmp: Path) -> None:
    tmp_path = workspace_tmp
    docs = tmp_path / "docs"
    docs.mkdir()
    old_name = "origin" + "-research" + "-plot"
    (docs / "leak.md").write_text(
        f"C:\\Users\\researcher\\private\\data.csv\n{old_name}\napi_key=not-a-real-but-long-token\n",
        encoding="utf-8",
    )
    (tmp_path / "untracked.png").write_bytes(b"private")
    (tmp_path / "untracked.opju").write_bytes(b"private")
    findings = scan_release_tree(tmp_path)
    assert any("personal absolute path" in item for item in findings)
    assert any("possible secret/token" in item for item in findings)
    assert any("stale project name" in item for item in findings)
    assert any("untracked.png: forbidden release asset" in item for item in findings)
    assert any("untracked.opju: forbidden release asset" in item for item in findings)
