import json
from pathlib import Path

import pytest

from snapmaker_u1_mcp.errors import ProfileError
from snapmaker_u1_mcp.profiles import ProfileSelection, ProfileStore, discover_profile_roots, validate_profiles


def write_profile(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def make_valid_profiles():
    machine = {
        "name": "Snapmaker U1 (0.4 nozzle)",
        "type": "machine",
        "printer_model": "Snapmaker U1",
        "nozzle_diameter": ["0.4"],
    }
    process = {
        "name": "0.20 Standard @Snapmaker U1 (0.4 nozzle)",
        "type": "process",
        "layer_height": "0.2",
        "compatible_printers": ["Snapmaker U1 (0.4 nozzle)"],
    }
    filament = {
        "name": "Snapmaker PLA Basic @U1",
        "type": "filament",
        "filament_type": ["PLA"],
        "nozzle_temperature": ["220"],
        "hot_plate_temp": ["60"],
    }
    return machine, process, filament


def test_multi_level_inheritance_and_child_override(tmp_path):
    root = tmp_path / "profiles" / "process"
    write_profile(root / "grand.json", {"name": "grand", "from": "system", "wall_loops": "2"})
    write_profile(root / "parent.json", {"name": "parent", "inherits": "grand", "layer_height": "0.2"})
    write_profile(root / "child.json", {"name": "child", "inherits": "parent", "wall_loops": "4"})

    resolved = ProfileStore([tmp_path / "profiles"]).resolve_profile("child", "process")

    assert resolved["layer_height"] == "0.2"
    assert resolved["wall_loops"] == "4"
    assert resolved["from"] == "system"


def test_missing_parent_fails_clearly(tmp_path):
    root = tmp_path / "profiles" / "process"
    write_profile(root / "child.json", {"name": "child", "inherits": "missing"})

    with pytest.raises(ProfileError, match="not found"):
        ProfileStore([tmp_path / "profiles"]).resolve_profile("child", "process")


def test_invalid_profile_type_rejected(tmp_path):
    with pytest.raises(ProfileError):
        ProfileStore([tmp_path]).list_profiles("bad")


def test_list_profiles_filters_to_u1_snapmaker(tmp_path):
    root = tmp_path / "profiles"
    machine, process, filament = make_valid_profiles()
    write_profile(root / "Snapmaker" / "machine" / "u1.json", machine)
    write_profile(root / "OtherVendor" / "machine" / "other.json", {"name": "Other U1", "type": "machine"})
    write_profile(root / "Snapmaker" / "process" / "std.json", process)
    write_profile(root / "Snapmaker" / "filament" / "pla.json", filament)

    result = ProfileStore([root]).list_profiles(nozzle=0.4, material="PLA", layer_height=0.2)

    assert [p.name for p in result["machine"]] == ["Snapmaker U1 (0.4 nozzle)"]
    assert [p.name for p in result["process"]] == ["0.20 Standard @Snapmaker U1 (0.4 nozzle)"]
    assert [p.name for p in result["filament"]] == ["Snapmaker PLA Basic @U1"]


def test_validate_profiles_success():
    validate_profiles(*make_valid_profiles(), nozzle=0.4)


@pytest.mark.parametrize("mutator,match", [
    (lambda m, p, f: m.update({"printer_model": "Other"}) or m.update({"name": "Other"}), "not Snapmaker U1"),
    (lambda m, p, f: m.update({"nozzle_diameter": ["0.6"]}), "does not support"),
    (lambda m, p, f: p.update({"compatible_printers": ["Snapmaker U1 (0.6 nozzle)"]}), "not compatible"),
    (lambda m, p, f: p.update({"layer_height": "2.0"}), "layer_height"),
    (lambda m, p, f: f.pop("nozzle_temperature"), "nozzle temperature"),
    (lambda m, p, f: f.pop("hot_plate_temp"), "bed temperature"),
])
def test_validate_profiles_rejects_bad_combinations(mutator, match):
    machine, process, filament = make_valid_profiles()
    mutator(machine, process, filament)
    with pytest.raises(ProfileError, match=match):
        validate_profiles(machine, process, filament, 0.4)


def test_validate_selection_returns_profiles(tmp_path):
    root = tmp_path / "profiles"
    machine, process, filament = make_valid_profiles()
    write_profile(root / "machine" / "u1.json", machine)
    write_profile(root / "process" / "std.json", process)
    write_profile(root / "filament" / "pla.json", filament)

    profiles = ProfileStore([root]).validate_selection(ProfileSelection(
        machine_name=machine["name"],
        process_name=process["name"],
        filament_name=filament["name"],
        nozzle=0.4,
    ))

    assert profiles["machine"]["name"] == machine["name"]
    assert profiles["process"]["name"] == process["name"]
    assert profiles["filament"]["name"] == filament["name"]


def test_discover_profile_roots_from_configured_and_binary(tmp_path):
    configured = tmp_path / "configured"
    relative = tmp_path / "install" / "resources" / "profiles"
    configured.mkdir()
    relative.mkdir(parents=True)
    binary = tmp_path / "install" / "AppRun"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")

    roots = discover_profile_roots(configured, binary)

    assert configured.resolve() in roots
    assert relative.resolve() in roots
