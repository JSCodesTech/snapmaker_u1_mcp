import json
from pathlib import Path

import pytest

from snapmaker_u1_mcp import slicer
from snapmaker_u1_mcp.errors import ConfigurationError


def make_run(root: Path, run_id: str, *, ok: bool = True) -> Path:
    run = root / run_id
    run.mkdir(parents=True)
    (run / "request.json").write_text(json.dumps({
        "model": "part.stl",
        "process": "0.20 Standard @Snapmaker U1 (0.4 nozzle)",
        "filament": "Snapmaker PLA Basic @U1",
        "nozzle": 0.4,
        "orientation": {},
    }), encoding="utf-8")
    (run / "analysis.json").write_text(json.dumps({
        "warnings": [] if ok else ["No G-code file was produced"],
        "estimated_print_time": "10m",
        "filament_weight": "1.2",
        "layer_count": 3,
    }), encoding="utf-8")
    (run / "stdout.log").write_text("hello stdout", encoding="utf-8")
    (run / "stderr.log").write_text("hello stderr", encoding="utf-8")
    if ok:
        (run / "plate_1.gcode").write_text("G1 X1\n", encoding="utf-8")
    return run


def test_list_runs_summarizes_recent_runs(tmp_path, monkeypatch):
    monkeypatch.setenv("U1_OUTPUT_DIR", str(tmp_path))
    make_run(tmp_path, "20260912-100000-aaaaaaaa")
    make_run(tmp_path, "20260912-100001-bbbbbbbb", ok=False)
    (tmp_path / "previews").mkdir()

    result = slicer.u1_list_runs(limit=10)

    assert result["status"] == "ok"
    assert [run["run_id"] for run in result["runs"]] == [
        "20260912-100001-bbbbbbbb",
        "20260912-100000-aaaaaaaa",
    ]
    assert result["runs"][0]["status"] == "error"
    assert result["runs"][1]["gcode_count"] == 1


def test_get_run_and_logs_are_safe_and_compact(tmp_path, monkeypatch):
    monkeypatch.setenv("U1_OUTPUT_DIR", str(tmp_path))
    make_run(tmp_path, "20260912-100000-aaaaaaaa")

    run = slicer.u1_get_run("20260912-100000-aaaaaaaa")
    logs = slicer.u1_get_run_logs("20260912-100000-aaaaaaaa", tail=5)

    assert run["status"] == "ok"
    assert run["artifacts"]["request.json"] is True
    assert run["artifacts"]["gcode"] == ["plate_1.gcode"]
    assert logs["stdout_tail"] == "tdout"
    assert logs["stderr_tail"] == "tderr"


def test_run_access_rejects_escape_and_bad_limits(tmp_path, monkeypatch):
    monkeypatch.setenv("U1_OUTPUT_DIR", str(tmp_path))
    with pytest.raises(ConfigurationError):
        slicer.u1_get_run("../bad")
    with pytest.raises(ConfigurationError):
        slicer.u1_list_runs(limit=0)
    with pytest.raises(ConfigurationError):
        slicer.u1_get_run_logs("20260912-100000-aaaaaaaa", tail=99999)


def test_delete_run_requires_confirmation(tmp_path, monkeypatch):
    monkeypatch.setenv("U1_OUTPUT_DIR", str(tmp_path))
    run = make_run(tmp_path, "20260912-100000-aaaaaaaa")

    with pytest.raises(ConfigurationError):
        slicer.u1_delete_run("20260912-100000-aaaaaaaa")

    result = slicer.u1_delete_run("20260912-100000-aaaaaaaa", confirm=True)

    assert result["deleted"] is True
    assert not run.exists()
