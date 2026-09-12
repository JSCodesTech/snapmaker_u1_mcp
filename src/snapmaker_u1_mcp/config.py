from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


DEFAULT_BASE_DIR = Path.home() / ".snapmaker-u1-mcp"


@dataclass(frozen=True)
class Config:
    """Runtime configuration loaded from environment variables."""

    orca_bin: Path | None
    orca_appimage: Path | None
    profile_dir: Path | None
    model_dir: Path
    output_dir: Path
    cache_dir: Path
    timeout_seconds: int = 300

    @classmethod
    def from_env(cls) -> "Config":
        base = Path(os.environ.get("SNAPMAKER_U1_MCP_HOME", DEFAULT_BASE_DIR)).expanduser()
        return cls(
            orca_bin=_optional_path("SNAPMAKER_ORCA_BIN"),
            orca_appimage=_optional_path("SNAPMAKER_ORCA_APPIMAGE"),
            profile_dir=_optional_path("SNAPMAKER_PROFILE_DIR"),
            model_dir=Path(os.environ.get("U1_MODEL_DIR", base / "models")).expanduser(),
            output_dir=Path(os.environ.get("U1_OUTPUT_DIR", base / "runs")).expanduser(),
            cache_dir=Path(os.environ.get("SNAPMAKER_U1_CACHE_DIR", base / "cache")).expanduser(),
            timeout_seconds=int(os.environ.get("SNAPMAKER_ORCA_TIMEOUT", "300")),
        )


def _optional_path(name: str) -> Path | None:
    value = os.environ.get(name)
    if not value:
        return None
    return Path(value).expanduser()
