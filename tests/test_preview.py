from pathlib import Path

import pytest

from snapmaker_u1_mcp.preview import u1_render_preview, u1_render_preview_bundle


def test_render_preview_creates_svg(tmp_path, monkeypatch):
    models = tmp_path / "models"
    output = tmp_path / "output"
    models.mkdir()
    output.mkdir()
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
    monkeypatch.setenv("U1_OUTPUT_DIR", str(output))

    result = u1_render_preview("cube.stl", "summary")

    assert result["status"] == "ok"
    path = Path(result["preview"])
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert text.startswith("<svg")
    assert "Dimensions: X 10.00 mm" in text
    assert "Dashed outline: U1" in text
    assert result["inspection"]["dimensions"]["z"] == 30.0


def test_render_preview_bundle_creates_all_views(tmp_path, monkeypatch):
    models = tmp_path / "models"
    output = tmp_path / "output"
    models.mkdir()
    output.mkdir()
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
    monkeypatch.setenv("U1_OUTPUT_DIR", str(output))

    result = u1_render_preview_bundle("cube.stl")

    assert result["status"] == "ok"
    assert set(result["views"]) == {"summary", "top", "front", "side"}
    assert all(Path(path).exists() for path in result["views"].values())


def test_render_preview_rejects_bad_view(tmp_path, monkeypatch):
    models = tmp_path / "models"
    models.mkdir()
    monkeypatch.setenv("U1_MODEL_DIR", str(models))

    with pytest.raises(ValueError):
        u1_render_preview("cube.stl", "diagonal")
