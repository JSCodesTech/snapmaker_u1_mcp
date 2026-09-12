import json
import sys

import pytest

from snapmaker_u1_mcp import server


def test_list_profiles_filtered_without_binary(tmp_path, monkeypatch):
    root = tmp_path / "profiles"
    (root / "machine").mkdir(parents=True)
    (root / "machine" / "u1.json").write_text(json.dumps({
        "name": "Snapmaker U1 (0.4 nozzle)",
        "type": "machine",
        "printer_model": "Snapmaker U1",
        "nozzle_diameter": ["0.4"],
    }), encoding="utf-8")
    monkeypatch.setenv("SNAPMAKER_PROFILE_DIR", str(root))
    monkeypatch.delenv("SNAPMAKER_ORCA_BIN", raising=False)
    monkeypatch.delenv("SNAPMAKER_ORCA_APPIMAGE", raising=False)

    result = server.list_profiles_filtered(nozzle=0.4)

    assert result["machine"][0] == "Snapmaker U1 (0.4 nozzle)"


def test_main_health_prints_json(monkeypatch, capsys):
    monkeypatch.setattr(server, "u1_health", lambda: {"status": "ok"})
    monkeypatch.setattr(sys, "argv", ["prog", "health"])

    server.main()

    assert json.loads(capsys.readouterr().out)["status"] == "ok"


def test_main_slice_parses_overrides(monkeypatch, capsys):
    captured = {}

    def fake_slice(model, process, filament, nozzle, overrides, orientation=None, verbose=False):
        captured.update({"model": model, "process": process, "filament": filament, "nozzle": nozzle, "overrides": overrides, "orientation": orientation, "verbose": verbose})
        return {"status": "ok"}

    monkeypatch.setattr(server, "slice_model", fake_slice)
    monkeypatch.setattr(sys, "argv", [
        "prog", "slice", "part.stl", "--process", "proc", "--filament", "fil", "--nozzle", "0.6", "--overrides", '{"wall_loops": 5}', "--orientation", '{"rotate_x": 90}'
    ])

    server.main()

    assert json.loads(capsys.readouterr().out)["status"] == "ok"
    assert captured["overrides"] == {"wall_loops": 5}
    assert captured["nozzle"] == 0.6
    assert captured["orientation"] == {"rotate_x": 90}
    assert captured["verbose"] is False


def test_main_compare_parses_variants(monkeypatch, capsys):
    monkeypatch.setattr(server, "compare_slices", lambda model, filament, variants, nozzle, verbose=False: {"variants": variants, "nozzle": nozzle, "verbose": verbose})
    monkeypatch.setattr(sys, "argv", [
        "prog", "compare-slices", "part.stl", "--filament", "PLA", "--variants", '[{"name":"a","process":"p"}]'
    ])

    server.main()

    result = json.loads(capsys.readouterr().out)
    assert result["variants"][0]["name"] == "a"
    assert result["nozzle"] == 0.4


def test_main_errors_are_json(monkeypatch, capsys):
    monkeypatch.setattr(server, "u1_health", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(sys, "argv", ["prog", "health"])

    with pytest.raises(SystemExit):
        server.main()

    err = json.loads(capsys.readouterr().err)
    assert err["status"] == "error"
    assert err["error"] == "boom"
