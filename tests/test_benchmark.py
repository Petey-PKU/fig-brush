from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from mcp_server.benchmark import build_report, record_review, run_case
from mcp_server.paths import InputValidationError, write_json


def _spec() -> dict:
    return {
        "schema_version": "2.0", "mode": "reference_template",
        "canvas": {"width_px": 80, "height_px": 60, "font_reference_px": 8, "font_anchor_pt": 10},
        "style": {"page_aspect_ratio": 4 / 3},
        "panels": [{"id": "Panel1", "frame_px": [8, 8, 72, 52], "axes": {
            "x": {"min": 0, "max": 10}, "y": {"min": 0, "max": 10}}, "series": [{
                "id": "Series1", "name": "Series 1", "kind": "line",
                "data": {"x": [0, 5, 10], "y": [0, 4, 2]}}]}],
        "output": {"preview_formats": ["png"]},
    }


def _fixture(tmp_path: Path, split: str = "development") -> tuple[Path, dict, Path]:
    image = tmp_path / "reference.png"
    Image.new("RGB", (80, 60), "white").save(image)
    spec = tmp_path / "case.json"
    write_json(spec, _spec())
    manifest = tmp_path / "manifest.json"
    payload = {"benchmark_version": "0.3", "cases": [{
        "case_id": "case1", "split": split, "reference": image.name,
        "image_sha256": __import__("hashlib").sha256(image.read_bytes()).hexdigest(),
    }]}
    write_json(manifest, payload)
    return manifest, payload["cases"][0], spec


def test_run_case_is_offline_and_pending_review(workspace_tmp: Path):
    manifest, case, spec = _fixture(workspace_tmp)
    result = run_case(manifest, case, spec, workspace_tmp / "attempts", model_version="test-model")
    assert result["overall_status"] == "pending_review"
    assert result["fidelity_claim"] is False
    assert result["checks"]["native"]["status"] == "not_run"
    attempt = workspace_tmp / "attempts" / "case1" / result["attempt_id"]
    assert (attempt / "IMMUTABLE_ATTEMPT").is_file()
    assert not (attempt / "result.opju").exists()
    assert (attempt / "prepared" / "template_spec.json").is_file()


def test_missing_and_unsupported_specs_never_pass(workspace_tmp: Path):
    manifest, case, spec = _fixture(workspace_tmp)
    missing = run_case(manifest, case, workspace_tmp / "does-not-exist.json", workspace_tmp / "attempts")
    assert missing["overall_status"] == "missing_spec"
    unsupported = workspace_tmp / "unsupported.json"
    write_json(unsupported, {"benchmark": {"status": "unsupported", "reason": "3D"}})
    marked = run_case(manifest, case, unsupported, workspace_tmp / "attempts")
    assert marked["overall_status"] == "unsupported"
    assert marked["fidelity_claim"] is False
    with pytest.raises(InputValidationError, match="cannot be recorded as pass"):
        record_review(workspace_tmp / "attempts" / "case1" / marked["attempt_id"], {"status": "pass"})


def test_heldout_requires_explicit_frozen_dev_and_regression(workspace_tmp: Path):
    manifest, case, spec = _fixture(workspace_tmp, "heldout_acceptance")
    with pytest.raises(InputValidationError, match="freeze"):
        run_case(manifest, case, spec, workspace_tmp / "attempts")
    freeze = workspace_tmp / "freeze.json"
    write_json(freeze, {"status": "frozen", "approved": True,
                        "development_status": "pass", "regression_status": "pass"})
    result = run_case(manifest, case, spec, workspace_tmp / "attempts", freeze_file=freeze)
    assert result["overall_status"] == "pending_review"


def test_record_is_written_outside_immutable_attempt_and_report_is_honest(workspace_tmp: Path):
    manifest, case, spec = _fixture(workspace_tmp)
    attempts = workspace_tmp / "attempts"
    result = run_case(manifest, case, spec, attempts)
    attempt = attempts / "case1" / result["attempt_id"]
    before = (attempt / "attempt.json").read_bytes()
    review = record_review(attempt, {"status": "major", "failure_category": ["legend_mapping"]}, reviewer="blind")
    assert Path(review["review"]).is_file()
    assert (attempt / "attempt.json").read_bytes() == before
    report = build_report(manifest, attempts)
    assert report["counts"] == {"major": 1}
    assert report["rows"][0]["native"]["status"] == "not_run"
    assert "not fidelity passes" in report["interpretation"]


def test_pass_requires_native_persistence_and_replacement_evidence(workspace_tmp: Path):
    manifest, case, spec = _fixture(workspace_tmp)
    attempts = workspace_tmp / "attempts"
    result = run_case(manifest, case, spec, attempts)
    attempt = attempts / "case1" / result["attempt_id"]
    with pytest.raises(InputValidationError, match="requires explicit evidence"):
        record_review(attempt, {"status": "pass"})
    review = record_review(attempt, {
        "status": "pass",
        "native_verification": "passed",
        "editable": {
            "save_reopen_persists": "pass",
            "replacement_updates_plot": True,
        },
    })
    assert Path(review["review"]).is_file()
    report = build_report(manifest, attempts)
    row = report["rows"][0]
    assert report["counts"] == {"pass": 1}
    assert row["native"]["status"] == "pass"
    assert row["save_reopen"]["status"] == "pass"
    assert row["data_replacement"]["status"] == "pass"


def test_report_rejects_review_attached_to_different_case(workspace_tmp: Path):
    manifest, case, spec = _fixture(workspace_tmp)
    attempts = workspace_tmp / "attempts"
    result = run_case(manifest, case, spec, attempts)
    attempt = attempts / "case1" / result["attempt_id"]
    review_dir = attempts / "reviews" / "case1"
    review_dir.mkdir(parents=True)
    write_json(review_dir / "forged.json", {
        "status": "pass", "attempt_id": result["attempt_id"],
        "case_id": "another-case", "split": "development",
        "native_verification": "passed",
        "editable": {"save_reopen_persists": "pass", "replacement_updates_plot": "pass"},
    })
    report = build_report(manifest, attempts)
    assert report["counts"] == {"pending_review": 1}
    assert report["rows"][0]["review_integrity"] == "not_recorded"
    assert report["rejected_reviews"][0]["reason"].startswith("Review case_id")


def test_report_uses_review_evidence_instead_of_stale_attempt_checks(workspace_tmp: Path):
    manifest, case, spec = _fixture(workspace_tmp)
    attempts = workspace_tmp / "attempts"
    result = run_case(manifest, case, spec, attempts)
    attempt = attempts / "case1" / result["attempt_id"]
    record_review(attempt, {
        "status": "minor",
        "native_verification": "passed",
        "editable": {"save_reopen_persists": "pass", "replacement_updates_plot": "not_run"},
    })
    report = build_report(manifest, attempts)
    row = report["rows"][0]
    assert row["native"]["status"] == "pass"
    assert row["save_reopen"]["status"] == "pass"
    assert row["data_replacement"]["status"] == "not_run"
