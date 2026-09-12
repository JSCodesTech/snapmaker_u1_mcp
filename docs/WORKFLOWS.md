# Agent Workflows

Example workflows for agents using `snapmaker-u1-mcp`.

## Basic slice workflow

1. `u1_health`
2. `u1_list_models`
3. `u1_list_profiles(nozzle=0.4, material="PLA")`
4. `u1_explain_profile_selection` for the intended process/filament
5. `u1_diagnose_model`
6. `u1_slice`
7. `u1_analyze_gcode` if extra analysis is needed

## Mechanical part workflow

1. Choose suitable material profiles, for example PETG.
2. Slice a baseline.
3. Use `u1_compare_slices` with explicit variants:
   - more walls
   - more infill
   - support/brim changes if needed
4. Compare time, filament, layer count, and warnings.
5. Present the tradeoff instead of silently choosing settings.

## Orientation workflow

1. Call `u1_inspect_model`.
2. Call `u1_orientation_preflight`.
3. Prefer the as-loaded orientation when it fits and print quality is acceptable.
4. If rotated slicing is needed, prefer `u1_compare_transformed_orientations`. It creates local transformed STL copies and slices those, avoiding Snapmaker Orca CLI rotation flags.
5. Treat `u1_compare_orientations` as an engine-behavior experiment because some Snapmaker Orca CLI rotation transforms can crash.

## Debugging a failed run

1. `u1_list_runs`
2. `u1_get_run(RUN_ID)`
3. `u1_get_run_logs(RUN_ID, tail=4000)` only when logs are needed

## Safety reminder

The server slices and analyzes. It does not upload files to the printer or start prints.
