# Profiles

Profiles are discovered from:

1. `SNAPMAKER_PROFILE_DIR`, if configured
2. profile directories found relative to the Snapmaker Orca installation/AppImage extraction

Supported categories:

- `machine`
- `process`
- `filament`

The server exposes Snapmaker U1-relevant profiles only. Bundled profiles for unrelated vendors are hidden from `u1_list_profiles`, but the resolver may still load internal parent profiles needed to flatten inheritance.

## Listing profiles

```bash
python3 -m snapmaker_u1_mcp.server list-profiles
python3 -m snapmaker_u1_mcp.server list-profiles --nozzle 0.4
python3 -m snapmaker_u1_mcp.server list-profiles --nozzle 0.4 --material PETG
python3 -m snapmaker_u1_mcp.server list-profiles --layer-height 0.20
```

## Inheritance resolution

Snapmaker Orca profiles can contain:

```json
{
  "inherits": "parent-profile"
}
```

The resolver recursively loads parents, merges parent settings first, then applies child values. It detects cycles and fails clearly on missing or ambiguous parents.

Generated runtime profiles are flattened and written to each run directory:

```text
RUN/profiles/machine.json
RUN/profiles/process.json
RUN/profiles/filament.json
```

Original Snapmaker profiles are never modified.

## Runtime cleanup

The flattened runtime profiles omit unresolved inheritance and omit `wipe_tower_filament` because Snapmaker Orca Linux CLI `01.10.01.50` has been observed to segfault when loading that U1 process-profile key. The current workflow is single-material, so this omission is intentional.

## Validation

Before slicing, the selected profiles are validated for:

- Snapmaker U1 machine identity
- nozzle compatibility
- process/machine compatibility
- plausible layer height
- filament nozzle temperature metadata
- filament bed/plate temperature metadata

Contradictory profiles are rejected before invoking Snapmaker Orca.
