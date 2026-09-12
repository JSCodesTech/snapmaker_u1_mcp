# Install and Verify from a Fresh Clone

These steps are intended for users installing from GitHub.

## 1. Clone

```bash
git clone git@github.com:JSCodesTech/snapmaker_u1_mcp.git
cd snapmaker_u1_mcp
```

## 2. Create a virtual environment

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -e '.[test]'
```

## 3. Configure Snapmaker Orca and directories

Use either an executable internal binary/AppRun:

```bash
export SNAPMAKER_ORCA_BIN=/absolute/path/to/AppRun-or-orca-slicer
```

or the AppImage path:

```bash
export SNAPMAKER_ORCA_APPIMAGE=/absolute/path/to/Snapmaker-Orca.AppImage
```

Set model/output directories:

```bash
export U1_MODEL_DIR=$HOME/3D_Printing/models
export U1_OUTPUT_DIR=$HOME/3D_Printing/output
mkdir -p "$U1_MODEL_DIR" "$U1_OUTPUT_DIR"
```

Optional, when profile auto-discovery does not find profiles:

```bash
export SNAPMAKER_PROFILE_DIR=/absolute/path/to/resources/profiles
```

## 4. Verify tests

```bash
.venv/bin/python -m pytest
```

For the coverage gate:

```bash
.venv/bin/python -m pytest --cov=snapmaker_u1_mcp --cov-report=term-missing --cov-fail-under=80
```

## 5. Verify local CLI health

```bash
.venv/bin/python -m snapmaker_u1_mcp.server health
# or, after editable install:
snapmaker-u1-mcp health
```

Expected result: `status` should be `ok` and `errors` should be empty.

## 6. Configure MCP client

Copy `examples/mcp/pi-mcp.json` into your client config and replace absolute paths.

Do not commit your personal MCP config.
