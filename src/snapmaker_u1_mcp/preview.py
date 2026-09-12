from __future__ import annotations

import html
import time
import uuid

from .config import Config
from .models import u1_inspect_model


def u1_render_preview(model: str, view: str = "summary") -> dict:
    """Generate a lightweight SVG model preview from inspected model bounds.

    This is intentionally independent from Snapmaker Orca. It does not render
    toolpaths; it creates a simple dimensional preview suitable for quick agent
    inspection and user-visible metadata.
    """
    if view not in {"summary", "top", "front", "side"}:
        raise ValueError("view must be one of: summary, top, front, side")

    inspection = u1_inspect_model(model)
    config = Config.from_env()
    preview_dir = config.output_dir.expanduser().resolve() / "previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    out = preview_dir / f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}.svg"
    svg = _svg_for_inspection(inspection, view)
    out.write_text(svg, encoding="utf-8")
    return {
        "status": "ok",
        "model": model,
        "view": view,
        "preview": str(out),
        "inspection": inspection,
    }


def u1_render_preview_bundle(model: str) -> dict:
    """Generate summary/top/front/side SVG previews in one explicit bundle."""
    previews = [u1_render_preview(model, view) for view in ("summary", "top", "front", "side")]
    return {
        "status": "ok",
        "model": model,
        "views": {item["view"]: item["preview"] for item in previews},
        "inspection": previews[0]["inspection"] if previews else None,
    }


def _svg_for_inspection(inspection: dict, view: str) -> str:
    dims = inspection.get("dimensions") or {"x": 0, "y": 0, "z": 0}
    build_volume = inspection.get("build_volume") or {"x": 270, "y": 270, "z": 270}
    name = html.escape(str(inspection.get("name") or "model"))
    warnings = inspection.get("warnings") or []
    width, height = 720, 480
    panels = _panels_for_view(view)
    panel_svgs = []
    for idx, (title, axes) in enumerate(panels):
        x = 30 + idx * (width // max(1, len(panels)))
        panel_w = width // max(1, len(panels)) - 45
        panel_svgs.append(_panel(title, axes, dims, build_volume, x, 105, panel_w, 285))
    warn_text = "".join(
        f'<text x="30" y="{420 + i * 18}" font-size="13" fill="#b45309">⚠ {html.escape(str(w))}</text>'
        for i, w in enumerate(warnings[:3])
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="#f8fafc"/>
  <text x="30" y="38" font-size="24" font-family="sans-serif" fill="#0f172a">Snapmaker U1 Model Preview</text>
  <text x="30" y="66" font-size="15" font-family="sans-serif" fill="#334155">{name}</text>
  <text x="30" y="88" font-size="13" font-family="monospace" fill="#475569">Dimensions: X {dims.get('x', 0):.2f} mm · Y {dims.get('y', 0):.2f} mm · Z {dims.get('z', 0):.2f} mm · Build volume {build_volume.get('x', 0):.0f}×{build_volume.get('y', 0):.0f}×{build_volume.get('z', 0):.0f} mm</text>
  {''.join(panel_svgs)}
  {warn_text}
</svg>
'''


def _panels_for_view(view: str) -> list[tuple[str, tuple[str, str]]]:
    if view == "top":
        return [("Top: X/Y", ("x", "y"))]
    if view == "front":
        return [("Front: X/Z", ("x", "z"))]
    if view == "side":
        return [("Side: Y/Z", ("y", "z"))]
    return [("Top: X/Y", ("x", "y")), ("Front: X/Z", ("x", "z")), ("Side: Y/Z", ("y", "z"))]


def _panel(title: str, axes: tuple[str, str], dims: dict, build_volume: dict, x: int, y: int, w: int, h: int) -> str:
    a, b = axes
    da = max(float(dims.get(a) or 0), 0.001)
    db = max(float(dims.get(b) or 0), 0.001)
    ba = max(float(build_volume.get(a) or da), da, 0.001)
    bb = max(float(build_volume.get(b) or db), db, 0.001)
    scale = min((w - 40) / ba, (h - 60) / bb)
    bw = ba * scale
    bh = bb * scale
    brx = x + (w - bw) / 2
    bry = y + 35 + (h - 55 - bh) / 2
    rw = da * scale
    rh = db * scale
    rx = brx + (bw - rw) / 2
    ry = bry + (bh - rh) / 2
    return f'''
  <g font-family="sans-serif">
    <text x="{x}" y="{y}" font-size="16" fill="#0f172a">{html.escape(title)}</text>
    <rect x="{x}" y="{y + 18}" width="{w}" height="{h}" rx="8" fill="#ffffff" stroke="#cbd5e1"/>
    <rect x="{brx:.2f}" y="{bry:.2f}" width="{bw:.2f}" height="{bh:.2f}" fill="none" stroke="#94a3b8" stroke-width="1.5" stroke-dasharray="6 4"/>
    <rect x="{rx:.2f}" y="{ry:.2f}" width="{rw:.2f}" height="{rh:.2f}" fill="#bfdbfe" stroke="#2563eb" stroke-width="2"/>
    <text x="{x + 12}" y="{y + h - 32}" font-size="12" fill="#475569">{a.upper()} {da:.2f} mm × {b.upper()} {db:.2f} mm</text>
    <text x="{x + 12}" y="{y + h - 14}" font-size="11" fill="#64748b">Dashed outline: U1 {a.upper()}/{b.upper()} build area</text>
  </g>
'''
