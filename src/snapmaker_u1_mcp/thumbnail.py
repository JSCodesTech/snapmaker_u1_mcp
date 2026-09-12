from __future__ import annotations

from pathlib import Path
import base64
import time
import uuid

from .config import Config
from .paths import safe_file
from .preview import u1_render_preview

THUMBNAIL_BEGIN = "; thumbnail begin snapmaker-u1-mcp svg"
THUMBNAIL_END = "; thumbnail end snapmaker-u1-mcp"


def u1_inject_thumbnail(gcode: str, model: str, view: str = "summary") -> dict:
    """Generate an SVG preview and inject it as G-code comment metadata.

    Motion/toolpath commands are not modified. A new G-code file is created in
    the same run directory; the original G-code is left unchanged.
    """
    config = Config.from_env()
    gcode_path = safe_file(config.output_dir, gcode, {".gcode"}, label="G-code")
    preview = u1_render_preview(model, view)
    svg_path = Path(preview["preview"]).resolve()
    svg_bytes = svg_path.read_bytes()
    encoded = base64.b64encode(svg_bytes).decode("ascii")
    block = _thumbnail_block(encoded)

    original = gcode_path.read_text(encoding="utf-8", errors="replace")
    cleaned = _remove_existing_thumbnail(original)
    output = gcode_path.with_name(f"{gcode_path.stem}.thumbnail-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}.gcode")
    output.write_text(block + cleaned, encoding="utf-8")

    return {
        "status": "ok",
        "source_gcode": str(gcode_path),
        "output_gcode": str(output),
        "preview": str(svg_path),
        "thumbnail_format": "svg-base64-comment",
        "motion_unchanged": _non_comment_lines(original) == _non_comment_lines(output.read_text(encoding="utf-8", errors="replace")),
    }


def _thumbnail_block(encoded: str) -> str:
    lines = [THUMBNAIL_BEGIN]
    for i in range(0, len(encoded), 76):
        lines.append(f"; thumbnail: {encoded[i:i + 76]}")
    lines.append(THUMBNAIL_END)
    return "\n".join(lines) + "\n"


def _remove_existing_thumbnail(text: str) -> str:
    lines = text.splitlines(keepends=True)
    output = []
    in_block = False
    for line in lines:
        stripped = line.strip()
        if stripped == THUMBNAIL_BEGIN:
            in_block = True
            continue
        if stripped == THUMBNAIL_END and in_block:
            in_block = False
            continue
        if not in_block:
            output.append(line)
    return "".join(output)


def _non_comment_lines(text: str) -> list[str]:
    return [line.rstrip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith(";")]

