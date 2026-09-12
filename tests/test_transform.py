import json
import struct
from pathlib import Path
import zipfile

import pytest

from snapmaker_u1_mcp import slicer
from snapmaker_u1_mcp.transform import u1_transform_model


def write_binary_stl(path: Path, points):
    data = bytearray(b"transform-test" + b" " * 66)
    data.extend(struct.pack("<I", 1))
    data.extend(struct.pack("<fff", 0.0, 0.0, 1.0))
    for point in points:
        data.extend(struct.pack("<fff", *point))
    data.extend(struct.pack("<H", 0))
    path.write_bytes(data)


def test_transform_model_rotates_stl_under_output_dir(tmp_path, monkeypatch):
    model_dir = tmp_path / "models"
    output_dir = tmp_path / "output"
    model_dir.mkdir()
    output_dir.mkdir()
    write_binary_stl(model_dir / "part.stl", [(0, 0, 0), (10, 0, 0), (0, 20, 0)])
    monkeypatch.setenv("U1_MODEL_DIR", str(model_dir))
    monkeypatch.setenv("U1_OUTPUT_DIR", str(output_dir))

    result = u1_transform_model("part.stl", rotate=90)

    assert result["status"] == "ok"
    assert result["rotate"] == 90.0
    output = Path(result["output_path"])
    assert output.exists()
    assert output.is_relative_to(output_dir.resolve())
    assert result["dimensions"]["x"] == pytest.approx(20.0)
    assert result["dimensions"]["y"] == pytest.approx(10.0)
    assert (output.parent / "transform.json").exists()


def test_transform_model_rotates_3mf_under_output_dir(tmp_path, monkeypatch):
    model_dir = tmp_path / "models"
    output_dir = tmp_path / "output"
    model_dir.mkdir()
    output_dir.mkdir()
    model_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">
  <resources><object id="1" type="model"><mesh><vertices>
    <vertex x="0" y="0" z="0"/><vertex x="10" y="0" z="0"/><vertex x="0" y="20" z="0"/>
  </vertices><triangles><triangle v1="0" v2="1" v3="2"/></triangles></mesh></object></resources>
  <build><item objectid="1"/></build>
</model>'''
    with zipfile.ZipFile(model_dir / "part.3mf", "w") as archive:
        archive.writestr("3D/3dmodel.model", model_xml)
    monkeypatch.setenv("U1_MODEL_DIR", str(model_dir))
    monkeypatch.setenv("U1_OUTPUT_DIR", str(output_dir))

    result = u1_transform_model("part.3mf", rotate=90)

    assert result["status"] == "ok"
    assert Path(result["output_path"]).suffix == ".3mf"
    assert result["dimensions"]["x"] == pytest.approx(20.0)
    assert result["dimensions"]["y"] == pytest.approx(10.0)


def test_compare_transformed_orientations_uses_transformed_paths(tmp_path, monkeypatch):
    model_dir = tmp_path / "models"
    output_dir = tmp_path / "output"
    model_dir.mkdir()
    output_dir.mkdir()
    write_binary_stl(model_dir / "part.stl", [(0, 0, 0), (10, 0, 0), (0, 20, 0)])
    monkeypatch.setenv("U1_MODEL_DIR", str(model_dir))
    monkeypatch.setenv("U1_OUTPUT_DIR", str(output_dir))
    calls = []

    def fake_slice(**kwargs):
        calls.append(kwargs)
        return {
            "status": "ok",
            "run_dir": str(output_dir / "run"),
            "gcode": str(output_dir / "run" / "plate_1.gcode"),
            "returncode": 0,
            "overrides": {},
            "analysis": {"estimated_print_time": "1m", "filament_weight": "1", "filament_length": "10", "layer_count": 1, "warnings": []},
        }

    monkeypatch.setattr(slicer, "_u1_slice_model_path", fake_slice)

    result = slicer.u1_compare_transformed_orientations(
        "part.stl",
        "process",
        "filament",
        orientations=[{"name": "flat"}, {"name": "z90", "rotate": 90}],
    )

    assert result["status"] == "ok"
    assert result["local_mesh_transform"] is True
    assert len(calls) == 2
    assert calls[0]["orientation"] is None
    assert calls[0]["model_path"].name == "part.transformed.stl"
    assert result["variants"][1]["transform"]["rotate"] == 90.0
