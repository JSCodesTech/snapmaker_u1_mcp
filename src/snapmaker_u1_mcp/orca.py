from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

from .config import Config
from .errors import ConfigurationError

HELP_FLAGS_REQUIRED = ("--slice", "--load-settings", "--load-filaments", "--outputdir")


def locate_slicer(config: Config) -> Path:
    """Locate a Snapmaker Orca CLI binary without falling back to upstream OrcaSlicer."""
    candidates: list[Path] = []
    if config.orca_bin:
        candidates.append(config.orca_bin)
    if config.orca_appimage:
        candidates.extend(appimage_candidates(config.orca_appimage, config.cache_dir))
    for path in candidates:
        if path.exists() and path.is_file():
            return path.resolve()
    raise ConfigurationError(
        "Snapmaker Orca binary not found. Set SNAPMAKER_ORCA_BIN to the internal slicer binary "
        "or SNAPMAKER_ORCA_APPIMAGE to a Snapmaker Orca AppImage."
    )


def appimage_candidates(appimage: Path, cache_dir: Path) -> list[Path]:
    appimage = appimage.expanduser().resolve()
    extracted = cache_dir / "snapmaker-orca-appimage"
    candidates = [
        extracted / "AppRun",
        extracted / "usr/bin/orca-slicer",
        extracted / "usr/bin/snapmaker-orca",
        extracted / "bin/orca-slicer",
    ]
    if not extracted.exists() and appimage.exists():
        extracted.mkdir(parents=True, exist_ok=True)
        # Extract into local cache only; never modifies the user's original AppImage.
        subprocess.run([str(appimage), "--appimage-extract"], shell=False, cwd=extracted, text=True, capture_output=True, timeout=120)
        squashfs = extracted / "squashfs-root"
        if squashfs.exists():
            for child in squashfs.iterdir():
                target = extracted / child.name
                if not target.exists():
                    shutil.move(str(child), str(target))
            shutil.rmtree(squashfs, ignore_errors=True)
    return candidates


def build_slice_command(
    binary: Path,
    model: Path,
    output_dir: Path,
    machine: Path,
    process: Path,
    filament: Path,
    orientation_args: list[str] | None = None,
) -> list[str]:
    return [
        str(binary),
        "--debug", "5",
        *(orientation_args or []),
        "--load-settings", str(machine),
        "--load-settings", str(process),
        "--load-filaments", str(filament),
        "--outputdir", str(output_dir),
        "--slice", "0",
        str(model),
    ]


def classify_failure(returncode: int, stdout: str, stderr: str) -> str:
    logs = f"{stdout}\n{stderr}".lower()
    if returncode < 0 or returncode == 139 or "segmentation fault" in logs:
        return "snapmaker_orca_cli_crash"
    if "from" in logs and "unsupported" in logs:
        return "profile_runtime_format"
    if "not compatible with printer" in logs:
        return "profile_compatibility"
    if "no g-code" in logs or "no g-code file" in logs:
        return "slicing_no_output"
    return "unknown"
