# Troubleshooting

## MCP server does not appear in Pi/agent client

- Confirm your client config points to the venv Python:

```json
"command": "/absolute/path/to/snapmaker_u1_mcp/.venv/bin/python",
"args": ["-m", "snapmaker_u1_mcp.server"]
```

- Restart/reload the MCP client after changing config.
- Run local health outside the client:

```bash
SNAPMAKER_ORCA_BIN=/path/to/AppRun \
U1_MODEL_DIR=/path/to/models \
U1_OUTPUT_DIR=/path/to/output \
.venv/bin/python -m snapmaker_u1_mcp.server health
```

## `mcp.server.fastmcp` missing

This project uses the MCP Python SDK v1 FastMCP API. Install project dependencies from `pyproject.toml`:

```bash
.venv/bin/pip install -e . --upgrade
```

The dependency is pinned to `mcp>=1.0.0,<2` because MCP SDK v2 changed APIs.

## Snapmaker Orca binary not found

Set one of:

```bash
export SNAPMAKER_ORCA_BIN=/absolute/path/to/AppRun-or-orca-slicer
# or
export SNAPMAKER_ORCA_APPIMAGE=/absolute/path/to/Snapmaker-Orca.AppImage
```

If using an AppImage, ensure it is executable:

```bash
chmod +x /absolute/path/to/Snapmaker-Orca.AppImage
```

The server may extract/cache an AppImage under `$HOME/.snapmaker-u1-mcp/cache`.

## U1 profiles not found

If health reports no U1 profiles, set:

```bash
export SNAPMAKER_PROFILE_DIR=/absolute/path/to/resources/profiles
```

For extracted Snapmaker Orca AppImages this is commonly near:

```text
.../resources/profiles
```

## Slice crashes or no G-code is produced

The server never falls back to upstream OrcaSlicer. It stores debug artifacts in the run directory:

- `request.json`
- `command.json`
- `profiles/`
- `stdout.log`
- `stderr.log`
- `analysis.json`

Use:

```bash
snapmaker-u1-mcp list-runs
snapmaker-u1-mcp get-run RUN_ID
snapmaker-u1-mcp get-run-logs RUN_ID --tail 4000
```

Known Snapmaker Orca Linux CLI `01.10.01.50` issues:

- flattened U1 process profiles containing `wipe_tower_filament` can segfault; generated runtime profiles intentionally omit it for single-material workflows
- non-zero CLI rotation transforms can segfault; use `u1_orientation_preflight` first, and prefer `u1_compare_transformed_orientations` when you need sliced rotated variants

## Paths are rejected

Models must be inside `U1_MODEL_DIR`. Generated G-code and run IDs must be inside `U1_OUTPUT_DIR`. Symlink/path escapes are intentionally rejected.
