from __future__ import annotations

import json
import types
from pathlib import Path

from scripts import doctor


ROOT = Path(__file__).resolve().parents[1]


def test_doctor_reports_required_checks_and_json_shape() -> None:
    report = doctor.run_doctor(
        ROOT,
        system_name=lambda: "Linux",
        importer=lambda name: (_ for _ in ()).throw(ImportError(name))
        if name == "originpro"
        else __import__(name),
    )

    assert report.screenshot_ready is True
    assert report.exit_code == 0
    payload = report.as_dict()
    assert payload["plugin_root"] == str(ROOT)
    assert payload["screenshot_ready"] is True
    assert payload["origin_ready"] is False
    assert any(item["name"] == "originpro import" for item in payload["checks"])


def test_doctor_missing_root_is_a_required_failure(workspace_tmp: Path) -> None:
    report = doctor.run_doctor(workspace_tmp / "missing", system_name=lambda: "Linux")
    assert report.screenshot_ready is False
    assert report.exit_code == 1
    assert report.checks[0].status == "error"


def test_origin_check_only_inspects_api_without_starting_origin() -> None:
    calls: list[str] = []

    def forbidden(*args, **kwargs):
        calls.append("origin-started")
        raise AssertionError("doctor must not invoke Origin project methods")

    fake_originpro = types.ModuleType("originpro")
    fake_originpro.__version__ = "test"
    fake_originpro.new = forbidden
    fake_originpro.open = forbidden

    platform_check, package_check, api_check, ready = doctor._check_origin(
        system_name=lambda: "Windows",
        importer=lambda name: fake_originpro,
    )

    assert platform_check.status == "ok"
    assert package_check.status == "ok"
    assert api_check.status == "ok"
    assert ready is True
    assert calls == []


def test_doctor_json_cli_is_machine_readable(capsys) -> None:
    exit_code = doctor.main(["--json", "--plugin-root", str(ROOT)])
    output = capsys.readouterr().out
    payload = json.loads(output)
    assert exit_code == payload["exit_code"] == 0
    assert payload["plugin_root"] == str(ROOT)
