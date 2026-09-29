from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class InputValidationError(ValueError):
    """Raised when an input path or structured payload is invalid."""


def resolve_input(path: str | Path, allowed_suffixes: set[str] | None = None) -> Path:
    candidate = Path(path).expanduser().resolve()
    if not candidate.exists() or not candidate.is_file():
        raise InputValidationError(f"Input file does not exist: {candidate}")
    if allowed_suffixes and candidate.suffix.lower() not in allowed_suffixes:
        allowed = ", ".join(sorted(allowed_suffixes))
        raise InputValidationError(
            f"Unsupported file type {candidate.suffix!r}; expected one of: {allowed}"
        )
    return candidate


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_safe(value: Any) -> Any:
    """Convert common pandas/numpy values into JSON-safe Python values."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "item"):
        try:
            return json_safe(value.item())
        except (ValueError, TypeError):
            pass
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    return str(value)


def write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(json_safe(payload), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path
