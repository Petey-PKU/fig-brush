"""Offline benchmark runner for screenshot-template reconstruction.

The benchmark deliberately stops before Origin.  It records what was prepared
and leaves native checks, visual review, persistence, and data replacement to a
separate review record.  A prepared artifact is never treated as a faithful
reconstruction merely because files exist or a pixel score was reported.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import sys
from typing import Any, Iterable
import uuid

from .paths import InputValidationError, sha256_file, write_json
from .template import prepare_template


RUNNER_VERSION = "0.3.1"
REVIEW_STATUSES = {"pass", "minor", "major", "unsupported", "missing"}
_EVIDENCE_PASS = {"pass", "passed", "ok", "true"}
_EVIDENCE_NOT_RUN = {
    "not_run", "not run", "pending", "not_recorded", "not recorded", "unknown", ""
}
HELDOUT_SPLIT_RE = re.compile(r"heldout|holdout|acceptance", re.I)


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _attempt_id() -> str:
    return f"{_utc_stamp()}-{uuid.uuid4().hex[:10]}"


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise InputValidationError(f"JSON file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise InputValidationError(f"Invalid JSON in {path}: {exc}") from exc


def _resolve(manifest_path: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = manifest_path.parent / path
    return path.resolve()


def load_benchmark_manifest(path: str | Path) -> tuple[Path, dict[str, Any]]:
    manifest_path = Path(path).expanduser().resolve()
    payload = _read_json(manifest_path)
    if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list):
        raise InputValidationError("Benchmark manifest must contain a cases list.")
    seen: set[str] = set()
    for case in payload["cases"]:
        if not isinstance(case, dict) or not isinstance(case.get("case_id"), str):
            raise InputValidationError("Every benchmark case needs a case_id.")
        case_id = case["case_id"]
        if case_id in seen:
            raise InputValidationError(f"Duplicate benchmark case_id: {case_id}")
        seen.add(case_id)
        if not isinstance(case.get("split"), str) or not case["split"].strip():
            raise InputValidationError(f"{case_id} needs a nonempty split.")
        if not isinstance(case.get("reference"), str):
            raise InputValidationError(f"{case_id} needs a reference path.")
    return manifest_path, payload


def select_cases(manifest: dict[str, Any], case_id: str | None = None,
                 split: str | None = None) -> list[dict[str, Any]]:
    if bool(case_id) == bool(split):
        raise InputValidationError("Specify exactly one of case_id or split.")
    cases = manifest["cases"]
    if case_id:
        selected = [case for case in cases if case.get("case_id") == case_id]
        if not selected:
            raise InputValidationError(f"Unknown benchmark case: {case_id}")
        return selected
    selected = [case for case in cases if case.get("split") == split]
    if not selected:
        raise InputValidationError(f"No benchmark cases in split: {split}")
    return selected


def _plugin_version() -> str:
    root = Path(__file__).resolve().parents[1]
    try:
        payload = _read_json(root / ".codex-plugin" / "plugin.json")
        return str(payload.get("version", "unknown"))
    except (InputValidationError, OSError):
        return "unknown"


def _runtime_metadata(model_version: str = "", runtime_label: str = "") -> dict[str, Any]:
    return {
        "runner_version": RUNNER_VERSION,
        "plugin_version": _plugin_version(),
        "model_version": model_version or "unspecified",
        "runtime_label": runtime_label or "local-offline",
        "python": sys.version,
        "platform": platform.platform(),
        "origin_invoked": False,
    }


def _freeze_ok(freeze_file: str | Path | None) -> tuple[bool, str]:
    if freeze_file is None:
        return False, "held-out evaluation requires --freeze-file."
    path = Path(freeze_file).expanduser().resolve()
    try:
        payload = _read_json(path)
    except InputValidationError as exc:
        return False, str(exc)
    if not isinstance(payload, dict):
        return False, "freeze file must be a JSON object."
    if payload.get("status") != "frozen" or payload.get("approved") is not True:
        return False, "freeze file must contain status=frozen and approved=true."
    for key in ("development_status", "regression_status"):
        if payload.get(key) not in {"pass", "passed", "ok"}:
            return False, f"freeze file requires {key}=pass before held-out evaluation."
    return True, ""


def _case_reference(manifest_path: Path, case: dict[str, Any]) -> Path:
    reference = _resolve(manifest_path, case["reference"])
    if not reference.is_file():
        raise InputValidationError(f"Reference image does not exist: {reference}")
    expected = case.get("image_sha256")
    if expected and sha256_file(reference) != expected:
        raise InputValidationError(f"Reference hash changed for {case['case_id']}.")
    return reference


def _write_attempt_metadata(attempt_dir: Path, metadata: dict[str, Any]) -> None:
    write_json(attempt_dir / "attempt.json", metadata)
    # A marker makes it clear that a run directory is a historical record.  A
    # new review is written beside the attempt and never overwrites this file.
    (attempt_dir / "IMMUTABLE_ATTEMPT").write_text(
        "This attempt is immutable. Add reviews under the benchmark reviews directory.\n",
        encoding="utf-8",
    )


def _new_attempt_dir(root: Path, case_id: str) -> Path:
    root = root.expanduser().resolve()
    for _ in range(5):
        path = root / case_id / _attempt_id()
        try:
            path.mkdir(parents=True, exist_ok=False)
            return path
        except FileExistsError:
            continue
    raise OSError(f"Could not allocate an immutable attempt directory for {case_id}.")


def _status_record(status: str, reason: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {"status": status}
    if reason:
        result["reason"] = reason
    return result


def _normalise_evidence(value: Any) -> dict[str, Any]:
    """Return a stable check record for a value supplied by a reviewer.

    Review files are intentionally human-authored, so older records use a
    mixture of ``passed``, ``pass`` and nested ``{"status": ...}`` forms.
    Keeping the normalisation in one place means reports can consume those
    records without silently treating an omitted check as a pass.
    """
    if isinstance(value, dict):
        record = dict(value)
        status = record.get("status")
        if status is None and "result" in record:
            status = record.get("result")
    elif value is None:
        return _status_record("not_run", "No reviewer evidence was recorded.")
    else:
        record = {"evidence": value}
        status = value
    if isinstance(status, bool):
        status = "pass" if status else "fail"
    status_text = str(status or "").strip().lower()
    if status_text in _EVIDENCE_PASS:
        record["status"] = "pass"
    elif status_text in _EVIDENCE_NOT_RUN:
        record["status"] = "not_run"
    else:
        # Preserve a reviewer's useful value while making the state explicit.
        record["status"] = str(status or "fail")
    return record


def _review_checks(attempt: dict[str, Any], review: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Merge immutable attempt checks with evidence from a visual review.

    The old report always returned the attempt's ``not_run`` records, even
    when a reviewer had actually verified save/reopen and replacement.  This
    helper exposes the reviewer evidence while retaining a truthful
    ``not_run`` value when the reviewer did not provide it.
    """
    attempt_checks = attempt.get("checks") if isinstance(attempt.get("checks"), dict) else {}
    result: dict[str, dict[str, Any]] = {
        name: dict(value) if isinstance(value, dict) else _status_record("not_run")
        for name, value in attempt_checks.items()
    }
    for name in ("native", "visual_review", "save_reopen", "data_replacement"):
        result.setdefault(name, _status_record("not_run"))
    if not review:
        return result

    # A review status is the visual decision (pass/minor/major), rather than
    # proof that an Origin project was opened successfully.
    review_status = str(review.get("status", "")).strip().lower()
    if review_status in REVIEW_STATUSES:
        result["visual_review"] = {
            "status": review_status,
            "source": "review.status",
        }
    native_value = review.get("native_verification", review.get("native"))
    if native_value is not None:
        result["native"] = _normalise_evidence(native_value)

    editable = review.get("editable") if isinstance(review.get("editable"), dict) else {}
    save_value = editable.get("save_reopen_persists", review.get("save_reopen"))
    replacement_value = editable.get("replacement_updates_plot", review.get("data_replacement"))
    if save_value is not None:
        result["save_reopen"] = _normalise_evidence(save_value)
    if replacement_value is not None:
        result["data_replacement"] = _normalise_evidence(replacement_value)
    return result


def _pass_evidence_missing(review: dict[str, Any]) -> list[str]:
    """List required evidence omitted by a reviewer claiming ``pass``."""
    checks = _review_checks({}, review)
    required = {
        "native": checks["native"],
        "save_reopen": checks["save_reopen"],
        "data_replacement": checks["data_replacement"],
    }
    return [name for name, record in required.items()
            if str(record.get("status", "")).strip().lower() not in {"pass", "passed", "ok"}]


def _unsupported_spec(spec: Any) -> tuple[bool, str]:
    if not isinstance(spec, dict):
        return False, ""
    marker = spec.get("benchmark")
    if isinstance(marker, dict) and marker.get("status") == "unsupported":
        return True, str(marker.get("reason", "The model marked this figure family unsupported."))
    if spec.get("status") == "unsupported" or spec.get("unsupported") is True:
        return True, str(spec.get("reason", "The model marked this figure family unsupported."))
    return False, ""


def run_case(
    manifest_path: str | Path,
    case: dict[str, Any],
    spec_path: str | Path | None,
    attempts_root: str | Path,
    *,
    model_version: str = "",
    runtime_label: str = "",
    freeze_file: str | Path | None = None,
) -> dict[str, Any]:
    """Prepare one model-authored spec without opening Origin.

    The returned overall status remains ``pending_review`` after successful
    preparation.  Only a separate review can say pass/minor/major.
    """
    manifest_file, _ = load_benchmark_manifest(manifest_path)
    case_id = str(case.get("case_id", ""))
    split = str(case.get("split", ""))
    if not case_id or not split:
        raise InputValidationError("Benchmark case requires case_id and split.")
    freeze_info: dict[str, Any] | None = None
    if HELDOUT_SPLIT_RE.search(split):
        frozen, reason = _freeze_ok(freeze_file)
        if not frozen:
            raise InputValidationError(reason)
        freeze_path = Path(freeze_file).expanduser().resolve() if freeze_file else None
        freeze_info = {"path": str(freeze_path), "sha256": sha256_file(freeze_path)} if freeze_path else None
    reference = _case_reference(manifest_file, case)
    attempt_dir = _new_attempt_dir(Path(attempts_root), case_id)
    metadata: dict[str, Any] = {
        "benchmark_version": str(_read_json(manifest_file).get("benchmark_version", "unknown")),
        "runner_version": RUNNER_VERSION,
        "attempt_id": attempt_dir.name,
        "case_id": case_id,
        "split": split,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "reference": {"path": str(reference), "sha256": sha256_file(reference)},
        "manifest": {"path": str(manifest_file), "sha256": sha256_file(manifest_file)},
        "runtime": _runtime_metadata(model_version, runtime_label),
        "heldout_freeze": freeze_info,
        "checks": {
            "native": _status_record("not_run", "Origin is intentionally not invoked by the offline benchmark runner."),
            "visual_review": _status_record("not_recorded", "Use benchmark record after blinded visual review."),
            "save_reopen": _status_record("not_run", "Requires a separate local Origin verification."),
            "data_replacement": _status_record("not_run", "Requires a separate local Origin verification."),
        },
        "fidelity_claim": False,
    }
    if spec_path is None:
        metadata["overall_status"] = "missing_spec"
        metadata["failure_categories"] = ["missing_spec"]
        metadata["spec"] = None
        _write_attempt_metadata(attempt_dir, metadata)
        return metadata
    spec_file = Path(spec_path).expanduser().resolve()
    metadata["spec"] = {"path": str(spec_file), "sha256": sha256_file(spec_file)} if spec_file.is_file() else {"path": str(spec_file)}
    if not spec_file.is_file():
        metadata["overall_status"] = "missing_spec"
        metadata["failure_categories"] = ["missing_spec"]
        _write_attempt_metadata(attempt_dir, metadata)
        return metadata
    spec = _read_json(spec_file)
    unsupported, reason = _unsupported_spec(spec)
    if unsupported:
        metadata["overall_status"] = "unsupported"
        metadata["failure_categories"] = ["unsupported"]
        metadata["unsupported_reason"] = reason
        write_json(attempt_dir / "template_spec_input.json", spec)
        _write_attempt_metadata(attempt_dir, metadata)
        return metadata
    write_json(attempt_dir / "template_spec_input.json", spec)
    try:
        prepared = prepare_template(str(reference), spec, str(attempt_dir / "prepared"))
    except Exception as exc:
        metadata["overall_status"] = "invalid_spec"
        metadata["failure_categories"] = ["invalid_spec"]
        metadata["error"] = str(exc)
        _write_attempt_metadata(attempt_dir, metadata)
        return metadata
    metadata["overall_status"] = "pending_review"
    metadata["failure_categories"] = []
    metadata["prepared"] = {
        "template_spec": str(prepared.get("template_spec", "")),
        "data_manifest": str(prepared.get("data_manifest", "")),
        "placeholder_policy": prepared.get("manifest", {}).get("data_policy", {}),
    }
    _write_attempt_metadata(attempt_dir, metadata)
    return metadata


def record_review(
    attempt_dir: str | Path,
    review: dict[str, Any],
    reviews_root: str | Path | None = None,
    *,
    reviewer: str = "",
) -> dict[str, Any]:
    """Write a review beside an immutable attempt, never mutate the attempt."""
    attempt = Path(attempt_dir).expanduser().resolve()
    attempt_json = attempt / "attempt.json"
    if not attempt_json.is_file():
        raise InputValidationError(f"Not an attempt directory: {attempt}")
    metadata = _read_json(attempt_json)
    if not isinstance(review, dict):
        raise InputValidationError("Review must be a JSON object.")
    status = review.get("status")
    if status not in REVIEW_STATUSES:
        raise InputValidationError(f"Review status must be one of: {sorted(REVIEW_STATUSES)}")
    if metadata.get("overall_status") in {"missing_spec", "unsupported"} and status == "pass":
        raise InputValidationError("A missing or unsupported attempt cannot be recorded as pass.")
    if status == "pass":
        missing = _pass_evidence_missing(review)
        if missing:
            names = ", ".join(missing)
            raise InputValidationError(
                "A pass review requires explicit evidence for: " + names + ". "
                "Record native_verification and editable save_reopen_persists/"
                "replacement_updates_plot as pass."
            )
    payload = dict(review)
    payload.update({
        "review_version": "0.3",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "reviewer": reviewer or review.get("reviewer", "unspecified"),
        "attempt_id": metadata.get("attempt_id", attempt.name),
        "case_id": metadata.get("case_id"),
        "split": metadata.get("split"),
        "fidelity_claim": False,
    })
    destination_root = Path(reviews_root or attempt.parent.parent / "reviews").expanduser().resolve()
    destination = destination_root / str(metadata.get("case_id", attempt.name))
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / f"{payload['attempt_id']}-{_utc_stamp()}-{uuid.uuid4().hex[:6]}.json"
    write_json(path, payload)
    return {"status": "recorded", "review": str(path), "attempt_id": payload["attempt_id"], "case_id": payload["case_id"]}


def _iter_reviews(reviews_root: Path) -> Iterable[dict[str, Any]]:
    if not reviews_root.is_dir():
        return []
    records: list[dict[str, Any]] = []
    for path in sorted(reviews_root.rglob("*.json")):
        try:
            item = _read_json(path)
        except InputValidationError:
            continue
        if isinstance(item, dict) and item.get("attempt_id") and item.get("status") in REVIEW_STATUSES:
            item["_path"] = str(path)
            records.append(item)
    return records


def _review_matches_attempt(review: dict[str, Any], attempt: dict[str, Any]) -> bool:
    """Reject hand-edited/copy-pasted reviews attached to another case."""
    if str(review.get("attempt_id", "")) != str(attempt.get("attempt_id", "")):
        return False
    for key in ("case_id", "split"):
        review_value = review.get(key)
        if review_value is not None and str(review_value) != str(attempt.get(key)):
            return False
    return True


def _latest_reviews(reviews: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Select the latest review deterministically for each attempt."""
    latest: dict[str, dict[str, Any]] = {}
    for review in reviews:
        attempt_id = str(review.get("attempt_id", ""))
        if not attempt_id:
            continue
        current = latest.get(attempt_id)
        if current is None:
            latest[attempt_id] = review
            continue
        # ISO timestamps sort lexically; path is a deterministic tie-breaker
        # for old review files that have no recorded_at field.
        key = (str(review.get("recorded_at", "")), str(review.get("_path", "")))
        old_key = (str(current.get("recorded_at", "")), str(current.get("_path", "")))
        if key >= old_key:
            latest[attempt_id] = review
    return latest


def build_report(
    manifest_path: str | Path,
    attempts_root: str | Path,
    reviews_root: str | Path | None = None,
    *,
    split: str | None = None,
) -> dict[str, Any]:
    manifest_file, manifest = load_benchmark_manifest(manifest_path)
    case_map = {case["case_id"]: case for case in manifest["cases"]}
    attempt_root = Path(attempts_root).expanduser().resolve()
    review_root = Path(reviews_root or attempt_root / "reviews").expanduser().resolve()
    attempts: list[dict[str, Any]] = []
    if attempt_root.is_dir():
        for path in sorted(attempt_root.glob("*/*/attempt.json")):
            try:
                item = _read_json(path)
            except InputValidationError:
                continue
            if isinstance(item, dict) and (split is None or item.get("split") == split):
                attempts.append(item)
    reviews = [item for item in _iter_reviews(review_root)
               if split is None or item.get("split") == split]
    reviewed = _latest_reviews(reviews)
    rejected_reviews: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for attempt in attempts:
        case_id = str(attempt.get("case_id"))
        if case_id not in case_map:
            continue
        review = reviewed.get(str(attempt.get("attempt_id")))
        if review is not None and not _review_matches_attempt(review, attempt):
            rejected_reviews.append({
                "path": review.get("_path"),
                "attempt_id": review.get("attempt_id"),
                "reason": "Review case_id or split does not match its attempt.",
            })
            review = None
        review_status = str(review.get("status")) if review else ""
        pass_evidence_missing = _pass_evidence_missing(review) if review_status == "pass" else []
        # A hand-authored review may bypass record_review.  Never present
        # such a pass as an accepted benchmark result.
        status = (
            "pass_incomplete" if pass_evidence_missing else
            review_status if review else str(attempt.get("overall_status", "unknown"))
        )
        counts[status] = counts.get(status, 0) + 1
        checks = _review_checks(attempt, review)
        rows.append({
            "case_id": case_id,
            "split": attempt.get("split"),
            "attempt_id": attempt.get("attempt_id"),
            "attempt_status": attempt.get("overall_status"),
            "review_status": review.get("status") if review else None,
            "status": status,
            "pass_evidence_missing": pass_evidence_missing,
            "review": review.get("_path") if review else None,
            "failure_categories": (review or {}).get("failure_category", attempt.get("failure_categories", [])),
            "native": checks["native"],
            "visual_review": checks["visual_review"],
            "save_reopen": checks["save_reopen"],
            "data_replacement": checks["data_replacement"],
            "review_integrity": "pass" if review is not None else "not_recorded",
        })
    return {
        "report_version": "0.3",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "manifest": {"path": str(manifest_file), "sha256": sha256_file(manifest_file)},
        "split": split,
        "attempt_root": str(attempt_root),
        "reviews_root": str(review_root),
        "counts": counts,
        "rows": rows,
        "rejected_reviews": rejected_reviews,
        "interpretation": "Prepared artifacts and pixel values are not fidelity passes. Only an explicit review records visual, semantic, native, persistence, or replacement evidence.",
    }


