"""Verify native Origin save, reopen, and editable data persistence.

The input project is copied before it is opened. The probe changes one numeric
worksheet cell in the copy, saves it, reopens it, and checks that the changed
value and at least one graph page persist. It never modifies the input file.
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import shutil
import sys
from pathlib import Path


def _error(message: str, error_type: str = "error") -> int:
    print(json.dumps({"status": "error", "error_type": error_type, "error": message}, indent=2))
    return 2


def run(project_path: Path, work_dir: Path) -> dict[str, object]:
    if platform.system().lower() != "windows":
        raise RuntimeError("native Origin automation requires Windows")
    try:
        import originpro as op
    except Exception as exc:  # pragma: no cover - depends on the local Origin installation
        raise RuntimeError(f"originpro is unavailable: {exc}") from exc

    work_dir.mkdir(parents=True, exist_ok=True)
    source_copy = work_dir / f"{project_path.stem}.roundtrip-input.opju"
    copy_path = work_dir / f"{project_path.stem}.roundtrip.opju"
    shutil.copy2(project_path, source_copy)
    op.set_show(False)
    try:
        if not op.open(str(source_copy), readonly=False, asksave=False):
            raise RuntimeError(f"Origin could not open {source_copy}")
        books = list(op.project.pages("w"))
        if not books:
            raise RuntimeError("the project contains no worksheet book")
        sheet = next(iter(books[0]), None)
        if sheet is None:
            raise RuntimeError("the first worksheet book contains no worksheet")
        selected: tuple[int, list[object], int, float] | None = None
        for col in range(sheet.cols):
            values = list(sheet.to_list(col))
            for row, value in enumerate(values):
                try:
                    numeric = float(value)
                except (TypeError, ValueError):
                    continue
                if math.isfinite(numeric):
                    selected = (col, values, row, numeric)
                    break
            if selected is not None:
                break
        if selected is None:
            raise RuntimeError("no numeric worksheet cell was available for the round-trip probe")
        col, values, row, before = selected
        after = before + (1.0 if before == 0 else abs(before) * 0.01)
        values[row] = after
        sheet.from_list(col, values)
        if not op.save(str(copy_path)):
            raise RuntimeError("Origin did not report a successful save")
        op.exit()

        op.set_show(False)
        if not op.open(str(copy_path), readonly=False, asksave=False):
            raise RuntimeError(f"Origin could not reopen {copy_path}")
        reopened_book = next(iter(op.project.pages("w")), None)
        if reopened_book is None:
            raise RuntimeError("the saved project has no worksheet book after reopen")
        reopened_sheet = next(iter(reopened_book), None)
        if reopened_sheet is None:
            raise RuntimeError("the saved project has no worksheet after reopen")
        persisted = float(reopened_sheet.to_list(col)[row])
        graph_pages = len(list(op.project.pages("g")))
        return {
            "status": "passed" if math.isclose(persisted, after, rel_tol=0, abs_tol=1e-12) and graph_pages else "failed",
            "project_copy": str(copy_path),
            "worksheet": reopened_sheet.name,
            "cell": {"row": row, "column": col, "before": before, "after": persisted},
            "save_reopen_persisted": math.isclose(persisted, after, rel_tol=0, abs_tol=1e-12),
            "graph_pages": graph_pages,
        }
    finally:
        try:
            op.exit()
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_path", type=Path, help="existing .opju project to copy and probe")
    parser.add_argument(
        "--work-dir",
        type=Path,
        help="directory for the copied project (default: <project>/roundtrip-check)",
    )
    args = parser.parse_args(argv)
    project_path = args.project_path.expanduser().resolve()
    if not project_path.is_file():
        return _error(f"project does not exist: {project_path}", "missing_project")
    work_dir = (args.work_dir or project_path.parent / "roundtrip-check").expanduser().resolve()
    try:
        result = run(project_path, work_dir)
    except Exception as exc:
        return _error(str(exc), type(exc).__name__)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
