import json
from pathlib import Path

from snapmaker_u1_mcp import server


def write_profile(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def write_valid_profiles(root: Path) -> tuple[dict, dict, dict]:
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
        "wall_loops": "2",
        "compatible_printers": ["Snapmaker U1 (0.4 nozzle)"],
    }
    filament = {
        "name": "Snapmaker PLA Basic @U1",
        "type": "filament",
        "filament_type": ["PLA"],
        "nozzle_temperature": ["220"],
        "hot_plate_temp": ["60"],
    }
    write_profile(root / "machine" / "u1.json", machine)
    write_profile(root / "process" / "std.json", process)
    write_profile(root / "filament" / "pla.json", filament)
    return machine, process, filament


def test_get_profile_detail_returns_resolved_single_profile(tmp_path, monkeypatch):
    root = tmp_path / "profiles"
    _machine, process, _filament = write_valid_profiles(root)
    monkeypatch.setenv("SNAPMAKER_PROFILE_DIR", str(root))
    monkeypatch.delenv("SNAPMAKER_ORCA_BIN", raising=False)
    monkeypatch.delenv("SNAPMAKER_ORCA_APPIMAGE", raising=False)

    result = server.get_profile_detail(process["name"], "process")

    assert result["status"] == "ok"
    assert result["kind"] == "process"
    assert result["name"] == process["name"]
    assert result["profile"]["wall_loops"] == "2"
    assert result["summary"]["layer_height"] == "0.2"


def test_explain_profile_selection_validates_and_summarizes(tmp_path, monkeypatch):
    root = tmp_path / "profiles"
    machine, process, filament = write_valid_profiles(root)
    monkeypatch.setenv("SNAPMAKER_PROFILE_DIR", str(root))
    monkeypatch.delenv("SNAPMAKER_ORCA_BIN", raising=False)
    monkeypatch.delenv("SNAPMAKER_ORCA_APPIMAGE", raising=False)

    result = server.explain_profile_selection(process["name"], filament["name"], 0.4, machine["name"])

    assert result["status"] == "ok"
    assert result["compatible"] is True
    assert result["machine"]["name"] == machine["name"]
    assert result["process"]["layer_height"] == "0.2"
    assert result["filament"]["filament_type"] == ["PLA"]
