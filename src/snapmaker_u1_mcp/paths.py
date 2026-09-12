from __future__ import annotations

from pathlib import Path
import json
import time
import uuid

from .errors import ConfigurationError


def resolve_child(root: Path, relative_path: str, *, label: str = "File") -> Path:
    root = root.expanduser().resolve()
    candidate = (root / relative_path).resolve()
    if not is_relative_to(candidate, root):
        raise ConfigurationError(f"{label} path escapes configured directory")
    return candidate


def safe_file(root: Path, relative_path: str, allowed_extensions: set[str], *, label: str = "File") -> Path:
    candidate = resolve_child(root, relative_path, label=label)
    if candidate.suffix.lower() not in allowed_extensions:
        raise ConfigurationError(f"Unsupported {label.lower()} extension: {candidate.suffix}")
    if not candidate.is_file():
        raise ConfigurationError(f"{label} not found: {relative_path}")
    return candidate


def list_allowed_files(root: Path, allowed_extensions: set[str]) -> list[dict]:
    root = root.expanduser().resolve()
    if not root.exists():
        return []
    files = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in allowed_extensions:
            continue
        resolved = path.resolve()
        if not is_relative_to(resolved, root):
            continue
        files.append({"name": str(resolved.relative_to(root)), "path": str(resolved), "size": resolved.stat().st_size})
    return sorted(files, key=lambda item: item["name"].lower())


def new_run_dir(root: Path) -> Path:
    root = root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    run_dir = root / f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    run_dir.mkdir()
    return run_dir


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
