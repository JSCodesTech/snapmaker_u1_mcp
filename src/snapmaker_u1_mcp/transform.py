from __future__ import annotations

from pathlib import Path
import json
import math
import struct
import time
import uuid

from .config import Config
from .errors import ConfigurationError
from .paths import safe_file

SUPPORTED_MODEL_EXTENSIONS = {".stl", ".3mf"}


def u1_transform_model(
    model: str,
    rotate: float = 0.0,
    rotate_x: float = 0.0,
    rotate_y: float = 0.0,
    translate_to_origin: bool = True,
) -> dict:
    """Create a transformed STL copy under U1_OUTPUT_DIR/transformed."""
    config = Config.from_env()
    source = safe_file(config.model_dir, model, SUPPORTED_MODEL_EXTENSIONS, label="Model")
    if source.suffix.lower() != ".stl":
        raise ConfigurationError("Model transforms currently support STL only")
    angles = _angles(rotate=rotate, rotate_x=rotate_x, rotate_y=rotate_y)
    out_dir = config.output_dir.expanduser().resolve() / "transformed" / f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / f"{source.stem}.transformed.stl"
    metadata = _transform_stl(source, output, angles, translate_to_origin)
    request = {
        "source_model": model,
        "source_path": str(source),
        "output_path": str(output),
        "rotate": angles["rotate"],
        "rotate_x": angles["rotate_x"],
        "rotate_y": angles["rotate_y"],
        "translate_to_origin": translate_to_origin,
        **metadata,
    }
    (out_dir / "transform.json").write_text(json.dumps(request, indent=2), encoding="utf-8")
    return {"status": "ok", **request}


def transform_model_to_path(
    model: str,
    output_dir: Path,
    *,
    rotate: float = 0.0,
    rotate_x: float = 0.0,
    rotate_y: float = 0.0,
    translate_to_origin: bool = True,
) -> dict:
    """Internal helper for slice workflows that need a transformed STL path."""
    config = Config.from_env()
    source = safe_file(config.model_dir, model, SUPPORTED_MODEL_EXTENSIONS, label="Model")
    if source.suffix.lower() != ".stl":
        raise ConfigurationError("Model transforms currently support STL only")
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"{source.stem}.transformed.stl"
    angles = _angles(rotate=rotate, rotate_x=rotate_x, rotate_y=rotate_y)
    metadata = _transform_stl(source, output, angles, translate_to_origin)
    request = {
        "source_model": model,
        "source_path": str(source),
        "output_path": str(output),
        "rotate": angles["rotate"],
        "rotate_x": angles["rotate_x"],
        "rotate_y": angles["rotate_y"],
        "translate_to_origin": translate_to_origin,
        **metadata,
    }
    (output_dir / "transform.json").write_text(json.dumps(request, indent=2), encoding="utf-8")
    return request


def _angles(**values: float) -> dict[str, float]:
    result = {}
    for key, value in values.items():
        try:
            angle = float(value or 0.0)
        except (TypeError, ValueError):
            raise ConfigurationError(f"{key} must be a number of degrees") from None
        if not -360 <= angle <= 360:
            raise ConfigurationError(f"{key} must be between -360 and 360 degrees")
        result[key] = angle
    return result


def _transform_stl(source: Path, output: Path, angles: dict[str, float], translate_to_origin: bool) -> dict:
    data = source.read_bytes()
    if _looks_binary_stl(data):
        return _transform_binary_stl(data, output, angles, translate_to_origin)
    return _transform_ascii_stl(data.decode("utf-8", errors="replace"), output, angles, translate_to_origin)


def _looks_binary_stl(data: bytes) -> bool:
    if len(data) < 84:
        return False
    count = struct.unpack_from("<I", data, 80)[0]
    return 84 + count * 50 == len(data)


def _transform_binary_stl(data: bytes, output: Path, angles: dict[str, float], translate_to_origin: bool) -> dict:
    count = struct.unpack_from("<I", data, 80)[0]
    triangles = []
    all_vertices = []
    offset = 84
    for _ in range(count):
        normal = struct.unpack_from("<fff", data, offset)
        offset += 12
        vertices = []
        for _vertex in range(3):
            point = _rotate_point(struct.unpack_from("<fff", data, offset), angles)
            vertices.append(point)
            all_vertices.append(point)
            offset += 12
        attr = struct.unpack_from("<H", data, offset)[0]
        offset += 2
        triangles.append((normal, vertices, attr))
    triangles, all_vertices = _translate_triangles(triangles, all_vertices, translate_to_origin)
    header = b"snapmaker-u1-mcp transformed STL"[:80].ljust(80, b" ")
    out = bytearray(header)
    out.extend(struct.pack("<I", count))
    for _normal, vertices, attr in triangles:
        normal = _triangle_normal(vertices)
        out.extend(struct.pack("<fff", *normal))
        for point in vertices:
            out.extend(struct.pack("<fff", *point))
        out.extend(struct.pack("<H", attr))
    output.write_bytes(out)
    return _metadata(all_vertices, count)


def _transform_ascii_stl(text: str, output: Path, angles: dict[str, float], translate_to_origin: bool) -> dict:
    lines = text.splitlines()
    vertices = []
    transformed_by_line: dict[int, tuple[float, float, float]] = {}
    for index, line in enumerate(lines):
        parts = line.strip().split()
        if len(parts) == 4 and parts[0] == "vertex":
            try:
                point = _rotate_point((float(parts[1]), float(parts[2]), float(parts[3])), angles)
            except ValueError:
                continue
            transformed_by_line[index] = point
            vertices.append(point)
    if translate_to_origin and vertices:
        min_x = min(p[0] for p in vertices)
        min_y = min(p[1] for p in vertices)
        min_z = min(p[2] for p in vertices)
        vertices = [(p[0] - min_x, p[1] - min_y, p[2] - min_z) for p in vertices]
        for line_index, point in list(transformed_by_line.items()):
            transformed_by_line[line_index] = (point[0] - min_x, point[1] - min_y, point[2] - min_z)
    out_lines = []
    for index, line in enumerate(lines):
        if index in transformed_by_line:
            x, y, z = transformed_by_line[index]
            prefix = line[: len(line) - len(line.lstrip())]
            out_lines.append(f"{prefix}vertex {x:.6f} {y:.6f} {z:.6f}")
        else:
            out_lines.append(line)
    output.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    return _metadata(vertices, sum(1 for line in lines if line.strip().startswith("facet normal")) or None)


def _rotate_point(point: tuple[float, float, float], angles: dict[str, float]) -> tuple[float, float, float]:
    x, y, z = point
    rx = math.radians(angles["rotate_x"])
    ry = math.radians(angles["rotate_y"])
    rz = math.radians(angles["rotate"])
    if rx:
        y, z = y * math.cos(rx) - z * math.sin(rx), y * math.sin(rx) + z * math.cos(rx)
    if ry:
        x, z = x * math.cos(ry) + z * math.sin(ry), -x * math.sin(ry) + z * math.cos(ry)
    if rz:
        x, y = x * math.cos(rz) - y * math.sin(rz), x * math.sin(rz) + y * math.cos(rz)
    return (x, y, z)


def _translate_triangles(triangles, vertices, translate_to_origin: bool):
    if not translate_to_origin or not vertices:
        return triangles, vertices
    min_x = min(p[0] for p in vertices)
    min_y = min(p[1] for p in vertices)
    min_z = min(p[2] for p in vertices)
    def translate(point):
        return (point[0] - min_x, point[1] - min_y, point[2] - min_z)
    translated = []
    all_vertices = []
    for normal, points, attr in triangles:
        new_points = [translate(point) for point in points]
        translated.append((normal, new_points, attr))
        all_vertices.extend(new_points)
    return translated, all_vertices


def _triangle_normal(vertices: list[tuple[float, float, float]]) -> tuple[float, float, float]:
    a, b, c = vertices
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    if length == 0:
        return (0.0, 0.0, 0.0)
    return (nx / length, ny / length, nz / length)


def _metadata(vertices: list[tuple[float, float, float]], facet_count: int | None) -> dict:
    if not vertices:
        return {"facet_count": facet_count, "dimensions": None, "bounding_box": None}
    xs, ys, zs = zip(*vertices)
    bbox = {"min": {"x": min(xs), "y": min(ys), "z": min(zs)}, "max": {"x": max(xs), "y": max(ys), "z": max(zs)}}
    return {
        "facet_count": facet_count,
        "dimensions": {"x": bbox["max"]["x"] - bbox["min"]["x"], "y": bbox["max"]["y"] - bbox["min"]["y"], "z": bbox["max"]["z"] - bbox["min"]["z"]},
        "bounding_box": bbox,
    }
