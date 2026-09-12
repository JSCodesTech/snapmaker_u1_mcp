from __future__ import annotations

import argparse
import json
import sys

from .config import Config
from .models import u1_inspect_model as inspect_model, u1_mesh_printability as mesh_printability, u1_model_diagnostics as model_diagnostics, u1_orientation_preflight as orientation_preflight
from .preview import u1_render_preview as render_preview, u1_render_preview_bundle as render_preview_bundle
from .thumbnail import u1_inject_thumbnail as inject_thumbnail
from .profiles import ProfileSelection, ProfileStore, discover_profile_roots
from .slicer import locate_slicer, list_models, run_smoke_slice, u1_analyze_gcode as analyze_gcode_file, u1_compare_orientations as compare_orientations, u1_compare_slices as compare_slices, u1_compare_transformed_orientations as compare_transformed_orientations, u1_delete_run as delete_run, u1_get_run as get_run, u1_get_run_logs as get_run_logs, u1_health, u1_list_runs as list_runs, u1_slice as slice_model
from .transform import u1_transform_model as transform_model
from .recipes import u1_compare_recipes as compare_recipes, u1_get_recipe as get_recipe, u1_list_recipes as list_recipes
from .reports import u1_export_run_report as export_run_report, u1_reproduce_run as reproduce_run, u1_search_runs as search_runs


def _profile_store() -> ProfileStore:
    config = Config.from_env()
    try:
        binary = locate_slicer(config)
    except Exception:
        binary = None
    return ProfileStore(discover_profile_roots(config.profile_dir, binary))


def list_profiles_filtered(
    nozzle: float | None = None,
    material: str | None = None,
    layer_height: float | None = None,
    details: bool = False,
) -> dict:
    store = _profile_store()
    profiles = store.list_profiles(nozzle=nozzle, material=material, layer_height=layer_height)
    if details:
        return {kind: [info.__dict__ for info in infos] for kind, infos in profiles.items()}
    return {kind: [info.name for info in infos] for kind, infos in profiles.items()}


def get_profile_detail(name: str, kind: str) -> dict:
    """Return one resolved profile by exact name or file stem."""
    store = _profile_store()
    path = store.find_profile_path(name, kind)
    resolved = store.resolve_profile(name, kind)
    infos = [info for info in store.list_profiles(kind).get(kind, []) if info.name.lower() == str(resolved.get("name", name)).lower()]
    return {
        "status": "ok",
        "kind": kind,
        "name": str(resolved.get("name") or name),
        "path": str(path),
        "summary": infos[0].__dict__ if infos else None,
        "profile": resolved,
    }


def profile_source_chain(name: str, kind: str) -> dict:
    store = _profile_store()
    return {"status": "ok", "kind": kind, "name": name, "chain": store.profile_source_chain(name, kind)}


def diff_profiles(left: str, right: str, kind: str) -> dict:
    store = _profile_store()
    return {"status": "ok", **store.diff_profiles(left, right, kind)}


def explain_profile_selection(process: str, filament: str, nozzle: float = 0.4, machine: str | None = None) -> dict:
    """Validate and summarize a machine/process/filament selection."""
    store = _profile_store()
    machine_name = machine or f"Snapmaker U1 ({nozzle:g} nozzle)"
    profiles = store.validate_selection(ProfileSelection(
        machine_name=machine_name,
        process_name=process,
        filament_name=filament,
        nozzle=nozzle,
    ))
    return {
        "status": "ok",
        "compatible": True,
        "nozzle": nozzle,
        "machine": _profile_summary(profiles["machine"]),
        "process": _profile_summary(profiles["process"]),
        "filament": _profile_summary(profiles["filament"]),
    }


def _profile_summary(profile: dict) -> dict:
    return {
        "name": profile.get("name") or profile.get("filament_settings_id") or profile.get("print_settings_id"),
        "type": profile.get("type"),
        "inherits_removed": "inherits" not in profile,
        "layer_height": profile.get("layer_height"),
        "filament_type": profile.get("filament_type"),
        "nozzle_diameter": profile.get("nozzle_diameter"),
        "compatible_printers": profile.get("compatible_printers"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Snapmaker U1 MCP server")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("health")
    sub.add_parser("list-models")
    profiles = sub.add_parser("list-profiles")
    profiles.add_argument("--nozzle", type=float)
    profiles.add_argument("--material")
    profiles.add_argument("--layer-height", type=float)
    profiles.add_argument("--details", action="store_true")
    profile = sub.add_parser("get-profile")
    profile.add_argument("kind", choices=["machine", "process", "filament"])
    profile.add_argument("name")
    chain = sub.add_parser("profile-source-chain")
    chain.add_argument("kind", choices=["machine", "process", "filament"])
    chain.add_argument("name")
    diff = sub.add_parser("diff-profiles")
    diff.add_argument("kind", choices=["machine", "process", "filament"])
    diff.add_argument("left")
    diff.add_argument("right")
    explain = sub.add_parser("explain-profile-selection")
    explain.add_argument("--process", required=True)
    explain.add_argument("--filament", required=True)
    explain.add_argument("--nozzle", type=float, default=0.4)
    explain.add_argument("--machine")
    slice_cmd = sub.add_parser("slice")
    slice_cmd.add_argument("model")
    slice_cmd.add_argument("--process", required=True)
    slice_cmd.add_argument("--filament", required=True)
    slice_cmd.add_argument("--nozzle", type=float, default=0.4)
    slice_cmd.add_argument("--overrides", help="JSON object of allowed process overrides")
    slice_cmd.add_argument("--orientation", help="JSON object with rotate/rotate_x/rotate_y degrees")
    slice_cmd.add_argument("--verbose", action="store_true", help="include command and log tails in response")
    smoke = sub.add_parser("smoke-slice")
    smoke.add_argument("model")
    smoke.add_argument("--process", required=True)
    smoke.add_argument("--filament", required=True)
    smoke.add_argument("--nozzle", type=float, default=0.4)
    smoke.add_argument("--verbose", action="store_true", help="include command and log tails in response")
    analyze = sub.add_parser("analyze-gcode")
    analyze.add_argument("gcode")
    analyze.add_argument("--requested-material")
    runs = sub.add_parser("list-runs")
    runs.add_argument("--limit", type=int, default=20)
    run_search = sub.add_parser("search-runs")
    run_search.add_argument("--model")
    run_search.add_argument("--filament")
    run_search.add_argument("--status")
    run_search.add_argument("--limit", type=int, default=50)
    run = sub.add_parser("get-run")
    run.add_argument("run_id")
    logs = sub.add_parser("get-run-logs")
    logs.add_argument("run_id")
    logs.add_argument("--tail", type=int, default=2000)
    delete = sub.add_parser("delete-run")
    delete.add_argument("run_id")
    delete.add_argument("--confirm", action="store_true")
    report = sub.add_parser("export-run-report")
    report.add_argument("run_id")
    reproduce = sub.add_parser("reproduce-run")
    reproduce.add_argument("run_id")
    reproduce.add_argument("--verbose", action="store_true")
    inspect = sub.add_parser("inspect-model")
    inspect.add_argument("model")
    diagnose = sub.add_parser("diagnose-model")
    diagnose.add_argument("model")
    mesh = sub.add_parser("mesh-printability")
    mesh.add_argument("model")
    mesh.add_argument("--overhang-angle", type=float, default=45.0)
    orient_preflight = sub.add_parser("orientation-preflight")
    orient_preflight.add_argument("model")
    transform = sub.add_parser("transform-model")
    transform.add_argument("model")
    transform.add_argument("--rotate", type=float, default=0.0)
    transform.add_argument("--rotate-x", type=float, default=0.0)
    transform.add_argument("--rotate-y", type=float, default=0.0)
    preview = sub.add_parser("render-preview")
    preview.add_argument("model")
    preview.add_argument("--view", default="summary", choices=["summary", "top", "front", "side"])
    preview_bundle = sub.add_parser("render-preview-bundle")
    preview_bundle.add_argument("model")
    thumb = sub.add_parser("inject-thumbnail")
    thumb.add_argument("gcode")
    thumb.add_argument("--model", required=True)
    thumb.add_argument("--view", default="summary", choices=["summary", "top", "front", "side"])
    compare = sub.add_parser("compare-slices")
    compare.add_argument("model")
    compare.add_argument("--filament", required=True)
    compare.add_argument("--variants", required=True, help="JSON array of {name, process, overrides}")
    compare.add_argument("--nozzle", type=float, default=0.4)
    compare.add_argument("--verbose", action="store_true", help="include per-slice command and log tails")
    orient = sub.add_parser("compare-orientations")
    orient.add_argument("model")
    orient.add_argument("--process", required=True)
    orient.add_argument("--filament", required=True)
    orient.add_argument("--orientations", required=True, help="JSON array of orientation objects")
    orient.add_argument("--nozzle", type=float, default=0.4)
    orient.add_argument("--overrides", help="JSON object of allowed process overrides")
    orient.add_argument("--verbose", action="store_true", help="include per-slice command and log tails")
    transformed_orient = sub.add_parser("compare-transformed-orientations")
    transformed_orient.add_argument("model")
    transformed_orient.add_argument("--process", required=True)
    transformed_orient.add_argument("--filament", required=True)
    transformed_orient.add_argument("--orientations", help="JSON array of orientation objects; defaults to as-loaded/x90/y90/z90")
    transformed_orient.add_argument("--nozzle", type=float, default=0.4)
    transformed_orient.add_argument("--overrides", help="JSON object of allowed process overrides")
    transformed_orient.add_argument("--verbose", action="store_true", help="include per-slice command and log tails")
    recipes = sub.add_parser("list-recipes")
    recipe = sub.add_parser("get-recipe")
    recipe.add_argument("name")
    recipe_compare = sub.add_parser("compare-recipes")
    recipe_compare.add_argument("model")
    recipe_compare.add_argument("--process", required=True)
    recipe_compare.add_argument("--filament", required=True)
    recipe_compare.add_argument("--recipes", required=True, help="JSON array of recipe names")
    recipe_compare.add_argument("--nozzle", type=float, default=0.4)
    recipe_compare.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    try:
        if args.command == "health":
            print(json.dumps(u1_health(), indent=2))
        elif args.command == "list-models":
            print(json.dumps(list_models(), indent=2))
        elif args.command == "list-profiles":
            print(json.dumps(list_profiles_filtered(args.nozzle, args.material, args.layer_height, args.details), indent=2))
        elif args.command == "get-profile":
            print(json.dumps(get_profile_detail(args.name, args.kind), indent=2))
        elif args.command == "profile-source-chain":
            print(json.dumps(profile_source_chain(args.name, args.kind), indent=2))
        elif args.command == "diff-profiles":
            print(json.dumps(diff_profiles(args.left, args.right, args.kind), indent=2))
        elif args.command == "explain-profile-selection":
            print(json.dumps(explain_profile_selection(args.process, args.filament, args.nozzle, args.machine), indent=2))
        elif args.command == "slice":
            overrides = json.loads(args.overrides) if args.overrides else None
            orientation = json.loads(args.orientation) if args.orientation else None
            print(json.dumps(slice_model(args.model, args.process, args.filament, args.nozzle, overrides, orientation, args.verbose), indent=2))
        elif args.command == "smoke-slice":
            print(json.dumps(run_smoke_slice(args.model, args.process, args.filament, args.nozzle, args.verbose), indent=2))
        elif args.command == "analyze-gcode":
            print(json.dumps(analyze_gcode_file(args.gcode, args.requested_material), indent=2))
        elif args.command == "list-runs":
            print(json.dumps(list_runs(args.limit), indent=2))
        elif args.command == "search-runs":
            print(json.dumps(search_runs(args.model, args.filament, args.status, args.limit), indent=2))
        elif args.command == "get-run":
            print(json.dumps(get_run(args.run_id), indent=2))
        elif args.command == "get-run-logs":
            print(json.dumps(get_run_logs(args.run_id, args.tail), indent=2))
        elif args.command == "delete-run":
            print(json.dumps(delete_run(args.run_id, args.confirm), indent=2))
        elif args.command == "export-run-report":
            print(json.dumps(export_run_report(args.run_id), indent=2))
        elif args.command == "reproduce-run":
            print(json.dumps(reproduce_run(args.run_id, args.verbose), indent=2))
        elif args.command == "inspect-model":
            print(json.dumps(inspect_model(args.model), indent=2))
        elif args.command == "diagnose-model":
            print(json.dumps(model_diagnostics(args.model), indent=2))
        elif args.command == "mesh-printability":
            print(json.dumps(mesh_printability(args.model, args.overhang_angle), indent=2))
        elif args.command == "orientation-preflight":
            print(json.dumps(orientation_preflight(args.model), indent=2))
        elif args.command == "transform-model":
            print(json.dumps(transform_model(args.model, args.rotate, args.rotate_x, args.rotate_y), indent=2))
        elif args.command == "render-preview":
            print(json.dumps(render_preview(args.model, args.view), indent=2))
        elif args.command == "render-preview-bundle":
            print(json.dumps(render_preview_bundle(args.model), indent=2))
        elif args.command == "inject-thumbnail":
            print(json.dumps(inject_thumbnail(args.gcode, args.model, args.view), indent=2))
        elif args.command == "compare-slices":
            print(json.dumps(compare_slices(args.model, args.filament, json.loads(args.variants), args.nozzle, args.verbose), indent=2))
        elif args.command == "compare-orientations":
            overrides = json.loads(args.overrides) if args.overrides else None
            print(json.dumps(compare_orientations(args.model, args.process, args.filament, json.loads(args.orientations), args.nozzle, overrides, args.verbose), indent=2))
        elif args.command == "compare-transformed-orientations":
            overrides = json.loads(args.overrides) if args.overrides else None
            orientations = json.loads(args.orientations) if args.orientations else None
            print(json.dumps(compare_transformed_orientations(args.model, args.process, args.filament, orientations, args.nozzle, overrides, args.verbose), indent=2))
        elif args.command == "list-recipes":
            print(json.dumps(list_recipes(), indent=2))
        elif args.command == "get-recipe":
            print(json.dumps(get_recipe(args.name), indent=2))
        elif args.command == "compare-recipes":
            print(json.dumps(compare_recipes(args.model, args.process, args.filament, json.loads(args.recipes), args.nozzle, args.verbose), indent=2))
        else:
            # If launched by an MCP client, start stdio server when mcp is installed.
            _run_mcp_stdio()
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc), "type": exc.__class__.__name__}, indent=2), file=sys.stderr)
        raise SystemExit(1)


def _run_mcp_stdio() -> None:
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception as exc:
        raise SystemExit(f"mcp package is not installed or unavailable: {exc}")

    mcp = FastMCP("snapmaker-u1")

    @mcp.tool()
    def u1_health() -> dict:
        """Check Snapmaker Orca CLI, U1 profile discovery, and output directory access."""
        from .slicer import u1_health as health
        return health()

    @mcp.tool()
    def u1_list_models() -> list[dict]:
        """List STL/3MF models inside U1_MODEL_DIR."""
        return list_models()

    @mcp.tool()
    def u1_list_profiles(nozzle: float | None = None, material: str | None = None, layer_height: float | None = None, details: bool = False) -> dict:
        """List discovered Snapmaker U1 profile names by default; set details=true for full metadata."""
        return list_profiles_filtered(nozzle, material, layer_height, details)

    @mcp.tool()
    def u1_get_profile(name: str, kind: str) -> dict:
        """Return one resolved machine/process/filament profile by exact name or file stem."""
        return get_profile_detail(name, kind)

    @mcp.tool()
    def u1_profile_source_chain(name: str, kind: str) -> dict:
        """Return child-to-parent profile inheritance source chain."""
        return profile_source_chain(name, kind)

    @mcp.tool()
    def u1_diff_profiles(left: str, right: str, kind: str) -> dict:
        """Diff two resolved profiles of the same kind."""
        return diff_profiles(left, right, kind)

    @mcp.tool()
    def u1_explain_profile_selection(process: str, filament: str, nozzle: float = 0.4, machine: str | None = None) -> dict:
        """Validate and summarize a machine/process/filament selection."""
        return explain_profile_selection(process, filament, nozzle, machine)

    @mcp.tool()
    def u1_slice(model: str, process: str, filament: str, nozzle: float = 0.4, overrides: dict | None = None, orientation: dict | None = None, verbose: bool = False) -> dict:
        """Slice an STL/3MF model for Snapmaker U1 and return compact G-code analysis; set verbose=true for logs."""
        return slice_model(model, process, filament, nozzle, overrides, orientation, verbose)

    @mcp.tool()
    def u1_analyze_gcode(gcode: str, requested_material: str | None = None) -> dict:
        """Analyze a generated G-code file under U1_OUTPUT_DIR."""
        return analyze_gcode_file(gcode, requested_material)

    @mcp.tool()
    def u1_list_runs(limit: int = 20) -> dict:
        """List recent generated slice runs with compact metadata."""
        return list_runs(limit)

    @mcp.tool()
    def u1_get_run(run_id: str) -> dict:
        """Return compact metadata and artifact availability for one run."""
        return get_run(run_id)

    @mcp.tool()
    def u1_get_run_logs(run_id: str, tail: int = 2000) -> dict:
        """Return stdout/stderr log tails for one run on explicit request."""
        return get_run_logs(run_id, tail)

    @mcp.tool()
    def u1_search_runs(model: str | None = None, filament: str | None = None, status: str | None = None, limit: int = 50) -> dict:
        """Search recent runs by model, filament, and/or status."""
        return search_runs(model, filament, status, limit)

    @mcp.tool()
    def u1_export_run_report(run_id: str) -> dict:
        """Write a Markdown summary report into a run directory."""
        return export_run_report(run_id)

    @mcp.tool()
    def u1_reproduce_run(run_id: str, verbose: bool = False) -> dict:
        """Re-slice a previous regular run from stored request metadata."""
        return reproduce_run(run_id, verbose)

    @mcp.tool()
    def u1_delete_run(run_id: str, confirm: bool = False) -> dict:
        """Delete one generated run directory; requires confirm=true."""
        return delete_run(run_id, confirm)

    @mcp.tool()
    def u1_compare_slices(model: str, filament: str, variants: list[dict], nozzle: float = 0.4, verbose: bool = False) -> dict:
        """Slice and compare multiple process/override variants."""
        return compare_slices(model, filament, variants, nozzle, verbose)

    @mcp.tool()
    def u1_compare_orientations(model: str, process: str, filament: str, orientations: list[dict], nozzle: float = 0.4, overrides: dict | None = None, verbose: bool = False) -> dict:
        """Slice and compare controlled orientation variants."""
        return compare_orientations(model, process, filament, orientations, nozzle, overrides, verbose)

    @mcp.tool()
    def u1_transform_model(model: str, rotate: float = 0.0, rotate_x: float = 0.0, rotate_y: float = 0.0) -> dict:
        """Create a locally transformed STL copy under U1_OUTPUT_DIR/transformed."""
        return transform_model(model, rotate, rotate_x, rotate_y)

    @mcp.tool()
    def u1_compare_transformed_orientations(model: str, process: str, filament: str, orientations: list[dict] | None = None, nozzle: float = 0.4, overrides: dict | None = None, verbose: bool = False) -> dict:
        """Transform STL copies locally, then slice without Snapmaker Orca CLI rotation flags."""
        return compare_transformed_orientations(model, process, filament, orientations, nozzle, overrides, verbose)

    @mcp.tool()
    def u1_inspect_model(model: str) -> dict:
        """Inspect STL/3MF dimensions and basic U1 fit information."""
        return inspect_model(model)

    @mcp.tool()
    def u1_diagnose_model(model: str) -> dict:
        """Return practical pre-slice model diagnostics and suggestions."""
        return model_diagnostics(model)

    @mcp.tool()
    def u1_mesh_printability(model: str, overhang_angle: float = 45.0) -> dict:
        """Estimate simple STL overhang/contact metrics without slicing."""
        return mesh_printability(model, overhang_angle)

    @mcp.tool()
    def u1_orientation_preflight(model: str) -> dict:
        """Preflight axis-aligned orientation candidates without slicing rotated variants."""
        return orientation_preflight(model)

    @mcp.tool()
    def u1_render_preview(model: str, view: str = "summary") -> dict:
        """Generate a lightweight SVG preview from model dimensions."""
        return render_preview(model, view)

    @mcp.tool()
    def u1_render_preview_bundle(model: str) -> dict:
        """Generate summary/top/front/side SVG previews for a model."""
        return render_preview_bundle(model)

    @mcp.tool()
    def u1_inject_thumbnail(gcode: str, model: str, view: str = "summary") -> dict:
        """Inject an SVG preview as comment metadata into a copied G-code file."""
        return inject_thumbnail(gcode, model, view)

    @mcp.tool()
    def u1_list_recipes() -> dict:
        """List built-in override recipes for common slicing goals."""
        return list_recipes()

    @mcp.tool()
    def u1_get_recipe(name: str) -> dict:
        """Return one built-in override recipe."""
        return get_recipe(name)

    @mcp.tool()
    def u1_compare_recipes(model: str, process: str, filament: str, recipes: list[str], nozzle: float = 0.4, verbose: bool = False) -> dict:
        """Compare built-in recipe override sets using the same process/filament."""
        return compare_recipes(model, process, filament, recipes, nozzle, verbose)

    @mcp.tool()
    def u1_smoke_slice(model: str, process: str, filament: str, nozzle: float = 0.4, verbose: bool = False) -> dict:
        """Run Phase 0 real smoke slice with explicit process and filament profiles."""
        return run_smoke_slice(model, process, filament, nozzle, verbose)

    mcp.run()


if __name__ == "__main__":
    main()
