"""Run the synthetic fig-brush example without starting Origin by default."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


EXAMPLE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = EXAMPLE_ROOT.parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mcp_server.server import prepare_reference_template_tool  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare the fig-brush synthetic template.")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "outputs" / "synthetic")
    parser.add_argument(
        "--render-origin",
        action="store_true",
        help="After preparation, ask a local Origin installation to render the editable project.",
    )
    args = parser.parse_args()
    spec_path = EXAMPLE_ROOT / "template_spec.json"
    reference_path = EXAMPLE_ROOT / "reference.png"
    output_dir = args.output_dir.expanduser().resolve()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    result = prepare_reference_template_tool(
        str(reference_path),
        spec,
        str(output_dir),
        render_origin=args.render_origin,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0 if result.get("status") in {"prepared", "ok", "rendered"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
