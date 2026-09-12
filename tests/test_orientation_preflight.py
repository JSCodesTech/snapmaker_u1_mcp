import struct

from snapmaker_u1_mcp.models import u1_orientation_preflight


def write_binary_stl(path, points):
    triangles = [points[:3]]
    data = bytearray(b"unit-test" + b" " * 71)
    data.extend(struct.pack("<I", len(triangles)))
    for tri in triangles:
        data.extend(struct.pack("<fff", 0.0, 0.0, 1.0))
        for point in tri:
            data.extend(struct.pack("<fff", *point))
        data.extend(struct.pack("<H", 0))
    path.write_bytes(data)


def test_orientation_preflight_returns_candidates_and_recommendation(tmp_path, monkeypatch):
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    write_binary_stl(model_dir / "part.stl", [(0, 0, 0), (10, 0, 0), (0, 20, 30)])
    monkeypatch.setenv("U1_MODEL_DIR", str(model_dir))
    monkeypatch.delenv("SNAPMAKER_ORCA_BIN", raising=False)
    monkeypatch.delenv("SNAPMAKER_ORCA_APPIMAGE", raising=False)

    result = u1_orientation_preflight("part.stl")

    assert result["status"] == "ok"
    assert result["recommended"] == "as-loaded"
    assert [item["name"] for item in result["candidates"]] == [
        "as-loaded",
        "rotate-x-90",
        "rotate-y-90",
        "rotate-z-90",
    ]
    assert result["candidates"][0]["cli_rotation_risk"] is False
    assert result["candidates"][1]["cli_orientation"] == {"rotate_x": 90}
    assert "segfault" in result["warnings"][0]


def test_orientation_preflight_warns_when_no_candidate_fits(tmp_path, monkeypatch):
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    write_binary_stl(model_dir / "huge.stl", [(0, 0, 0), (500, 0, 0), (0, 400, 300)])
    monkeypatch.setenv("U1_MODEL_DIR", str(model_dir))
    monkeypatch.delenv("SNAPMAKER_ORCA_BIN", raising=False)
    monkeypatch.delenv("SNAPMAKER_ORCA_APPIMAGE", raising=False)

    result = u1_orientation_preflight("huge.stl")

    assert result["status"] == "warning"
    assert result["recommended"] is None
    assert any("No simple" in warning for warning in result["warnings"])
