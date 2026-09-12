import struct

from snapmaker_u1_mcp.models import u1_model_diagnostics


def write_binary_stl(path, points):
    data = bytearray(b"diag-test" + b" " * 71)
    data.extend(struct.pack("<I", 1))
    data.extend(struct.pack("<fff", 0.0, 0.0, 1.0))
    for point in points[:3]:
        data.extend(struct.pack("<fff", *point))
    data.extend(struct.pack("<H", 0))
    path.write_bytes(data)


def test_model_diagnostics_warns_for_tiny_model(tmp_path, monkeypatch):
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    write_binary_stl(model_dir / "tiny.stl", [(0, 0, 0), (1, 0, 0), (0, 1, 0.2)])
    monkeypatch.setenv("U1_MODEL_DIR", str(model_dir))
    monkeypatch.delenv("SNAPMAKER_ORCA_BIN", raising=False)
    monkeypatch.delenv("SNAPMAKER_ORCA_APPIMAGE", raising=False)

    result = u1_model_diagnostics("tiny.stl")

    assert result["status"] == "ok"
    assert any("Very thin" in warning for warning in result["diagnostics"]["warnings"])
    assert any("very small" in warning for warning in result["diagnostics"]["warnings"])


def test_model_diagnostics_reports_oversize_model(tmp_path, monkeypatch):
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    write_binary_stl(model_dir / "huge.stl", [(0, 0, 0), (500, 0, 0), (0, 400, 300)])
    monkeypatch.setenv("U1_MODEL_DIR", str(model_dir))
    monkeypatch.delenv("SNAPMAKER_ORCA_BIN", raising=False)
    monkeypatch.delenv("SNAPMAKER_ORCA_APPIMAGE", raising=False)

    result = u1_model_diagnostics("huge.stl")

    assert result["status"] == "warning"
    assert result["diagnostics"]["errors"]
    assert any("build volume" in error for error in result["diagnostics"]["errors"])
