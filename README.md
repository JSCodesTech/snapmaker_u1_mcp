# snapmaker-u1-mcp

MCP server for Snapmaker U1 headless slicing on Ubuntu using **Snapmaker Orca**.

The server exposes safe tools to inspect models, select profiles, slice to G-code, compare settings, and inspect generated runs. It does not control the printer or start prints.

## Scope

- Snapmaker Orca only; no fallback to upstream OrcaSlicer
- headless CLI slicing; no GUI automation
- single-material workflows first
- all model paths restricted to `U1_MODEL_DIR`
- all generated outputs restricted to `U1_OUTPUT_DIR`
- generated G-code is reproducible from stored request/profile artifacts

## Tools

Core:

- `u1_health`
- `u1_list_models`
- `u1_list_profiles`
- `u1_get_profile`
- `u1_profile_source_chain`
- `u1_diff_profiles`
- `u1_explain_profile_selection`
- `u1_slice`
- `u1_smoke_slice`

Analysis and comparison:

- `u1_analyze_gcode`
- `u1_compare_slices`
- `u1_compare_orientations`
- `u1_transform_model`
- `u1_compare_transformed_orientations`
- `u1_inspect_model`
- `u1_diagnose_model`
- `u1_mesh_printability`
- `u1_multimaterial_readiness`
- `u1_orientation_preflight`

Preview and metadata:

- `u1_render_preview`
- `u1_render_preview_bundle`
- `u1_inject_thumbnail`

Recipes:

- `u1_list_recipes`
- `u1_get_recipe`
- `u1_compare_recipes`

Run management:

- `u1_list_runs`
- `u1_get_run`
- `u1_get_run_logs`
- `u1_search_runs`
- `u1_export_run_report`
- `u1_reproduce_run`
- `u1_delete_run`

## Install

```bash
git clone git@github.com:JSCodesTech/snapmaker_u1_mcp.git
cd snapmaker_u1_mcp
python3 -m venv .venv
.venv/bin/pip install -e '.[test]'
```

Configure paths:

```bash
export SNAPMAKER_ORCA_BIN=/path/to/snapmaker-orca/AppRun
# or
export SNAPMAKER_ORCA_APPIMAGE=/path/to/Snapmaker-Orca.AppImage

export U1_MODEL_DIR=$HOME/3D_Printing/models
export U1_OUTPUT_DIR=$HOME/3D_Printing/output
mkdir -p "$U1_MODEL_DIR" "$U1_OUTPUT_DIR"
```

Optional if profiles are not auto-discovered:

```bash
export SNAPMAKER_PROFILE_DIR=/path/to/Snapmaker/Orca/resources/profiles
```

Check health:

```bash
snapmaker-u1-mcp health
```

## MCP configuration

A template is included at `examples/mcp/pi-mcp.json`. Copy it into your MCP client configuration and replace the absolute paths.

Keep your personal MCP config out of git.

## How to use the MCP

Use the MCP as a batch/reproducibility assistant, not as a replacement for manually reviewing prints in Snapmaker Orca.

Good MCP use cases:

- compare a small number of slice variants
- check model dimensions and printability warnings
- test orientations using local transformed model copies
- inspect profiles and explain compatibility
- analyze generated G-code
- export run reports for later review

Example prompts:

```text
Check Snapmaker U1 health and list my PLA profiles for a 0.4 mm nozzle.
```

```text
Inspect hase.stl, run printability checks, and render a summary preview.
```

```text
Compare baseline, pla-draft, and pla-strong for hase.stl. Return only a compact table and recommendation.
```

```text
Compare flat and X90 using transformed orientations, not Snapmaker Orca CLI rotation flags.
```

Keep usage low-cost by being specific. Prefer 2–4 variants per request and ask for compact summaries. Use Snapmaker Orca GUI for final visual review, manual support decisions, and one-off simple prints.

## CLI examples

List models and profiles:

```bash
snapmaker-u1-mcp list-models
snapmaker-u1-mcp list-profiles --nozzle 0.4 --material PLA
snapmaker-u1-mcp get-profile process "0.20 Standard @Snapmaker U1 (0.4 nozzle)"
snapmaker-u1-mcp profile-source-chain process "0.20 Standard @Snapmaker U1 (0.4 nozzle)"
snapmaker-u1-mcp list-recipes
snapmaker-u1-mcp compare-recipes hase.stl \
  --process "0.20 Standard @Snapmaker U1 (0.4 nozzle)" \
  --filament "Snapmaker PLA Basic @U1" \
  --recipes '["pla-draft","pla-strong"]'
```

Inspect a model:

```bash
snapmaker-u1-mcp inspect-model hase.stl
snapmaker-u1-mcp diagnose-model hase.stl
snapmaker-u1-mcp mesh-printability hase.stl
snapmaker-u1-mcp multimaterial-readiness --model hase.stl
snapmaker-u1-mcp orientation-preflight hase.stl
snapmaker-u1-mcp transform-model hase.stl --rotate-x 90
snapmaker-u1-mcp render-preview hase.stl --view summary
```

Slice:

```bash
snapmaker-u1-mcp slice hase.stl \
  --process "0.20 Standard @Snapmaker U1 (0.4 nozzle)" \
  --filament "Snapmaker PLA Basic @U1"
```

Compare local mesh-transformed orientations without Snapmaker Orca CLI rotation flags:

```bash
snapmaker-u1-mcp compare-transformed-orientations hase.stl \
  --process "0.20 Standard @Snapmaker U1 (0.4 nozzle)" \
  --filament "Snapmaker PLA Basic @U1" \
  --orientations '[{"name":"flat"},{"name":"x90","rotate_x":90},{"name":"y90","rotate_y":90}]'
```

Slice with controlled overrides:

```bash
snapmaker-u1-mcp slice hase.stl \
  --process "0.20 Standard @Snapmaker U1 (0.4 nozzle)" \
  --filament "Snapmaker PLA Basic @U1" \
  --overrides '{"wall_loops":3}'
```

Inspect generated runs:

```bash
snapmaker-u1-mcp list-runs --limit 10
snapmaker-u1-mcp get-run RUN_ID
snapmaker-u1-mcp get-run-logs RUN_ID --tail 2000
snapmaker-u1-mcp search-runs --model hase --status ok
snapmaker-u1-mcp export-run-report RUN_ID
```

Delete a generated run only when intentional:

```bash
snapmaker-u1-mcp delete-run RUN_ID --confirm
```

## Run artifacts

Each slice creates a run directory under `U1_OUTPUT_DIR` containing:

```text
request.json
command.json
profiles/
stdout.log
stderr.log
analysis.json
plate_1.gcode
```

Original Snapmaker profiles are never modified.

## Notes

Snapmaker Orca Linux CLI `01.10.01.50` has been observed to crash with some profile fields and non-zero CLI rotation transforms. This server reports those failures and keeps logs; it does not silently switch slicers.

For setup and troubleshooting, see:

- `docs/INSTALL.md`
- `docs/MCP_USAGE.md`
- `docs/TROUBLESHOOTING.md`
- `docs/ARCHITECTURE.md`
- `examples/requests/`

## Tests

```bash
python -m pytest
python -m pytest --cov=snapmaker_u1_mcp --cov-report=term-missing --cov-fail-under=80
```

## Acknowledgements

This project was built with awareness of `Diterex/orcaslicer-mcp`, but is a smaller Snapmaker U1/Snapmaker Orca-focused implementation.
