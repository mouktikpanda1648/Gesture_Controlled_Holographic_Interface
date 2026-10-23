"""Generate a print-ready, true-scale SVG cutting template for the four pyramid faces.

The pyramid is a truncated square pyramid, small end down on the screen, whose faces
lean at 45 degrees (the standard Pepper's-ghost geometry).  Each face is an isosceles
trapezoid (join the edges with clear tape):  bottom width = BASE, top width = TOP, height (slant) = (TOP - BASE) / sqrt(2).

    python scripts/pyramid_template.py                 # 10 mm base, 70 mm top
    python scripts/pyramid_template.py --base 12 --top 90 -o docs/pyramid_template.svg

Print at 100 % scale (no "fit to page") and check the 50 mm scale bar with a ruler.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path


def build_svg(base: float, top: float, page_w: float = 210.0, page_h: float = 297.0, gap: float = 12.0) -> str:
    if not 0 < base < top:
        raise SystemExit("need 0 < base < top")
    rise = (top - base) / 2               # vertical height of the pyramid at 45 degrees
    slant = rise * math.sqrt(2)           # length of the face along its slope
    margin = 15.0
    cols = max(1, int((page_w - 2 * margin + gap) // (top + gap)))
    rows = math.ceil(4 / cols)
    need_h = rows * slant + (rows - 1) * gap + 2 * margin + 20
    if need_h > page_h:
        raise SystemExit(f"faces do not fit on one {page_w:.0f}x{page_h:.0f} mm page; reduce --top")

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{page_w}mm" height="{page_h}mm" '
        f'viewBox="0 0 {page_w} {page_h}">',
        '<style>.cut{fill:none;stroke:#000;stroke-width:.35}text{font:3.2px sans-serif;fill:#444}</style>',
        f'<text x="{margin}" y="{margin - 5}">Pyramid faces x4 · base {base:g} mm · top {top:g} mm · '
        f'slant {slant:.1f} mm · rise {rise:.1f} mm · print at 100%</text>',
    ]
    for i in range(4):
        r, c = divmod(i, cols)
        x0 = margin + c * (top + gap)
        y0 = margin + r * (slant + gap)
        dx = (top - base) / 2
        pts = [(x0 + dx, y0 + slant), (x0 + dx + base, y0 + slant), (x0 + top, y0), (x0, y0)]
        parts.append('<polygon class="cut" points="' + " ".join(f"{x:.2f},{y:.2f}" for x, y in pts) + '"/>')
        parts.append(f'<text x="{x0 + top / 2 - 3:.1f}" y="{y0 + slant / 2:.1f}">face {i + 1}</text>')
    sy = page_h - margin
    parts += [
        f'<line class="cut" x1="{margin}" y1="{sy}" x2="{margin + 50}" y2="{sy}"/>',
        f'<line class="cut" x1="{margin}" y1="{sy - 2}" x2="{margin}" y2="{sy + 2}"/>',
        f'<line class="cut" x1="{margin + 50}" y1="{sy - 2}" x2="{margin + 50}" y2="{sy + 2}"/>',
        f'<text x="{margin + 14}" y="{sy - 3}">50 mm scale bar</text>',
        "</svg>",
    ]
    return "\n".join(parts)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base", type=float, default=10.0, help="small (bottom) edge, mm")
    p.add_argument("--top", type=float, default=70.0, help="large (top) edge, mm")
    p.add_argument("-o", "--output", type=Path, default=Path("docs/pyramid_template.svg"))
    a = p.parse_args()
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(build_svg(a.base, a.top), encoding="utf-8")
    rise = (a.top - a.base) / 2
    print(f"{a.output}: slant {rise * math.sqrt(2):.1f} mm, height {rise:.1f} mm")


if __name__ == "__main__":
    main()
