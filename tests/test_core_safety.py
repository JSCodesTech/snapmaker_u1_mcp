from pathlib import Path
import json

import pytest

from snapmaker_u1_mcp.overrides import apply_process_overrides
from snapmaker_u1_mcp.profiles import ProfileSelection, ProfileStore, ProfileError
from snapmaker_u1_mcp.slicer import build_slice_command, u1_analyze_gcode, u1_compare_slices


def write_profile(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_profile_resolver_one_level_inheritance(tmp_path):
    root = tmp_path / "profiles" / "process"
    write_profile(root / "base.json", {"name": "base", "layer_height": "0.2", "wall_loops": "2"})
    write_profile(root / "child.json", {"name": "child", "inherits": "base", "wall_loops": "3"})

    resolved = ProfileStore([tmp_path / "profiles"]).resolve_profile("child", "process")

    assert resolved["layer_height"] == "0.2"
    assert resolved["wall_loops"] == "3"
    assert "inherits" not in resolved


def test_profile_resolver_cycle(tmp_path):
    root = tmp_path / "profiles" / "process"
    write_profile(root / "a.json", {"name": "a", "inherits": "b"})
    write_profile(root / "b.json", {"name": "b", "inherits": "a"})

    try:
        ProfileStore([tmp_path / "profiles"]).resolve_profile("a", "process")
    except ProfileError as exc:
        assert "cycle" in str(exc).lower()
    else:
        raise AssertionError("expected ProfileError")


def test_runtime_profile_removes_inheritance_and_wipe_tower_key(tmp_path):
    root = tmp_path / "profiles" / "process"
    write_profile(root / "base.json", {"name": "base", "from": "system", "layer_height": "0.2"})
    write_profile(root / "child.json", {"name": "child", "inherits": "base", "wipe_tower_filament": "0"})

    resolved = ProfileStore([tmp_path / "profiles"]).resolve_profile("child", "process")

    assert "inherits" not in resolved
    assert "wipe_tower_filament" not in resolved
    assert resolved["from"] == "system"


def test_validate_selection_rejects_wrong_nozzle(tmp_path):
    root = tmp_path / "profiles"
    write_profile(root / "machine" / "u1.json", {
        "name": "Snapmaker U1 (0.4 nozzle)",
        "type": "machine",
        "printer_model": "Snapmaker U1",
        "nozzle_diameter": ["0.4"],
    })
    write_profile(root / "process" / "standard.json", {
        "name": "0.20 Standard @Snapmaker U1 (0.6 nozzle)",
        "type": "process",
        "layer_height": "0.2",
        "compatible_printers": ["Snapmaker U1 (0.6 nozzle)"],
    })
    write_profile(root / "filament" / "pla.json", {
        "name": "Snapmaker PLA Basic @U1",
        "type": "filament",
        "filament_type": ["PLA"],
        "nozzle_temperature": ["220"],
        "hot_plate_temp": ["60"],
    })

    try:
        ProfileStore([root]).validate_selection(ProfileSelection(
            machine_name="Snapmaker U1 (0.4 nozzle)",
            process_name="0.20 Standard @Snapmaker U1 (0.6 nozzle)",
            filament_name="Snapmaker PLA Basic @U1",
            nozzle=0.4,
        ))
    except ProfileError as exc:
        assert "not compatible" in str(exc) or "nozzle" in str(exc)
    else:
        raise AssertionError("expected ProfileError")


def test_apply_allowed_process_overrides():
    process = {"wall_loops": "2", "sparse_infill_density": "15%", "enable_support": "0"}

    updated, report = apply_process_overrides(process, {
        "wall_loops": 5,
        "sparse_infill_density": 20,
        "enable_support": True,
    })

    assert updated["wall_loops"] == "5"
    assert updated["sparse_infill_density"] == "20%"
    assert updated["enable_support"] == "1"
    assert report["wall_loops"]["original"] == "2"
    assert report["wall_loops"]["effective"] == 5


def test_reject_disallowed_override():
    try:
        apply_process_overrides({}, {"nozzle_temperature": 260})
    except ProfileError as exc:
        assert "not allowed" in str(exc)
    else:
        raise AssertionError("expected ProfileError")


def test_analyze_gcode_rejects_path_escape(tmp_path, monkeypatch):
    out = tmp_path / "out"
    out.mkdir()
    outside = tmp_path / "outside.gcode"
    outside.write_text("; filament_type = PLA\n", encoding="utf-8")
    monkeypatch.setenv("U1_OUTPUT_DIR", str(out))

    with pytest.raises(Exception) as exc:
        u1_analyze_gcode("../outside.gcode")

    assert "escapes" in str(exc.value)


def test_compare_slices_requires_variants():
    with pytest.raises(Exception) as exc:
        u1_compare_slices("part.stl", "PLA", [])

    assert "variants" in str(exc.value)


def test_build_slice_command_paths_with_spaces():
    cmd = build_slice_command(
        Path("/opt/Snapmaker Orca/orca-slicer"),
        Path("/models/my part.stl"),
        Path("/out/run 1"),
        Path("/out/run 1/profiles/machine.json"),
        Path("/out/run 1/profiles/process.json"),
        Path("/out/run 1/profiles/filament.json"),
    )

    assert cmd[0] == "/opt/Snapmaker Orca/orca-slicer"
    assert "--load-settings" in cmd
    assert "--load-filaments" in cmd
    assert "/models/my part.stl" == cmd[-1]
