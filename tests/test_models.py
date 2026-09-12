import struct
import zipfile

import pytest

from snapmaker_u1_mcp.errors import ConfigurationError
from snapmaker_u1_mcp.models import u1_inspect_model


def test_inspect_ascii_stl(tmp_path, monkeypatch):
    models = tmp_path / "models"
    models.mkdir()
    (models / "cube.stl").write_text("""solid cube
facet normal 0 0 1
 outer loop
  vertex 0 0 0
  vertex 10 0 0
  vertex 0 20 30
 endloop
endfacet
endsolid cube
""", encoding="utf-8")
    monkeypatch.setenv("U1_MODEL_DIR", str(models))
    monkeypatch.delenv("SNAPMAKER_ORCA_BIN", raising=False)
    monkeypatch.delenv("SNAPMAKER_ORCA_APPIMAGE", raising=False)

    result = u1_inspect_model("cube.stl")

    assert result["type"] == "stl"
    assert result["valid_mesh"] is True
    assert result["dimensions"] == {"x": 10.0, "y": 20.0, "z": 30.0}
    assert result["facet_count"] == 1
    assert result["fits_u1_build_volume"] is True


def test_inspect_binary_stl(tmp_path, monkeypatch):
    models = tmp_path / "models"
    models.mkdir()
    header = b"binary stl" + b" " * (80 - len("binary stl"))
    facet_count = struct.pack("<I", 1)
    normal = struct.pack("<fff", 0, 0, 1)
    vertices = struct.pack("<fffffffff", 0, 0, 0, 1, 0, 0, 0, 2, 3)
    (models / "tri.stl").write_bytes(header + facet_count + normal + vertices + struct.pack("<H", 0))
    monkeypatch.setenv("U1_MODEL_DIR", str(models))

    result = u1_inspect_model("tri.stl")

    assert result["dimensions"] == {"x": 1.0, "y": 2.0, "z": 3.0}
    assert result["facet_count"] == 1


def test_inspect_3mf(tmp_path, monkeypatch):
    models = tmp_path / "models"
    models.mkdir()
    model_xml = """<?xml version='1.0' encoding='UTF-8'?>
<model xmlns='http://schemas.microsoft.com/3dmanufacturing/core/2015/02'>
 <resources>
  <object id='1' type='model'>
   <mesh>
    <vertices>
     <vertex x='0' y='0' z='0'/>
     <vertex x='5' y='0' z='0'/>
     <vertex x='0' y='6' z='7'/>
    </vertices>
    <triangles><triangle v1='0' v2='1' v3='2'/></triangles>
   </mesh>
  </object>
 </resources>
</model>
"""
    with zipfile.ZipFile(models / "part.3mf", "w") as zf:
        zf.writestr("3D/3dmodel.model", model_xml)
    monkeypatch.setenv("U1_MODEL_DIR", str(models))

    result = u1_inspect_model("part.3mf")

    assert result["type"] == "3mf"
    assert result["dimensions"] == {"x": 5.0, "y": 6.0, "z": 7.0}
    assert result["facet_count"] == 1
    assert result["body_count"] == 1


def test_inspect_model_rejects_escape_and_extension(tmp_path, monkeypatch):
    models = tmp_path / "models"
    models.mkdir()
    (tmp_path / "outside.stl").write_text("solid\n", encoding="utf-8")
    (models / "bad.txt").write_text("x", encoding="utf-8")
    monkeypatch.setenv("U1_MODEL_DIR", str(models))

    with pytest.raises(ConfigurationError):
        u1_inspect_model("../outside.stl")
    with pytest.raises(ConfigurationError):
        u1_inspect_model("bad.txt")


def test_inspect_oversized_model_warns(tmp_path, monkeypatch):
    models = tmp_path / "models"
    models.mkdir()
    (models / "huge.stl").write_text("""solid huge
facet normal 0 0 1
 outer loop
  vertex 0 0 0
  vertex 300 0 0
  vertex 0 300 300
 endloop
endfacet
endsolid huge
""", encoding="utf-8")
    monkeypatch.setenv("U1_MODEL_DIR", str(models))

    result = u1_inspect_model("huge.stl")

    assert result["fits_u1_build_volume"] is False
    assert result["warnings"]
