import zipfile

from snapmaker_u1_mcp.models import u1_inspect_model, u1_multimaterial_readiness


def test_multimaterial_readiness_without_model():
    result = u1_multimaterial_readiness()

    assert result["status"] == "ok"
    assert result["supported"] is False
    assert result["mode"] == "single-material-only"


def test_inspect_3mf_multiple_bodies_warns_single_material(tmp_path, monkeypatch):
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    model_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">
  <resources>
    <object id="1" type="model"><mesh><vertices><vertex x="0" y="0" z="0"/><vertex x="1" y="0" z="0"/><vertex x="0" y="1" z="0"/></vertices><triangles><triangle v1="0" v2="1" v3="2"/></triangles></mesh></object>
    <object id="2" type="model"><mesh><vertices><vertex x="0" y="0" z="1"/><vertex x="1" y="0" z="1"/><vertex x="0" y="1" z="1"/></vertices><triangles><triangle v1="0" v2="1" v3="2"/></triangles></mesh></object>
  </resources>
  <build><item objectid="1"/><item objectid="2"/></build>
</model>'''
    with zipfile.ZipFile(model_dir / "multi.3mf", "w") as archive:
        archive.writestr("3D/3dmodel.model", model_xml)
    monkeypatch.setenv("U1_MODEL_DIR", str(model_dir))
    monkeypatch.delenv("SNAPMAKER_ORCA_BIN", raising=False)
    monkeypatch.delenv("SNAPMAKER_ORCA_APPIMAGE", raising=False)

    inspection = u1_inspect_model("multi.3mf")
    readiness = u1_multimaterial_readiness("multi.3mf")

    assert inspection["body_count"] == 2
    assert inspection["single_material_ready"] is False
    assert readiness["supported"] is False
    assert readiness["warnings"]
