from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from pathlib import Path
import json

from .errors import ProfileError

PROFILE_TYPES = ("machine", "process", "filament")
PROFILE_DIR_NAMES = {
    "machine": ("machine", "Machine", "printers", "printer"),
    "process": ("process", "Process", "print", "prints"),
    "filament": ("filament", "Filament", "filaments"),
}


@dataclass(frozen=True)
class ProfileInfo:
    name: str
    type: str
    path: str
    inherits: str | None = None
    nozzle: str | None = None
    material: str | None = None
    layer_height: str | None = None


@dataclass(frozen=True)
class ProfileSelection:
    machine_name: str
    process_name: str
    filament_name: str
    nozzle: float


class ProfileStore:
    def __init__(self, roots: list[Path]):
        self.roots = [p.expanduser().resolve() for p in roots if p]

    def list_profiles(
        self,
        profile_type: str | None = None,
        *,
        nozzle: float | None = None,
        material: str | None = None,
        layer_height: float | None = None,
    ) -> dict[str, list[ProfileInfo]]:
        types = [profile_type] if profile_type else list(PROFILE_TYPES)
        result: dict[str, list[ProfileInfo]] = {}
        for kind in types:
            _check_type(kind)
            infos = []
            for path in self._candidate_files(kind):
                try:
                    data = _load_json(path)
                except Exception:
                    continue
                name = str(data.get("name") or data.get("filament_settings_id") or data.get("print_settings_id") or path.stem)
                if not _is_relevant_profile(kind, data, name, path):
                    continue
                info = ProfileInfo(
                    name=name,
                    type=kind,
                    path=str(path),
                    inherits=data.get("inherits"),
                    nozzle=_first_str(data, "nozzle_diameter", "printer_variant"),
                    material=_first_str(data, "filament_type", "type"),
                    layer_height=_first_str(data, "layer_height"),
                )
                if _matches_filters(info, nozzle=nozzle, material=material, layer_height=layer_height):
                    infos.append(info)
            result[kind] = sorted(infos, key=lambda i: i.name.lower())
        return result

    def find_profile_path(self, name: str, profile_type: str, near: Path | None = None) -> Path:
        _check_type(profile_type)
        matches: list[Path] = []
        lowered = name.lower()
        for path in self._candidate_files(profile_type):
            try:
                data = _load_json(path)
            except Exception:
                continue
            profile_name = str(data.get("name") or data.get("filament_settings_id") or data.get("print_settings_id") or path.stem)
            if profile_name.lower() == lowered or path.stem.lower() == lowered:
                matches.append(path)
        if not matches:
            suggestions = self.suggest_profiles(name, profile_type)
            suffix = f". Did you mean: {suggestions}" if suggestions else ""
            raise ProfileError(f"{profile_type} profile not found: {name}{suffix}")
        matches = _prefer_context(matches, near) or _prefer_vendor(matches, "Snapmaker") or matches
        matches = _prefer_current(matches) or matches
        if len(matches) > 1:
            raise ProfileError(f"Ambiguous {profile_type} profile {name!r}: {[str(m) for m in matches]}")
        return matches[0]

    def resolve_profile(self, name: str, profile_type: str) -> dict:
        return self._resolve_path(self.find_profile_path(name, profile_type), profile_type, [])

    def suggest_profiles(self, query: str, profile_type: str, limit: int = 8) -> list[str]:
        _check_type(profile_type)
        query_tokens = _tokens(query)
        scored: list[tuple[int, str]] = []
        for path in self._candidate_files(profile_type):
            try:
                data = _load_json(path)
            except Exception:
                continue
            name = str(data.get("name") or data.get("filament_settings_id") or data.get("print_settings_id") or path.stem)
            haystack = f"{name} {path.stem}".lower()
            score = sum(1 for token in query_tokens if token in haystack)
            if score or query.lower() in haystack:
                if "snapmaker" in haystack:
                    score += 2
                if "u1" in haystack:
                    score += 2
                if "base" in haystack or "support" in haystack or "copy" in haystack or "old" in haystack:
                    score -= 1
                scored.append((score, name))
        return [name for _score, name in sorted(scored, key=lambda item: (-item[0], item[1].lower()))[:limit]]

    def validate_selection(self, selection: ProfileSelection) -> dict[str, Any]:
        machine = self.resolve_profile(selection.machine_name, "machine")
        process = self.resolve_profile(selection.process_name, "process")
        filament = self.resolve_profile(selection.filament_name, "filament")
        validate_profiles(machine, process, filament, selection.nozzle)
        return {"machine": machine, "process": process, "filament": filament}

    def _resolve_path(self, path: Path, profile_type: str, stack: list[Path]) -> dict:
        path = path.resolve()
        if path in stack:
            cycle = " -> ".join(p.stem for p in [*stack, path])
            raise ProfileError(f"Profile inheritance cycle detected: {cycle}")
        data = _load_json(path)
        parent_name = data.get("inherits")
        if not parent_name:
            return _runtime_profile(data)
        parent_path = self.find_profile_path(str(parent_name), profile_type, near=path)
        parent = self._resolve_path(parent_path, profile_type, [*stack, path])
        merged = dict(parent)
        merged.update(data)
        return _runtime_profile(merged)

    def _candidate_files(self, profile_type: str) -> list[Path]:
        dirs = PROFILE_DIR_NAMES[profile_type]
        files: list[Path] = []
        for root in self.roots:
            if not root.exists():
                continue
            search_roots = [p for d in dirs for p in root.glob(f"**/{d}") if p.is_dir()]
            if root.name in dirs:
                search_roots.append(root)
            for search_root in search_roots:
                files.extend(p for p in search_root.rglob("*.json") if p.is_file())
        return sorted(set(files))


def discover_profile_roots(configured: Path | None, slicer_binary: Path | None = None) -> list[Path]:
    roots: list[Path] = []
    if configured:
        roots.append(configured)
    if slicer_binary:
        for parent in [slicer_binary.parent, *slicer_binary.parents]:
            for rel in ("resources/profiles", "profiles", "Resources/profiles", "share/orca-slicer/profiles"):
                candidate = parent / rel
                if candidate.exists():
                    roots.append(candidate)
    return _dedupe(roots)


def validate_profiles(machine: dict, process: dict, filament: dict, nozzle: float) -> None:
    """Validate a resolved U1 machine/process/filament combination before slicing."""
    machine_name = str(machine.get("name") or "")
    model = str(machine.get("printer_model") or machine_name)
    if "snapmaker u1" not in f"{machine_name} {model}".lower():
        raise ProfileError(f"Selected machine profile is not Snapmaker U1: {machine_name or model}")

    explicit_machine_nozzles = _numbers(machine.get("nozzle_diameter")) + _numbers(machine.get("printer_variant"))
    machine_nozzles = explicit_machine_nozzles or _numbers(machine_name)
    if machine_nozzles and not any(abs(n - nozzle) < 0.001 for n in machine_nozzles):
        raise ProfileError(f"Selected machine profile {machine_name!r} does not support {nozzle:g} mm nozzle")

    compatible = _as_list(process.get("compatible_printers"))
    if compatible and not any(machine_name == item or f"({nozzle:g} nozzle)" in item for item in compatible):
        raise ProfileError(f"Selected process {process.get('name')!r} is not compatible with machine {machine_name!r}")

    process_nozzles = _numbers(process.get("compatible_printers")) + _numbers(process.get("compatible_printers_condition")) + _numbers(process.get("name"))
    if process_nozzles and not any(abs(n - nozzle) < 0.001 for n in process_nozzles):
        raise ProfileError(f"Selected process expects nozzle(s) {process_nozzles}, but machine nozzle is {nozzle:g} mm")

    layer_height = _first_number(process.get("layer_height"))
    if layer_height is not None and not 0.03 <= layer_height <= nozzle * 0.9:
        raise ProfileError(f"Process layer_height {layer_height:g} is not plausible for {nozzle:g} mm nozzle")

    if not _has_temperature(filament, "nozzle"):
        raise ProfileError(f"Filament profile {filament.get('name')!r} is missing nozzle temperature settings")
    if not _has_temperature(filament, "bed"):
        raise ProfileError(f"Filament profile {filament.get('name')!r} is missing bed temperature settings")


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        value = json.load(f)
    if not isinstance(value, dict):
        raise ProfileError(f"Profile JSON is not an object: {path}")
    return value


def _check_type(profile_type: str) -> None:
    if profile_type not in PROFILE_TYPES:
        raise ProfileError(f"Invalid profile type {profile_type!r}; expected one of {PROFILE_TYPES}")


def _is_relevant_profile(profile_type: str, data: dict, name: str, path: Path) -> bool:
    if profile_type == "machine":
        return data.get("type") == "machine" and not name.startswith("fdm_") and _looks_u1(data, name, path)
    vendor = (_vendor_part(path) or "").lower()
    # Bundled Snapmaker Orca installs contain many vendors. V1 only exposes U1
    # selection profiles from Snapmaker unless the user points directly at a
    # custom/non-vendor profile directory, where _vendor_part commonly resolves
    # to "profiles".
    if vendor and vendor not in {"snapmaker", "profiles"}:
        return False
    profile_label = f"{name} {path.stem}".lower()
    if name.startswith("fdm_") or any(marker in profile_label for marker in ("base", "copy", "old")):
        return vendor == "profiles"
    haystack = f"{name} {path.stem} {data.get('compatible_printers')} {data.get('compatible_prints')}".lower()
    return vendor == "profiles" or "u1" in haystack


def _looks_u1(data: dict, name: str, path: Path) -> bool:
    vendor = _vendor_part(path) or ""
    haystack = " ".join(str(v) for v in [name, data.get("printer_model"), data.get("printer_notes"), data.get("vendor"), vendor])
    lowered = haystack.lower()
    return "u1" in lowered and "snapmaker" in lowered


def _runtime_profile(data: dict) -> dict:
    cleaned = dict(data)
    # Headless --load-settings rejects files without a recognized `from` value.
    # Keep/set it while still removing inheritance for reproducible flat profiles.
    cleaned.pop("inherits", None)
    # Snapmaker Orca 01.10.01.50 Linux CLI segfaults while loading U1
    # process profiles that contain wipe_tower_filament. V1 is single-material,
    # so omitting this multi-material wipe-tower selector is safe for Phase 0.
    cleaned.pop("wipe_tower_filament", None)
    cleaned.setdefault("from", "system")
    return cleaned


def _matches_filters(info: ProfileInfo, *, nozzle: float | None, material: str | None, layer_height: float | None) -> bool:
    if nozzle is not None:
        haystack = f"{info.name} {info.nozzle or ''}"
        values = _numbers(haystack)
        if values and not any(abs(v - nozzle) < 0.001 for v in values):
            return False
    if material is not None and info.type == "filament":
        haystack = f"{info.name} {info.material or ''}".lower()
        if material.lower() not in haystack:
            return False
    if layer_height is not None and info.type == "process":
        haystack = f"{info.name} {info.layer_height or ''}"
        values = _numbers(haystack)
        if values and not any(abs(v - layer_height) < 0.001 for v in values):
            return False
    return True


def _tokens(value: str) -> list[str]:
    return [token for token in value.lower().replace("_", " ").replace("-", " ").split() if token]


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def _numbers(value: Any) -> list[float]:
    import re
    numbers: list[float] = []
    for item in _as_list(value):
        numbers.extend(float(match.group(1)) for match in re.finditer(r"(?<![A-Za-z0-9])(\d+(?:\.\d+)?)\s*(?:mm|nozzle)?", item, re.IGNORECASE))
    return numbers


def _first_number(value: Any) -> float | None:
    numbers = _numbers(value)
    return numbers[0] if numbers else None


def _has_temperature(profile: dict, kind: str) -> bool:
    kind = kind.lower()
    keys = [k for k in profile if "temp" in k.lower()]
    if kind == "nozzle":
        keys = [k for k in keys if "bed" not in k.lower() and "plate" not in k.lower() and "chamber" not in k.lower()]
    elif kind == "bed":
        keys = [k for k in keys if "bed" in k.lower() or "plate" in k.lower()]
    return any(_numbers(profile.get(k)) for k in keys)


def _first_str(data: dict, *keys: str) -> str | None:
    for key in keys:
        if key in data:
            value = data[key]
            if isinstance(value, list):
                return ",".join(map(str, value))
            return str(value)
    return None


def _prefer_current(matches: list[Path]) -> list[Path]:
    """Prefer active profiles over legacy/copy backup files when names are duplicated."""
    preferred = [p for p in matches if not any(marker in p.stem.lower() for marker in ("_old", " old", " copy", "_copy"))]
    return preferred if preferred and len(preferred) < len(matches) else []


def _prefer_context(matches: list[Path], near: Path | None) -> list[Path]:
    """Prefer profiles from the same vendor subtree as the child profile."""
    if near is None:
        return []
    near_vendor = _vendor_part(near)
    if not near_vendor:
        return []
    preferred = [p for p in matches if _vendor_part(p) == near_vendor]
    return preferred if preferred else []


def _prefer_vendor(matches: list[Path], vendor: str) -> list[Path]:
    preferred = [p for p in matches if vendor.lower() in [part.lower() for part in p.parts]]
    return preferred if preferred else []


def _vendor_part(path: Path) -> str | None:
    parts = path.parts
    for marker in ("machine", "Machine", "process", "Process", "filament", "Filament"):
        if marker in parts:
            idx = parts.index(marker)
            if idx > 0:
                return parts[idx - 1]
    return None


def _dedupe(paths: list[Path]) -> list[Path]:
    seen = set()
    out = []
    for p in paths:
        rp = p.expanduser().resolve()
        if rp not in seen:
            seen.add(rp)
            out.append(rp)
    return out
