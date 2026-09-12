from __future__ import annotations

from pathlib import Path
import json
import os
import re
import shutil
import subprocess
import time
import uuid

from .config import Config
from .errors import ConfigurationError, SlicerError
from .gcode import analyze_gcode
from .orca import HELP_FLAGS_REQUIRED, build_slice_command, classify_failure as _classify_failure, locate_slicer
from .overrides import apply_process_overrides
from .paths import list_allowed_files, new_run_dir as _new_run_dir, safe_file as _safe_output_file, write_json as _write_json
from .profiles import ProfileSelection, ProfileStore, discover_profile_roots

SUPPORTED_MODEL_EXTENSIONS = {".stl", ".3mf"}


def u1_health() -> dict:
    config = Config.from_env()
    response = {
        "status": "error",
        "slicer": "Snapmaker Orca",
        "binary": None,
        "cli_available": False,
        "required_cli_flags": {flag: False for flag in HELP_FLAGS_REQUIRED},
        "profile_roots": [],
        "u1_profiles_found": False,
        "output_dir_writable": False,
        "errors": [],
    }
    try:
        binary = locate_slicer(config)
        response["binary"] = str(binary)
        if not os.access(binary, os.X_OK):
            response["errors"].append(f"Slicer binary is not executable: {binary}")
        help_result = subprocess.run([str(binary), "--help"], shell=False, text=True, capture_output=True, timeout=30)
        help_text = f"{help_result.stdout}\n{help_result.stderr}"
        response["cli_available"] = help_result.returncode == 0
        response["required_cli_flags"] = {flag: flag in help_text for flag in HELP_FLAGS_REQUIRED}
        if help_result.returncode != 0:
            response["errors"].append(f"--help exited with {help_result.returncode}")
        missing = [flag for flag, ok in response["required_cli_flags"].items() if not ok]
        if missing:
            response["errors"].append(f"Expected CLI flags not found in --help output: {missing}")

        roots = discover_profile_roots(config.profile_dir, binary)
        response["profile_roots"] = [str(p) for p in roots]
        store = ProfileStore(roots)
        machines = store.list_profiles("machine")["machine"]
        response["u1_profiles_found"] = bool(machines)
        if not machines:
            response["errors"].append("No Snapmaker U1 machine profiles found")

        config.output_dir.mkdir(parents=True, exist_ok=True)
        test_file = config.output_dir / ".write-test"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink(missing_ok=True)
        response["output_dir_writable"] = True
    except Exception as exc:  # health should report, not raise
        response["errors"].append(str(exc))

    if (
        response["binary"]
        and response["cli_available"]
        and all(response["required_cli_flags"].values())
        and response["u1_profiles_found"]
        and response["output_dir_writable"]
        and not response["errors"]
    ):
        response["status"] = "ok"
    return response


def list_models() -> list[dict]:
    config = Config.from_env()
    return list_allowed_files(config.model_dir, SUPPORTED_MODEL_EXTENSIONS)


def u1_slice(
    model: str,
    process: str,
    filament: str,
    nozzle: float = 0.4,
    overrides: dict | None = None,
    orientation: dict | None = None,
    verbose: bool = False,
) -> dict:
    """Slice a model for Snapmaker U1 using validated single-material profiles."""
    config = Config.from_env()
    model_path = _safe_model_path(config.model_dir, model)
    return _u1_slice_model_path(
        model_label=model,
        model_path=model_path,
        process=process,
        filament=filament,
        nozzle=nozzle,
        overrides=overrides,
        orientation=orientation,
        verbose=verbose,
    )


def _u1_slice_model_path(
    model_label: str,
    model_path: Path,
    process: str,
    filament: str,
    nozzle: float = 0.4,
    overrides: dict | None = None,
    orientation: dict | None = None,
    verbose: bool = False,
) -> dict:
    """Internal slicer for already-validated model paths."""
    config = Config.from_env()
    binary = locate_slicer(config)
    run_dir = _new_run_dir(config.output_dir)
    roots = discover_profile_roots(config.profile_dir, binary)
    store = ProfileStore(roots)
    profiles_dir = run_dir / "profiles"
    profiles_dir.mkdir(parents=True)

    machine_name = f"Snapmaker U1 ({nozzle:g} nozzle)"
    try:
        machine = store.find_profile_path(machine_name, "machine")
        selected_machine = machine_name
    except Exception:
        machines = [p for p in store.list_profiles("machine")["machine"] if f"{nozzle:g}" in (p.nozzle or p.name)]
        if not machines:
            raise SlicerError(f"No Snapmaker U1 machine profile available for {nozzle:g} mm nozzle")
        selected_machine = machines[0].name

    orientation_args, orientation_report = _orientation_args(orientation)
    request = {"model": model_label, "model_path": str(model_path), "machine": selected_machine, "process": process, "filament": filament, "nozzle": nozzle, "overrides": overrides or {}, "orientation": orientation_report}
    (run_dir / "request.json").write_text(json.dumps(request, indent=2), encoding="utf-8")

    profiles = store.validate_selection(ProfileSelection(
        machine_name=selected_machine,
        process_name=process,
        filament_name=filament,
        nozzle=nozzle,
    ))
    process_profile, override_report = apply_process_overrides(profiles["process"], overrides)
    profiles["process"] = process_profile
    _write_json(profiles_dir / "machine.json", profiles["machine"])
    _write_json(profiles_dir / "process.json", profiles["process"])
    _write_json(profiles_dir / "filament.json", profiles["filament"])

    cmd = build_slice_command(binary, model_path, run_dir, profiles_dir / "machine.json", profiles_dir / "process.json", profiles_dir / "filament.json", orientation_args=orientation_args)
    (run_dir / "command.json").write_text(json.dumps(cmd, indent=2), encoding="utf-8")
    proc = subprocess.run(cmd, shell=False, text=True, capture_output=True, timeout=config.timeout_seconds)
    (run_dir / "stdout.log").write_text(proc.stdout, encoding="utf-8", errors="replace")
    (run_dir / "stderr.log").write_text(proc.stderr, encoding="utf-8", errors="replace")

    gcode_files = sorted(run_dir.glob("*.gcode"))
    analysis = analyze_gcode(gcode_files[0], requested_material=filament) if gcode_files else {"warnings": ["No G-code file was produced"]}
    (run_dir / "analysis.json").write_text(json.dumps(analysis, indent=2), encoding="utf-8")

    ok = proc.returncode == 0 and gcode_files and gcode_files[0].stat().st_size > 0
    result = {
        "status": "ok" if ok else "error",
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "returncode": proc.returncode,
        "gcode": str(gcode_files[0]) if gcode_files else None,
        "analysis": analysis,
        "overrides": override_report,
        "orientation": orientation_report,
    }
    if verbose:
        result["command"] = cmd
        result["stdout_tail"] = proc.stdout[-4000:]
        result["stderr_tail"] = proc.stderr[-4000:]
    elif not ok:
        result["stdout_tail"] = proc.stdout[-1000:]
        result["stderr_tail"] = proc.stderr[-1000:]
    if not ok:
        result["stop_condition"] = {
            "phase": "Phase 3 slicing",
            "reason": "Snapmaker Orca did not complete headless slicing; do not fall back to upstream OrcaSlicer.",
            "failure_category": _classify_failure(proc.returncode, proc.stdout, proc.stderr),
            "artifacts": ["request.json", "command.json", "profiles/", "stdout.log", "stderr.log", "analysis.json"],
        }
    return result


def run_smoke_slice(model: str, process: str, filament: str, nozzle: float = 0.4, verbose: bool = False) -> dict:
    """Run the Phase 0 real smoke test using explicitly selected profiles."""
    result = u1_slice(model=model, process=process, filament=filament, nozzle=nozzle, verbose=verbose)
    if result.get("status") != "ok" and "stop_condition" in result:
        result["stop_condition"]["phase"] = "Phase 0 feasibility gate"
        result["stop_condition"]["reason"] = "Snapmaker Orca did not complete a real headless smoke slice; do not proceed to higher-level MCP features or fall back to upstream OrcaSlicer."
    return result


def u1_analyze_gcode(gcode: str, requested_material: str | None = None) -> dict:
    """Analyze a G-code file under U1_OUTPUT_DIR by relative path or run-id path."""
    config = Config.from_env()
    path = _safe_output_file(config.output_dir, gcode, {".gcode"})
    return analyze_gcode(path, requested_material=requested_material)


def u1_list_runs(limit: int = 20) -> dict:
    """List recent slice run directories under U1_OUTPUT_DIR."""
    config = Config.from_env()
    if limit < 1 or limit > 100:
        raise ConfigurationError("limit must be between 1 and 100")
    root = config.output_dir.expanduser().resolve()
    if not root.exists():
        return {"status": "ok", "runs": []}
    runs = [_run_summary(path) for path in root.iterdir() if path.is_dir() and _looks_like_run_dir(path)]
    runs.sort(key=lambda item: item["run_id"], reverse=True)
    return {"status": "ok", "runs": runs[:limit]}


def u1_get_run(run_id: str) -> dict:
    """Return compact metadata for one generated slice run."""
    config = Config.from_env()
    run_dir = _safe_run_dir(config.output_dir, run_id)
    summary = _run_summary(run_dir)
    summary["artifacts"] = _run_artifacts(run_dir)
    return summary


def u1_get_run_logs(run_id: str, tail: int = 2000) -> dict:
    """Return stdout/stderr log tails for one run, explicitly requested."""
    if tail < 0 or tail > 20000:
        raise ConfigurationError("tail must be between 0 and 20000 characters")
    config = Config.from_env()
    run_dir = _safe_run_dir(config.output_dir, run_id)
    return {
        "status": "ok",
        "run_id": run_dir.name,
        "stdout_tail": _tail_text(run_dir / "stdout.log", tail),
        "stderr_tail": _tail_text(run_dir / "stderr.log", tail),
    }


def u1_delete_run(run_id: str, confirm: bool = False) -> dict:
    """Delete one generated run directory after explicit confirmation."""
    if not confirm:
        raise ConfigurationError("confirm=true is required to delete a run")
    config = Config.from_env()
    run_dir = _safe_run_dir(config.output_dir, run_id)
    shutil.rmtree(run_dir)
    return {"status": "ok", "deleted": True, "run_id": run_id}


def u1_compare_slices(model: str, filament: str, variants: list[dict], nozzle: float = 0.4, verbose: bool = False) -> dict:
    """Slice multiple process/override variants and return a compact comparison."""
    if not isinstance(variants, list) or not variants:
        raise ConfigurationError("variants must be a non-empty list")

    results = []
    for index, variant in enumerate(variants):
        if not isinstance(variant, dict):
            raise ConfigurationError(f"variant {index} must be an object")
        name = str(variant.get("name") or f"variant-{index + 1}")
        process = variant.get("process")
        if not process:
            raise ConfigurationError(f"variant {name!r} is missing required process")
        variant_filament = str(variant.get("filament") or filament)
        overrides = variant.get("overrides") or {}
        slice_result = u1_slice(
            model=model,
            process=str(process),
            filament=variant_filament,
            nozzle=float(variant.get("nozzle", nozzle)),
            overrides=overrides,
            orientation=variant.get("orientation"),
            verbose=verbose,
        )
        analysis = slice_result.get("analysis", {})
        results.append({
            "name": name,
            "status": slice_result.get("status"),
            "run_dir": slice_result.get("run_dir"),
            "gcode": slice_result.get("gcode"),
            "process": str(process),
            "filament": variant_filament,
            "overrides": slice_result.get("overrides", {}),
            "orientation": slice_result.get("orientation", {}),
            "returncode": slice_result.get("returncode"),
            "estimated_print_time": analysis.get("estimated_print_time"),
            "filament_weight": analysis.get("filament_weight"),
            "filament_length": analysis.get("filament_length"),
            "layer_count": analysis.get("layer_count"),
            "warnings": analysis.get("warnings", []),
        })

    return {
        "status": "ok" if all(r["status"] == "ok" for r in results) else "error",
        "model": model,
        "filament": filament,
        "nozzle": nozzle,
        "variants": results,
        "table": _comparison_table(results),
    }


def u1_compare_orientations(
    model: str,
    process: str,
    filament: str,
    orientations: list[dict],
    nozzle: float = 0.4,
    overrides: dict | None = None,
    verbose: bool = False,
) -> dict:
    """Slice controlled orientation variants using Snapmaker Orca CLI rotations."""
    if not isinstance(orientations, list) or not orientations:
        raise ConfigurationError("orientations must be a non-empty list")
    variants = []
    for index, orientation in enumerate(orientations):
        if not isinstance(orientation, dict):
            raise ConfigurationError(f"orientation {index} must be an object")
        name = str(orientation.get("name") or _orientation_name(orientation, index))
        variants.append({
            "name": name,
            "process": process,
            "filament": filament,
            "overrides": overrides or {},
            "orientation": orientation,
        })
    result = u1_compare_slices(model=model, filament=filament, variants=variants, nozzle=nozzle, verbose=verbose)
    result["process"] = process
    result["orientation_experiment"] = True
    return result


def u1_compare_transformed_orientations(
    model: str,
    process: str,
    filament: str,
    orientations: list[dict] | None = None,
    nozzle: float = 0.4,
    overrides: dict | None = None,
    verbose: bool = False,
) -> dict:
    """Transform STL copies locally, then slice without Snapmaker Orca CLI rotation flags."""
    from .transform import transform_model_to_path

    if orientations is None:
        orientations = [
            {"name": "as-loaded"},
            {"name": "x90", "rotate_x": 90},
            {"name": "y90", "rotate_y": 90},
            {"name": "z90", "rotate": 90},
        ]
    if not isinstance(orientations, list) or not orientations:
        raise ConfigurationError("orientations must be a non-empty list")

    config = Config.from_env()
    results = []
    for index, orientation in enumerate(orientations):
        if not isinstance(orientation, dict):
            raise ConfigurationError(f"orientation {index} must be an object")
        name = str(orientation.get("name") or _orientation_name(orientation, index))
        _args, orientation_report = _orientation_args(orientation)
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", name).strip(".-") or f"orientation-{index + 1}"
        transform_dir = config.output_dir.expanduser().resolve() / "transformed" / f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}-{safe_name}"
        transform = transform_model_to_path(
            model,
            transform_dir,
            rotate=orientation_report.get("rotate", 0.0),
            rotate_x=orientation_report.get("rotate_x", 0.0),
            rotate_y=orientation_report.get("rotate_y", 0.0),
        )
        slice_result = _u1_slice_model_path(
            model_label=f"{model} ({name}, transformed)",
            model_path=Path(transform["output_path"]),
            process=process,
            filament=filament,
            nozzle=nozzle,
            overrides=overrides or {},
            orientation=None,
            verbose=verbose,
        )
        analysis = slice_result.get("analysis", {})
        results.append({
            "name": name,
            "status": slice_result.get("status"),
            "run_dir": slice_result.get("run_dir"),
            "gcode": slice_result.get("gcode"),
            "transformed_model": transform["output_path"],
            "transform": {"rotate": transform["rotate"], "rotate_x": transform["rotate_x"], "rotate_y": transform["rotate_y"], "dimensions": transform.get("dimensions")},
            "process": process,
            "filament": filament,
            "overrides": slice_result.get("overrides", {}),
            "returncode": slice_result.get("returncode"),
            "estimated_print_time": analysis.get("estimated_print_time"),
            "filament_weight": analysis.get("filament_weight"),
            "filament_length": analysis.get("filament_length"),
            "layer_count": analysis.get("layer_count"),
            "warnings": analysis.get("warnings", []),
        })
    return {
        "status": "ok" if all(r["status"] == "ok" for r in results) else "error",
        "model": model,
        "process": process,
        "filament": filament,
        "nozzle": nozzle,
        "local_mesh_transform": True,
        "variants": results,
        "table": _comparison_table(results),
    }


def _comparison_table(results: list[dict]) -> str:
    lines = [f"{'Variant':<18} {'Status':<8} {'Time':<12} {'Filament(g)':<12} {'Layers':<8}"]
    for item in results:
        lines.append(
            f"{item['name']:<18} {str(item.get('status')):<8} {str(item.get('estimated_print_time') or ''):<12} "
            f"{str(item.get('filament_weight') or ''):<12} {str(item.get('layer_count') or ''):<8}"
        )
    return "\n".join(lines)


def _orientation_args(orientation: dict | None) -> tuple[list[str], dict]:
    if not orientation:
        return [], {}
    if not isinstance(orientation, dict):
        raise ConfigurationError("orientation must be an object/dict")
    mapping = {
        "rotate": "--rotate",
        "rotate_x": "--rotate-x",
        "rotate_y": "--rotate-y",
    }
    args: list[str] = []
    report: dict = {}
    for key, flag in mapping.items():
        if key not in orientation:
            continue
        angle = _angle(key, orientation[key])
        report[key] = angle
        # Snapmaker Orca CLI can crash on no-op rotation commands such as
        # --rotate 0. Preserve the requested metadata but avoid no-op flags.
        if abs(angle) > 1e-9:
            args.extend([flag, f"{angle:g}"])
    unsupported = sorted(set(orientation) - {"name", *mapping})
    if unsupported:
        raise ConfigurationError(f"Unsupported orientation keys: {unsupported}. Allowed keys: {sorted(mapping)}")
    return args, report


def _angle(key: str, value) -> float:
    try:
        angle = float(value)
    except (TypeError, ValueError):
        raise ConfigurationError(f"orientation {key!r} must be a number of degrees") from None
    if not -360 <= angle <= 360:
        raise ConfigurationError(f"orientation {key!r} must be between -360 and 360 degrees")
    return angle


def _orientation_name(orientation: dict, index: int) -> str:
    _args, report = _orientation_args(orientation)
    if not report:
        return "default" if index == 0 else f"orientation-{index + 1}"
    return "+".join(f"{key}={value:g}" for key, value in report.items())


RUN_ID_RE = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{8}$")


def _safe_model_path(root: Path, model: str) -> Path:
    return _safe_output_file(root, model, SUPPORTED_MODEL_EXTENSIONS, label="Model")


def _safe_run_dir(root: Path, run_id: str) -> Path:
    if not RUN_ID_RE.fullmatch(run_id):
        raise ConfigurationError("Invalid run_id format")
    root = root.expanduser().resolve()
    run_dir = (root / run_id).resolve()
    try:
        run_dir.relative_to(root)
    except ValueError:
        raise ConfigurationError("Run path escapes configured output directory") from None
    if not run_dir.is_dir() or not _looks_like_run_dir(run_dir):
        raise ConfigurationError(f"Run not found: {run_id}")
    return run_dir


def _looks_like_run_dir(path: Path) -> bool:
    return RUN_ID_RE.fullmatch(path.name) is not None and any((path / name).exists() for name in ("request.json", "analysis.json", "stdout.log", "stderr.log"))


def _run_summary(run_dir: Path) -> dict:
    request = _read_json_optional(run_dir / "request.json") or {}
    analysis = _read_json_optional(run_dir / "analysis.json") or {}
    gcode_files = sorted(run_dir.glob("*.gcode"))
    warnings = analysis.get("warnings", []) if isinstance(analysis, dict) else []
    status = "ok" if gcode_files else "unknown"
    if warnings and "No G-code file was produced" in warnings:
        status = "error"
    return {
        "status": status,
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "model": request.get("model"),
        "process": request.get("process"),
        "filament": request.get("filament"),
        "nozzle": request.get("nozzle"),
        "orientation": request.get("orientation", {}),
        "gcode": str(gcode_files[0]) if gcode_files else None,
        "gcode_count": len(gcode_files),
        "estimated_print_time": analysis.get("estimated_print_time") if isinstance(analysis, dict) else None,
        "filament_weight": analysis.get("filament_weight") if isinstance(analysis, dict) else None,
        "layer_count": analysis.get("layer_count") if isinstance(analysis, dict) else None,
        "warnings": warnings,
    }


def _run_artifacts(run_dir: Path) -> dict:
    names = ["request.json", "command.json", "analysis.json", "stdout.log", "stderr.log"]
    artifacts = {name: (run_dir / name).exists() for name in names}
    artifacts["profiles"] = (run_dir / "profiles").is_dir()
    artifacts["gcode"] = [path.name for path in sorted(run_dir.glob("*.gcode"))]
    return artifacts


def _read_json_optional(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _tail_text(path: Path, tail: int) -> str:
    if tail == 0 or not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[-tail:]
