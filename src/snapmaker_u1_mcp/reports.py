from __future__ import annotations

from pathlib import Path
import json

from .config import Config
from .errors import ConfigurationError
from .gcode import analyze_gcode
from .slicer import u1_get_run, u1_list_runs, u1_slice


def u1_export_run_report(run_id: str) -> dict:
    run = u1_get_run(run_id)
    run_dir = Path(run["run_dir"])
    report = run_dir / "run-summary.md"
    request = _read_json(run_dir / "request.json")
    analysis = _read_json(run_dir / "analysis.json")
    safety = analyze_gcode(Path(run["gcode"]), requested_material=run.get("filament")).get("safety_checks", {}) if run.get("gcode") else {}
    lines = [
        f"# Slice Run {run_id}",
        "",
        "## Summary",
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
        "## Request",
        "",
        "```json",
        json.dumps(request, indent=2, sort_keys=True),
        "```",
        "",
        "## Analysis",
        "",
        "```json",
        json.dumps(analysis, indent=2, sort_keys=True),
        "```",
        "",
        "## Warnings",
        "",
    ]
    warnings = run.get("warnings") or []
    lines.extend(f"- {warning}" for warning in warnings) if warnings else lines.append("None")
    safety_warnings = safety.get("warnings") or []
    if safety_warnings:
        lines.append("")
        lines.append("## Safety checks")
        lines.append("")
        lines.extend(f"- {warning}" for warning in safety_warnings)
    lines.append("")
    lines.append("## Artifacts")
    lines.append("")
    for key, value in (run.get("artifacts") or {}).items():
        lines.append(f"- {key}: {value}")
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"status": "ok", "run_id": run_id, "report": str(report)}


def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def u1_export_runs_report(run_ids: list[str], name: str = "comparison") -> dict:
    if not run_ids:
        raise ConfigurationError("run_ids must be a non-empty list")
    config = Config.from_env()
    out_dir = config.output_dir.expanduser().resolve() / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in name).strip(".-") or "comparison"
    report = out_dir / f"{safe_name}.md"
    runs = [u1_get_run(run_id) for run_id in run_ids]
    lines = [
        f"# Run Comparison: {safe_name}",
        "",
        "| Run | Status | Model | Process | Filament | Time | Filament (g) | Layers |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for run in runs:
        lines.append(
            f"| {run.get('run_id')} | {run.get('status')} | {run.get('model')} | {run.get('process')} | "
            f"{run.get('filament')} | {run.get('estimated_print_time')} | {run.get('filament_weight')} | {run.get('layer_count')} |"
        )
    lines.extend(["", "## Warnings", ""])
    for run in runs:
        warnings = run.get("warnings") or []
        if warnings:
            lines.append(f"### {run.get('run_id')}")
            lines.extend(f"- {warning}" for warning in warnings)
            lines.append("")
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"status": "ok", "report": str(report), "run_ids": run_ids}


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
