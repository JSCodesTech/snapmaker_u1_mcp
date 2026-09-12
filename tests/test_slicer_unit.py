import json
import subprocess
from pathlib import Path

import pytest

from snapmaker_u1_mcp.errors import ConfigurationError
from snapmaker_u1_mcp import slicer


def write_profile(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def make_env(tmp_path, monkeypatch):
    model_dir = tmp_path / "models"
    output_dir = tmp_path / "runs"
    profile_dir = tmp_path / "profiles"
    model_dir.mkdir()
    output_dir.mkdir()
    (model_dir / "part.stl").write_text("solid test\nendsolid test\n", encoding="utf-8")
    binary = tmp_path / "AppRun"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)
    monkeypatch.setenv("SNAPMAKER_ORCA_BIN", str(binary))
    monkeypatch.setenv("SNAPMAKER_PROFILE_DIR", str(profile_dir))
    monkeypatch.setenv("U1_MODEL_DIR", str(model_dir))
    monkeypatch.setenv("U1_OUTPUT_DIR", str(output_dir))
    return model_dir, output_dir, profile_dir, binary


def write_valid_profiles(profile_dir: Path):
    write_profile(profile_dir / "machine" / "u1.json", {
        "name": "Snapmaker U1 (0.4 nozzle)",
        "type": "machine",
        "from": "system",
        "printer_model": "Snapmaker U1",
        "nozzle_diameter": ["0.4"],
    })
    write_profile(profile_dir / "process" / "std.json", {
        "name": "0.20 Standard @Snapmaker U1 (0.4 nozzle)",
        "type": "process",
        "from": "system",
        "layer_height": "0.2",
        "wall_loops": "2",
        "sparse_infill_density": "15%",
        "compatible_printers": ["Snapmaker U1 (0.4 nozzle)"],
    })
    write_profile(profile_dir / "filament" / "pla.json", {
        "name": "Snapmaker PLA Basic @U1",
        "type": "filament",
        "from": "system",
        "filament_type": ["PLA"],
        "nozzle_temperature": ["220"],
        "hot_plate_temp": ["60"],
    })


def test_locate_slicer_direct_bin(tmp_path, monkeypatch):
    binary = tmp_path / "snapmaker-orca"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setenv("SNAPMAKER_ORCA_BIN", str(binary))
    assert slicer.locate_slicer(slicer.Config.from_env()) == binary.resolve()


def test_locate_slicer_missing(monkeypatch):
    monkeypatch.delenv("SNAPMAKER_ORCA_BIN", raising=False)
    monkeypatch.delenv("SNAPMAKER_ORCA_APPIMAGE", raising=False)
    with pytest.raises(ConfigurationError):
        slicer.locate_slicer(slicer.Config.from_env())


def test_list_models_filters_extensions_and_symlink_escape(tmp_path, monkeypatch):
    model_dir = tmp_path / "models"
    outside = tmp_path / "outside.stl"
    model_dir.mkdir()
    (model_dir / "part.stl").write_text("solid\n", encoding="utf-8")
    (model_dir / "part.3mf").write_text("3mf\n", encoding="utf-8")
    (model_dir / "note.txt").write_text("x\n", encoding="utf-8")
    outside.write_text("solid\n", encoding="utf-8")
    (model_dir / "escape.stl").symlink_to(outside)
    monkeypatch.setenv("U1_MODEL_DIR", str(model_dir))

    models = slicer.list_models()

    assert [m["name"] for m in models] == ["part.3mf", "part.stl"]


def test_u1_health_ok(tmp_path, monkeypatch):
    _model_dir, output_dir, profile_dir, binary = make_env(tmp_path, monkeypatch)
    write_valid_profiles(profile_dir)

    def fake_run(cmd, **kwargs):
        assert cmd == [str(binary.resolve()), "--help"]
        return subprocess.CompletedProcess(cmd, 0, stdout="--slice --load-settings --load-filaments --outputdir", stderr="")

    monkeypatch.setattr(slicer.subprocess, "run", fake_run)

    result = slicer.u1_health()

    assert result["status"] == "ok"
    assert result["output_dir_writable"] is True
    assert output_dir.exists()


def test_u1_health_reports_help_failure(tmp_path, monkeypatch):
    _model_dir, _output_dir, profile_dir, binary = make_env(tmp_path, monkeypatch)
    write_valid_profiles(profile_dir)

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 2, stdout="", stderr="bad")

    monkeypatch.setattr(slicer.subprocess, "run", fake_run)

    result = slicer.u1_health()

    assert result["status"] == "error"
    assert result["errors"]


def test_u1_slice_success_with_mocked_subprocess(tmp_path, monkeypatch):
    _model_dir, output_dir, profile_dir, binary = make_env(tmp_path, monkeypatch)
    write_valid_profiles(profile_dir)

    def fake_run(cmd, **kwargs):
        out = Path(cmd[cmd.index("--outputdir") + 1])
        (out / "plate_1.gcode").write_text(
            "; filament_type = PLA\n; estimated printing time: 10m\n; filament used [g] = 1.2\n; LAYER:0\n",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr(slicer.subprocess, "run", fake_run)

    result = slicer.u1_slice(
        "part.stl",
        "0.20 Standard @Snapmaker U1 (0.4 nozzle)",
        "Snapmaker PLA Basic @U1",
        overrides={"wall_loops": 4},
        orientation={"rotate_x": 90},
    )

    assert result["status"] == "ok"
    assert result["overrides"]["wall_loops"]["effective"] == 4
    assert result["orientation"] == {"rotate_x": 90.0}
    assert Path(result["gcode"]).exists()
    assert (Path(result["run_dir"]) / "request.json").exists()
    assert (Path(result["run_dir"]) / "profiles" / "process.json").exists()


def test_u1_slice_failure_reports_stop_condition(tmp_path, monkeypatch):
    _model_dir, _output_dir, profile_dir, _binary = make_env(tmp_path, monkeypatch)
    write_valid_profiles(profile_dir)

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, -11, stdout="segfault-ish", stderr="")

    monkeypatch.setattr(slicer.subprocess, "run", fake_run)

    result = slicer.u1_slice("part.stl", "0.20 Standard @Snapmaker U1 (0.4 nozzle)", "Snapmaker PLA Basic @U1")

    assert result["status"] == "error"
    assert result["stop_condition"]["failure_category"] == "snapmaker_orca_cli_crash"


def test_safe_model_path_rejects_escape_and_extension(tmp_path):
    root = tmp_path / "models"
    root.mkdir()
    (tmp_path / "outside.stl").write_text("solid\n", encoding="utf-8")
    (root / "bad.txt").write_text("x\n", encoding="utf-8")

    with pytest.raises(ConfigurationError):
        slicer._safe_model_path(root, "../outside.stl")
    with pytest.raises(ConfigurationError):
        slicer._safe_model_path(root, "bad.txt")


def test_classify_failure_categories():
    assert slicer._classify_failure(139, "", "") == "snapmaker_orca_cli_crash"
    assert slicer._classify_failure(1, "", "from unsupported") == "profile_runtime_format"
    assert slicer._classify_failure(1, "not compatible with printer", "") == "profile_compatibility"
    assert slicer._classify_failure(1, "no g-code file", "") == "slicing_no_output"
    assert slicer._classify_failure(1, "", "") == "unknown"


def test_compare_slices_uses_u1_slice(monkeypatch):
    calls = []

    def fake_slice(**kwargs):
        calls.append(kwargs)
        return {
            "status": "ok",
            "run_dir": f"/runs/{kwargs['process']}",
            "gcode": "/runs/out.gcode",
            "returncode": 0,
            "overrides": {},
            "analysis": {"estimated_print_time": "1m", "filament_weight": "1", "filament_length": "10", "layer_count": 2, "warnings": []},
        }

    monkeypatch.setattr(slicer, "u1_slice", fake_slice)

    result = slicer.u1_compare_slices("part.stl", "PLA", [{"name": "a", "process": "p", "overrides": {}, "orientation": {"rotate": 90}}])

    assert result["status"] == "ok"
    assert "Variant" in result["table"]
    assert calls[0]["model"] == "part.stl"
    assert calls[0]["orientation"] == {"rotate": 90}


def test_compare_orientations_builds_variants(monkeypatch):
    captured = {}

    def fake_compare(**kwargs):
        captured.update(kwargs)
        return {"status": "ok", "variants": [], "table": ""}

    monkeypatch.setattr(slicer, "u1_compare_slices", fake_compare)

    result = slicer.u1_compare_orientations(
        "part.stl",
        "proc",
        "PLA",
        [{"name": "flat"}, {"rotate_x": 90}],
        overrides={"wall_loops": 5},
    )

    assert result["status"] == "ok"
    assert result["orientation_experiment"] is True
    assert captured["variants"][0]["name"] == "flat"
    assert captured["variants"][1]["orientation"] == {"rotate_x": 90}


def test_orientation_args_validation():
    args, report = slicer._orientation_args({"rotate": 90, "rotate_x": "180", "name": "x"})
    assert args == ["--rotate", "90", "--rotate-x", "180"]
    assert report == {"rotate": 90.0, "rotate_x": 180.0}
    with pytest.raises(ConfigurationError):
        slicer._orientation_args({"bad": 1})
    with pytest.raises(ConfigurationError):
        slicer._orientation_args({"rotate": 999})
