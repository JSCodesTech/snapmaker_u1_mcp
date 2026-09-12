from __future__ import annotations

from pathlib import Path
import re


def analyze_gcode(path: Path, requested_material: str | None = None) -> dict:
    path = path.expanduser().resolve()
    result: dict = {
        "path": str(path),
        "file_size": path.stat().st_size if path.exists() else 0,
        "warnings": [],
    }
    if not path.exists() or path.stat().st_size == 0:
        result["warnings"].append("G-code file missing or empty")
        return result

    text = path.read_text(encoding="utf-8", errors="replace")
    comments = "\n".join(line for line in text.splitlines() if line.startswith(";"))

    result["layer_count"] = _max_int(comments, [r"total layer(?: number|s)?\s*[:=]\s*(\d+)", r"LAYER_COUNT\s*[:=]\s*(\d+)"])
    if result["layer_count"] is None:
        layers = [int(m.group(1)) for m in re.finditer(r"^;\s*LAYER:?\s*(\d+)", text, re.MULTILINE)]
        result["layer_count"] = max(layers) + 1 if layers else None

    result["estimated_print_time"] = _first_match(comments, [
        r"estimated printing time.*?[:=]\s*([^\n;]+)",
        r"estimated_print_time\s*[:=]\s*([^\n;]+)",
    ])
    result["filament_length"] = _first_match(comments, [r"filament used \[mm\]\s*[:=]\s*([^\n;]+)", r"filament used\s*[:=]\s*([^\n;]+)"])
    result["filament_weight"] = _first_match(comments, [r"filament used \[g\]\s*[:=]\s*([^\n;]+)", r"filament weight\s*[:=]\s*([^\n;]+)"])
    result["layer_height"] = _first_match(comments, [r"layer_height\s*[:=]\s*([^\n;]+)", r"Layer height\s*[:=]\s*([^\n;]+)"])
    result["detected_material"] = _first_match(comments, [r"filament_type\s*[:=]\s*([^\n;]+)", r"filament_type = ([^\n;]+)", r"filament_settings_id\s*[:=]\s*([^\n;]+)"])
    result["nozzle_temperatures"] = sorted(set(int(v) for v in re.findall(r"\bM10[49]\s+S(\d+)", text)))
    result["bed_temperatures"] = sorted(set(int(v) for v in re.findall(r"\bM(?:140|190)\s+S(\d+)", text)))
    result["tool_count"] = len(set(re.findall(r"^T(\d+)\b", text, re.MULTILINE))) or 1
    result["safety_checks"] = _safety_checks(result, text, requested_material)
    result["warnings"].extend(result["safety_checks"]["warnings"])

    if requested_material and result.get("detected_material"):
        requested = requested_material.lower()
        detected = str(result["detected_material"]).lower()
        if detected not in requested and requested not in detected:
            result["warnings"].append(
                f"Requested material {requested_material!r} but G-code metadata appears to be {result['detected_material']!r}"
            )
    return result


def _safety_checks(result: dict, text: str, requested_material: str | None) -> dict:
    warnings: list[str] = []
    nozzle_temps = [t for t in result.get("nozzle_temperatures", []) if t > 0]
    bed_temps = [t for t in result.get("bed_temperatures", []) if t > 0]
    material = str(requested_material or result.get("detected_material") or "").upper()
    if result.get("tool_count", 1) > 1:
        warnings.append(f"G-code uses {result['tool_count']} tools; current workflow is intended for single-material slicing")
    if nozzle_temps and max(nozzle_temps) > 280:
        warnings.append(f"High nozzle temperature detected: {max(nozzle_temps)} °C")
    if bed_temps and max(bed_temps) > 120:
        warnings.append(f"High bed temperature detected: {max(bed_temps)} °C")
    if "PLA" in material and nozzle_temps and max(nozzle_temps) > 235:
        warnings.append(f"PLA nozzle temperature looks high: {max(nozzle_temps)} °C")
    if "PETG" in material and nozzle_temps and max(nozzle_temps) < 220:
        warnings.append(f"PETG nozzle temperature looks low: {max(nozzle_temps)} °C")
    if "TPU" in material and nozzle_temps and max(nozzle_temps) > 250:
        warnings.append(f"TPU nozzle temperature looks high: {max(nozzle_temps)} °C")
    if not re.search(r"\bM84\b|\bM18\b", text):
        warnings.append("No motor-disable command M84/M18 detected near end of G-code")
    if not re.search(r"\bM10[49]\s+S0\b", text):
        warnings.append("No nozzle heater-off command detected")
    return {"warnings": warnings}


def _first_match(text: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def _max_int(text: str, patterns: list[str]) -> int | None:
    values = []
    for pattern in patterns:
        values.extend(int(m.group(1)) for m in re.finditer(pattern, text, re.IGNORECASE))
    return max(values) if values else None
