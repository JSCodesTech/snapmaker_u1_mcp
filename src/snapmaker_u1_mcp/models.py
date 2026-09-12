from __future__ import annotations

from pathlib import Path
import struct
import zipfile
import xml.etree.ElementTree as ET

from .config import Config
from .errors import ConfigurationError
from .orca import locate_slicer
from .paths import safe_file
from .profiles import ProfileStore, discover_profile_roots
from .slicer import SUPPORTED_MODEL_EXTENSIONS

DEFAULT_U1_BUILD_VOLUME = {"x": 270.0, "y": 270.0, "z": 270.0}


def u1_inspect_model(model: str) -> dict:
    """Inspect STL/3MF dimensions and basic printability facts inside U1_MODEL_DIR."""
    config = Config.from_env()
    model_path = _safe_model_path(config.model_dir, model)
    if model_path.suffix.lower() == ".stl":
        info = _inspect_stl(model_path)
    elif model_path.suffix.lower() == ".3mf":
        info = _inspect_3mf(model_path)
    else:  # defensive; _safe_model_path already checks this
        raise ConfigurationError(f"Unsupported model extension: {model_path.suffix}")

    build_volume = _u1_build_volume(config)
    info.update({
        "path": str(model_path),
        "name": str(model_path.relative_to(config.model_dir.expanduser().resolve())),
        "file_size": model_path.stat().st_size,
        "build_volume": build_volume,
        "fits_u1_build_volume": _fits(info.get("dimensions"), build_volume),
    })
    info["warnings"] = _model_warnings(info, build_volume)
    return info


def u1_model_diagnostics(model: str) -> dict:
    """Return practical pre-slice diagnostics derived from model inspection."""
    inspection = u1_inspect_model(model)
    dims = inspection.get("dimensions")
    build_volume = inspection.get("build_volume") or dict(DEFAULT_U1_BUILD_VOLUME)
    diagnostics = _diagnostics_for_inspection(inspection, build_volume)
    return {
        "status": "ok" if not diagnostics["errors"] else "warning",
        "model": inspection.get("name"),
        "path": inspection.get("path"),
        "build_volume": build_volume,
        "dimensions": dims,
        "diagnostics": diagnostics,
        "inspection_warnings": inspection.get("warnings", []),
    }


def u1_orientation_preflight(model: str) -> dict:
    """Compare simple bounding-box orientation candidates without invoking Snapmaker Orca rotations."""
    info = u1_inspect_model(model)
    dims = info.get("dimensions")
    build_volume = info.get("build_volume") or dict(DEFAULT_U1_BUILD_VOLUME)
    if not dims:
        return {
            "status": "error",
            "model": model,
            "reason": "Model dimensions are unavailable; cannot preflight orientations",
            "inspection": info,
        }

    candidates = _orientation_candidates(dims, build_volume)
    printable = [item for item in candidates if item["fits_axis_aligned"]]
    recommended = min(printable, key=lambda item: (item["cli_rotation_risk"], item["dimensions"]["z"], item["footprint_area"])) if printable else None
    return {
        "status": "ok" if printable else "warning",
        "model": info["name"],
        "path": info["path"],
        "source_dimensions": dims,
        "build_volume": build_volume,
        "recommended": recommended["name"] if recommended else None,
        "candidates": candidates,
        "warnings": [
            "Snapmaker Orca Linux CLI 01.10.01.50 may segfault on non-zero CLI rotation transforms; this tool is preflight-only and does not slice rotated variants."
        ] + ([] if printable else ["No simple axis-aligned orientation candidate fits the U1 build volume"]),
    }


def _inspect_stl(path: Path) -> dict:
    data = path.read_bytes()
    if _looks_binary_stl(data):
        return _inspect_binary_stl(data)
    return _inspect_ascii_stl(data.decode("utf-8", errors="replace"))


def _looks_binary_stl(data: bytes) -> bool:
    if len(data) < 84:
        return False
    count = struct.unpack_from("<I", data, 80)[0]
    return 84 + count * 50 == len(data)


def _inspect_binary_stl(data: bytes) -> dict:
    count = struct.unpack_from("<I", data, 80)[0]
    points = []
    offset = 84
    for _ in range(count):
        offset += 12  # normal
        for _vertex in range(3):
            points.append(struct.unpack_from("<fff", data, offset))
            offset += 12
        offset += 2
    return _mesh_info("stl", points, facet_count=count, body_count=None)


def _inspect_ascii_stl(text: str) -> dict:
    points = []
    facet_count = 0
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("facet normal"):
            facet_count += 1
        elif stripped.startswith("vertex "):
            parts = stripped.split()
            if len(parts) == 4:
                try:
                    points.append((float(parts[1]), float(parts[2]), float(parts[3])))
                except ValueError:
                    pass
    return _mesh_info("stl", points, facet_count=facet_count or None, body_count=None)


def _inspect_3mf(path: Path) -> dict:
    points = []
    triangle_count = 0
    object_count = 0
    with zipfile.ZipFile(path) as archive:
        model_names = [name for name in archive.namelist() if name.startswith("3D/") and name.endswith(".model")]
        for name in model_names:
            root = ET.fromstring(archive.read(name))
            ns = {"m": root.tag.split("}")[0].strip("{")} if root.tag.startswith("{") else {}
            objects = root.findall(".//m:object", ns) if ns else root.findall(".//object")
            object_count += len(objects)
            vertices = root.findall(".//m:vertex", ns) if ns else root.findall(".//vertex")
            triangles = root.findall(".//m:triangle", ns) if ns else root.findall(".//triangle")
            triangle_count += len(triangles)
            for vertex in vertices:
                try:
                    points.append((float(vertex.attrib["x"]), float(vertex.attrib["y"]), float(vertex.attrib["z"])))
                except (KeyError, ValueError):
                    pass
    return _mesh_info("3mf", points, facet_count=triangle_count, body_count=object_count)


def _mesh_info(file_type: str, points: list[tuple[float, float, float]], facet_count: int | None, body_count: int | None) -> dict:
    if not points:
        return {
            "type": file_type,
            "valid_mesh": False,
            "dimensions": None,
            "bounding_box": None,
            "facet_count": facet_count,
            "body_count": body_count,
        }
    xs, ys, zs = zip(*points)
    bbox = {
        "min": {"x": min(xs), "y": min(ys), "z": min(zs)},
        "max": {"x": max(xs), "y": max(ys), "z": max(zs)},
    }
    dims = {
        "x": bbox["max"]["x"] - bbox["min"]["x"],
        "y": bbox["max"]["y"] - bbox["min"]["y"],
        "z": bbox["max"]["z"] - bbox["min"]["z"],
    }
    return {
        "type": file_type,
        "valid_mesh": bool(facet_count is None or facet_count > 0),
        "dimensions": dims,
        "bounding_box": bbox,
        "facet_count": facet_count,
        "body_count": body_count,
    }


def _u1_build_volume(config: Config) -> dict[str, float]:
    try:
        binary = locate_slicer(config)
        store = ProfileStore(discover_profile_roots(config.profile_dir, binary))
        machine = store.resolve_profile("Snapmaker U1 (0.4 nozzle)", "machine")
        height = _float_or_none(machine.get("printable_height")) or DEFAULT_U1_BUILD_VOLUME["z"]
        area = machine.get("printable_area")
        if isinstance(area, list) and area:
            xs, ys = [], []
            for point in area:
                x, y = str(point).split("x", 1)
                xs.append(float(x)); ys.append(float(y))
            return {"x": max(xs) - min(xs), "y": max(ys) - min(ys), "z": height}
    except Exception:
        pass
    return dict(DEFAULT_U1_BUILD_VOLUME)


def _fits(dimensions: dict | None, build_volume: dict[str, float]) -> bool | None:
    if not dimensions:
        return None
    dims = sorted(float(v) for v in dimensions.values())
    bed = sorted([build_volume["x"], build_volume["y"], build_volume["z"]])
    return all(d <= b for d, b in zip(dims, bed))


def _model_warnings(info: dict, build_volume: dict[str, float]) -> list[str]:
    warnings = []
    if not info.get("valid_mesh"):
        warnings.append("No valid mesh vertices/facets were detected")
    if info.get("fits_u1_build_volume") is False:
        warnings.append("Model dimensions exceed Snapmaker U1 build volume in all axis-aligned orientations")
    dims = info.get("dimensions") or {}
    if dims and min(dims.values()) <= 0:
        warnings.append("Model has a zero-sized bounding-box dimension")
    return warnings


def _diagnostics_for_inspection(inspection: dict, build_volume: dict[str, float]) -> dict:
    dims = inspection.get("dimensions") or {}
    warnings: list[str] = []
    errors: list[str] = []
    suggestions: list[str] = []
    if not inspection.get("valid_mesh"):
        errors.append("No valid mesh vertices/facets were detected")
        return {"errors": errors, "warnings": warnings, "suggestions": suggestions}
    if not dims:
        errors.append("Model dimensions are unavailable")
        return {"errors": errors, "warnings": warnings, "suggestions": suggestions}

    values = {axis: float(dims.get(axis) or 0.0) for axis in ("x", "y", "z")}
    smallest = min(values.values())
    largest = max(values.values())
    if smallest <= 0:
        errors.append("Model has a zero-sized bounding-box dimension")
    elif smallest < 0.5:
        warnings.append(f"Very thin feature/bounding dimension detected: {smallest:.2f} mm")
    if largest < 5:
        warnings.append("Model is very small; verify units are millimeters")
    if largest > max(build_volume.values()):
        errors.append("At least one model dimension exceeds the largest U1 build-volume axis")
    elif largest > max(build_volume.values()) * 0.9:
        warnings.append("Model is close to the U1 build-volume limit")

    axis_fit = _fits_axis_aligned(values, build_volume)
    any_fit = _fits(values, build_volume)
    if not axis_fit and any_fit:
        suggestions.append("Model may fit after reorientation; run u1_orientation_preflight before slicing")
    elif not any_fit:
        errors.append("Model does not fit the U1 build volume in any simple axis-aligned orientation")
    if values["z"] > build_volume["z"] * 0.8:
        warnings.append("Tall model; verify stability, supports, and clearance")
    footprint = values["x"] * values["y"]
    bed_area = build_volume["x"] * build_volume["y"]
    if footprint > bed_area * 0.8:
        warnings.append("Large bed footprint; verify brim/skirt clearance")
    facet_count = inspection.get("facet_count")
    if isinstance(facet_count, int) and facet_count > 1_000_000:
        warnings.append("Very high facet count; slicing may be slow")
    if isinstance(facet_count, int) and facet_count < 4:
        warnings.append("Very low facet count; model may not be a closed printable mesh")
    return {"errors": errors, "warnings": warnings, "suggestions": suggestions}


def _orientation_candidates(dimensions: dict, build_volume: dict[str, float]) -> list[dict]:
    x = float(dimensions["x"])
    y = float(dimensions["y"])
    z = float(dimensions["z"])
    definitions = [
        ("as-loaded", {}, {"x": x, "y": y, "z": z}, "Safest candidate; no CLI rotation transform is needed."),
        ("rotate-x-90", {"rotate_x": 90}, {"x": x, "y": z, "z": y}, "Preflight only; slicing this orientation through CLI rotation may crash this Snapmaker Orca build."),
        ("rotate-y-90", {"rotate_y": 90}, {"x": z, "y": y, "z": x}, "Preflight only; slicing this orientation through CLI rotation may crash this Snapmaker Orca build."),
        ("rotate-z-90", {"rotate": 90}, {"x": y, "y": x, "z": z}, "Preflight only; slicing this orientation through CLI rotation may crash this Snapmaker Orca build."),
    ]
    candidates = []
    for name, cli_orientation, dims, note in definitions:
        fits = _fits_axis_aligned(dims, build_volume)
        candidates.append({
            "name": name,
            "cli_orientation": cli_orientation,
            "dimensions": dims,
            "footprint_area": dims["x"] * dims["y"],
            "fits_axis_aligned": fits,
            "cli_rotation_risk": bool(cli_orientation),
            "note": note,
        })
    return candidates


def _fits_axis_aligned(dimensions: dict, build_volume: dict[str, float]) -> bool:
    return (
        float(dimensions["x"]) <= float(build_volume["x"])
        and float(dimensions["y"]) <= float(build_volume["y"])
        and float(dimensions["z"]) <= float(build_volume["z"])
    )


def _float_or_none(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_model_path(root: Path, model: str) -> Path:
    return safe_file(root, model, SUPPORTED_MODEL_EXTENSIONS, label="Model")
