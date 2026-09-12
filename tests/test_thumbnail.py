from pathlib import Path

import pytest

from snapmaker_u1_mcp.errors import ConfigurationError
from snapmaker_u1_mcp.thumbnail import THUMBNAIL_BEGIN, THUMBNAIL_END, u1_inject_thumbnail


def write_model(path: Path):
    path.write_text("""solid cube
facet normal 0 0 1
 outer loop
  vertex 0 0 0
  vertex 10 0 0
  vertex 0 20 30
 endloop
endfacet
endsolid cube
""", encoding="utf-8")


def test_inject_thumbnail_creates_copy_and_preserves_motion(tmp_path, monkeypatch):
    models = tmp_path / "models"
    output = tmp_path / "output"
    run = output / "run1"
    models.mkdir(); run.mkdir(parents=True)
    write_model(models / "cube.stl")
    source = run / "plate_1.gcode"
    source.write_text("; header\nG28\nG1 X1 Y2 E3\n; footer\n", encoding="utf-8")
    monkeypatch.setenv("U1_MODEL_DIR", str(models))
    monkeypatch.setenv("U1_OUTPUT_DIR", str(output))

    result = u1_inject_thumbnail("run1/plate_1.gcode", "cube.stl")

    assert result["status"] == "ok"
    assert result["motion_unchanged"] is True
    out = Path(result["output_gcode"])
    assert out != source
    assert source.read_text(encoding="utf-8") == "; header\nG28\nG1 X1 Y2 E3\n; footer\n"
    text = out.read_text(encoding="utf-8")
    assert THUMBNAIL_BEGIN in text
    assert THUMBNAIL_END in text
    assert [l for l in text.splitlines() if l and not l.startswith(";")] == ["G28", "G1 X1 Y2 E3"]


def test_inject_thumbnail_replaces_existing_block(tmp_path, monkeypatch):
    models = tmp_path / "models"
    output = tmp_path / "output"
    models.mkdir(); output.mkdir()
    write_model(models / "cube.stl")
    source = output / "plate.gcode"
    source.write_text(f"{THUMBNAIL_BEGIN}\n; thumbnail: old\n{THUMBNAIL_END}\nG28\n", encoding="utf-8")
    monkeypatch.setenv("U1_MODEL_DIR", str(models))
    monkeypatch.setenv("U1_OUTPUT_DIR", str(output))

    result = u1_inject_thumbnail("plate.gcode", "cube.stl")
    text = Path(result["output_gcode"]).read_text(encoding="utf-8")

    assert text.count(THUMBNAIL_BEGIN) == 1
    assert "old" not in text
    assert "G28" in text


def test_inject_thumbnail_rejects_path_escape(tmp_path, monkeypatch):
    output = tmp_path / "output"
    output.mkdir()
    (tmp_path / "outside.gcode").write_text("G28\n", encoding="utf-8")
    monkeypatch.setenv("U1_OUTPUT_DIR", str(output))

    with pytest.raises(ConfigurationError):
        u1_inject_thumbnail("../outside.gcode", "cube.stl")
