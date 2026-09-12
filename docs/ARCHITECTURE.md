# Architecture

`snapmaker-u1-mcp` exposes small MCP tools around Snapmaker Orca headless slicing.

```text
MCP client / CLI
  -> snapmaker_u1_mcp.server
  -> reusable service modules
  -> Snapmaker Orca CLI where slicing is required
  -> reproducible run artifacts / G-code
```

## Module responsibilities

- `config.py` — environment-driven configuration
- `paths.py` — reusable safe path handling, run directory creation, JSON writing
- `orca.py` — Snapmaker Orca discovery, AppImage extraction, CLI command construction, failure classification
- `profiles.py` — profile discovery, lookup, inheritance resolution, runtime-profile cleanup, validation
- `overrides.py` — allowlisted process override validation/application
- `slicer.py` — orchestration of slicing workflows and comparisons
- `gcode.py` — G-code metadata analysis
- `models.py` — STL/3MF model inspection
- `preview.py` — lightweight SVG preview rendering
- `thumbnail.py` — metadata-only thumbnail injection into copied G-code files
- `server.py` — CLI and MCP tool registration only
- `errors.py` — explicit project exceptions

## Reuse patterns

- All filesystem access goes through reusable safe path helpers where practical.
- Snapmaker Orca-specific CLI concerns are isolated in `orca.py`.
- Slicing orchestration writes reproducibility artifacts before/after subprocess execution.
- Profile mutation is never done in place against user-installed profiles; runtime copies are generated per run.
- Optional higher-level workflows (`compare_slices`, `compare_orientations`) call the primitive `u1_slice` rather than duplicating slicing logic.

## Constraints

- Snapmaker Orca only; no silent upstream OrcaSlicer fallback.
- No GUI automation.
- Subprocess commands are built as argument lists with `shell=False`.
- Models are restricted to `U1_MODEL_DIR`.
- Generated G-code and analysis paths are restricted to `U1_OUTPUT_DIR`.
- Slice outputs use unique run directories and preserve reproducibility artifacts.
- Original Snapmaker profiles are never modified.

## Runtime profiles

Every slice creates flattened runtime profiles under the run directory. This preserves reproducibility while leaving Snapmaker's installed profiles untouched.

For Snapmaker Orca Linux CLI `01.10.01.50`, generated runtime profiles omit `wipe_tower_filament` because that key has been observed to trigger a CLI segfault when loading U1 process profiles. The current workflow is single-material only.
