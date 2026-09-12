from __future__ import annotations

from pathlib import Path
import json

from .config import Config
from .errors import ConfigurationError
from .slicer import u1_get_run, u1_list_runs, u1_slice


def u1_export_run_report(run_id: str) -> dict:
    run = u1_get_run(run_id)
    run_dir = Path(run["run_dir"])
    report = run_dir / "run-summary.md"
    lines = [
        f"# Slice Run {run_id}",
        "",
        f"- Status: {run.get('status')}",
        f"- Model: {run.get('model')}",
        f"- Process: {run.get('process')}",
        f"- Filament: {run.get('filament')}",
        f"- Nozzle: {run.get('nozzle')}",
        f"- G-code: {run.get('gcode')}",
        f"- Estimated time: {run.get('estimated_print_time')}",
        f"- Filament weight: {run.get('filament_weight')}",
        f"- Layers: {run.get('layer_count')}",
        "",
        "## Warnings",
        "",
    ]
    warnings = run.get("warnings") or []
    lines.extend(f"- {warning}" for warning in warnings) if warnings else lines.append("None")
    lines.append("")
    lines.append("## Artifacts")
    lines.append("")
    for key, value in (run.get("artifacts") or {}).items():
        lines.append(f"- {key}: {value}")
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"status": "ok", "run_id": run_id, "report": str(report)}


def u1_search_runs(model: str | None = None, filament: str | None = None, status: str | None = None, limit: int = 50) -> dict:
    runs = u1_list_runs(limit=100)["runs"]
    def matches(run: dict) -> bool:
        if model and model.lower() not in str(run.get("model") or "").lower():
            return False
        if filament and filament.lower() not in str(run.get("filament") or "").lower():
            return False
        if status and status != run.get("status"):
            return False
        return True
    filtered = [run for run in runs if matches(run)]
    return {"status": "ok", "runs": filtered[:limit]}


def u1_reproduce_run(run_id: str, verbose: bool = False) -> dict:
    config = Config.from_env()
    run = u1_get_run(run_id)
    request_path = Path(run["run_dir"]) / "request.json"
    request = json.loads(request_path.read_text(encoding="utf-8"))
    model = request.get("model")
    if not model or "(transformed)" in str(model):
        raise ConfigurationError("This run cannot be reproduced by model name; transformed/ad-hoc model path detected")
    return u1_slice(
        model=str(model),
        process=str(request["process"]),
        filament=str(request["filament"]),
        nozzle=float(request.get("nozzle", 0.4)),
        overrides=request.get("overrides") or {},
        orientation=request.get("orientation") or None,
        verbose=verbose,
    )
