import json
from pathlib import Path

from snapmaker_u1_mcp import server
from snapmaker_u1_mcp.models import u1_mesh_printability
from snapmaker_u1_mcp.recipes import u1_compare_recipes, u1_get_recipe, u1_list_recipes
from snapmaker_u1_mcp.reports import u1_export_run_report, u1_export_runs_report, u1_search_runs


def write_profile(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_recipes_available():
    recipes = u1_list_recipes()
    assert recipes["status"] == "ok"
    assert "pla-draft" in recipes["recipes"]
    assert u1_get_recipe("petg-strong")["overrides"]["wall_loops"] == 5


def test_compare_recipes_builds_variants(monkeypatch):
    captured = {}

    def fake_compare(**kwargs):
        captured.update(kwargs)
        return {"status": "ok", "variants": [], "table": ""}

    monkeypatch.setattr("snapmaker_u1_mcp.slicer.u1_compare_slices", fake_compare)

    result = u1_compare_recipes("part.stl", "process", "PLA", ["pla-draft", "pla-strong"])

    assert result["status"] == "ok"
    assert result["recipe_comparison"] is True
    assert [variant["name"] for variant in captured["variants"]] == ["pla-draft", "pla-strong"]


def test_profile_chain_and_diff(tmp_path, monkeypatch):
    root = tmp_path / "profiles" / "process"
    write_profile(root / "base.json", {"name": "base", "type": "process", "layer_height": "0.2", "wall_loops": "2"})
    write_profile(root / "child.json", {"name": "child", "type": "process", "inherits": "base", "wall_loops": "3"})
    monkeypatch.setenv("SNAPMAKER_PROFILE_DIR", str(tmp_path / "profiles"))
    monkeypatch.delenv("SNAPMAKER_ORCA_BIN", raising=False)
    monkeypatch.delenv("SNAPMAKER_ORCA_APPIMAGE", raising=False)

    chain = server.profile_source_chain("child", "process")
    diff = server.diff_profiles("base", "child", "process")

    assert [item["name"] for item in chain["chain"]] == ["child", "base"]
    assert diff["changed"]["wall_loops"] == {"left": "2", "right": "3"}


def test_search_and_export_run_report(tmp_path, monkeypatch):
    run = tmp_path / "20260912-100000-aaaaaaaa"
    run.mkdir()
    (run / "request.json").write_text(json.dumps({"model": "part.stl", "process": "p", "filament": "PLA", "nozzle": 0.4}), encoding="utf-8")
    (run / "analysis.json").write_text(json.dumps({"warnings": [], "estimated_print_time": "1m", "filament_weight": "1", "layer_count": 1}), encoding="utf-8")
    (run / "stdout.log").write_text("", encoding="utf-8")
    (run / "plate_1.gcode").write_text("G1 X1\n", encoding="utf-8")
    monkeypatch.setenv("U1_OUTPUT_DIR", str(tmp_path))

    found = u1_search_runs(model="part")
    report = u1_export_run_report("20260912-100000-aaaaaaaa")
    comparison = u1_export_runs_report(["20260912-100000-aaaaaaaa"], name="one-run")

    assert len(found["runs"]) == 1
    assert Path(report["report"]).exists()
    assert Path(comparison["report"]).exists()


def test_mesh_printability_basic(tmp_path, monkeypatch):
    models = tmp_path / "models"
    models.mkdir()
    (models / "part.stl").write_text("""solid p
facet normal 0 0 -1
 outer loop
  vertex 0 0 1
  vertex 0 1 1
  vertex 1 0 1
 endloop
endfacet
endsolid p
""", encoding="utf-8")
    monkeypatch.setenv("U1_MODEL_DIR", str(models))

    result = u1_mesh_printability("part.stl")

    assert result["status"] == "ok"
    assert result["triangle_count"] == 1
    assert result["downward_overhang_triangles"] == 1
