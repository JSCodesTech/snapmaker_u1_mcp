from __future__ import annotations

from typing import Any

from .errors import ProfileError


SPARSE_INFILL_PATTERNS = {
    "rectilinear",
    "grid",
    "triangles",
    "stars",
    "cubic",
    "line",
    "concentric",
    "honeycomb",
    "3dhoneycomb",
    "gyroid",
    "hilbertcurve",
    "archimedeanchords",
    "octagramspiral",
    "adaptivecubic",
    "supportcubic",
    "lightning",
}

BRIM_TYPES = {
    "no_brim",
    "outer_only",
    "inner_only",
    "outer_and_inner",
    "auto_brim",
    "brim_ears",
    "painted",
}


def apply_process_overrides(process: dict, overrides: dict[str, Any] | None) -> tuple[dict, dict]:
    """Apply validated V1 process overrides to a resolved process profile.

    Returns `(new_process_profile, override_report)`.
    """
    if not overrides:
        return dict(process), {}
    if not isinstance(overrides, dict):
        raise ProfileError("overrides must be an object/dict")

    result = dict(process)
    report: dict[str, dict[str, Any]] = {}
    for key, value in overrides.items():
        if key == "layer_height":
            effective = _float_range(key, value, 0.03, 0.8)
            stored = _format_float(effective)
        elif key == "wall_loops":
            effective = _int_range(key, value, 1, 20)
            stored = str(effective)
        elif key == "top_shell_layers":
            effective = _int_range(key, value, 0, 30)
            stored = str(effective)
        elif key == "bottom_shell_layers":
            effective = _int_range(key, value, 0, 30)
            stored = str(effective)
        elif key == "sparse_infill_density":
            effective = _percent(key, value, 0, 100)
            stored = f"{_format_float(effective)}%"
        elif key == "sparse_infill_pattern":
            effective = _enum(key, value, SPARSE_INFILL_PATTERNS)
            stored = effective
        elif key == "enable_support":
            effective = _bool(key, value)
            stored = "1" if effective else "0"
        elif key == "brim_type":
            effective = _enum(key, value, BRIM_TYPES)
            stored = effective
        else:
            allowed = [
                "layer_height",
                "wall_loops",
                "top_shell_layers",
                "bottom_shell_layers",
                "sparse_infill_density",
                "sparse_infill_pattern",
                "enable_support",
                "brim_type",
            ]
            raise ProfileError(f"Override {key!r} is not allowed in V1. Allowed overrides: {allowed}")

        original = result.get(key)
        result[key] = stored
        report[key] = {"original": original, "effective": effective, "stored": stored}
    return result, report


def _float_range(key: str, value: Any, minimum: float, maximum: float) -> float:
    try:
        parsed = float(str(value).rstrip("%"))
    except (TypeError, ValueError):
        raise ProfileError(f"Override {key!r} must be a number") from None
    if not minimum <= parsed <= maximum:
        raise ProfileError(f"Override {key!r} must be between {minimum:g} and {maximum:g}")
    return parsed


def _int_range(key: str, value: Any, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise ProfileError(f"Override {key!r} must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ProfileError(f"Override {key!r} must be an integer") from None
    if not minimum <= parsed <= maximum:
        raise ProfileError(f"Override {key!r} must be between {minimum} and {maximum}")
    return parsed


def _percent(key: str, value: Any, minimum: float, maximum: float) -> float:
    return _float_range(key, value, minimum, maximum)


def _enum(key: str, value: Any, allowed: set[str]) -> str:
    if not isinstance(value, str):
        raise ProfileError(f"Override {key!r} must be a string")
    normalized = value.strip()
    if normalized not in allowed:
        raise ProfileError(f"Override {key!r} must be one of {sorted(allowed)}")
    return normalized


def _bool(key: str, value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    raise ProfileError(f"Override {key!r} must be a boolean")


def _format_float(value: float) -> str:
    return f"{value:g}"
