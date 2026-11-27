#!/usr/bin/env python3
"""Draw an exploded hexagon view of one part of the map: a prototype of how the map page can lift a segment.

    python3 tools/make_hex_view.py [view id] [tag]      # e.g. sandton-rosebank shopping

Reads src/map/hexes.json and src/map/joburg-draft.svg (both from tools/make_map.py), src/data/map.json and
src/data/neighbourhoods.json. Writes src/map/exploded-<view>.svg.

The city lies flat and faded, seen from the south at a tilt, with the ring road on it. The view's areas are lifted out
of it and each is raised into a column of hexagons. A column's height is the number of hexagons the area touches, so
bigger areas stand taller. Every hexagon keeps its colour from the base map's colour wheel; areas with the given tag
are outlined in white and keep full colour, the rest of the segment is softened. A label floats above each column on a short leader line.
"""
import json, math, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HEX = json.loads((ROOT / "src" / "map" / "hexes.json").read_text())
MAP = json.loads((ROOT / "src" / "data" / "map.json").read_text())
DATA = json.loads((ROOT / "src" / "data" / "neighbourhoods.json").read_text())
DRAFT = (ROOT / "src" / "map" / "joburg-draft.svg").read_text()
view_id = sys.argv[1] if len(sys.argv) > 1 else "sandton-rosebank"
tag = sys.argv[2] if len(sys.argv) > 2 else None
view = next(v for v in MAP["views"] if v["id"] == view_id)
places = {p["id"]: p for p in DATA["places"]}
REGION = {"far-north-midrand": "#f5c400", "north-west-randburg": "#18794e", "sandton-rosebank": "#175cd3",
          "central": "#b42318", "east": "#c4320a", "west": "#9e1c5c", "south": "#b54708", "soweto": "#6927da"}
FOREST, FOREST_DARK, PAPER, INK = "#1c4a2e", "#10291a", "#faf8f4", "#1a1c20"
COLOUR = {a: dict(zip(map(tuple, HEX["areas"][a]), HEX["colours"][a])) for a in HEX["areas"]}
TILT, LIFT, PER_HEX, BASE_H = 0.5, 70, 2.5, 8   # y squash, lift of the segment, height per hexagon, minimum height
R = HEX["hex_radius"]


def shade(hexcol, k):
    c = [int(hexcol[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{max(0, min(255, round(v * k))):02x}" for v in c)


def proj(x, y, h=0):
    return x, y * TILT - h


def hexpts(cx, cy, h=0, r=R):
    return [proj(cx + r * math.cos(math.radians(30 + 60 * k)), cy + r * math.sin(math.radians(30 + 60 * k)), h) for k in range(6)]


def poly(pts, **attrs):
    a = " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in attrs.items())
    return f'<path d="M{" L".join(f"{x:.1f},{y:.1f}" for x, y in pts)}Z" {a}/>'


seg = [a for a in view["fit"] if a in HEX["areas"]]
# Grow the segment to the areas next to the named ones, so the lifted piece reads as a part of the city.
near = set(seg)
for a in seg:
    for b, cs in HEX["areas"].items():
        if b not in near and any(math.dist(c, d) < 2.2 * R for c in cs for d in HEX["areas"][a]):
            near.add(b)
seg = sorted(near)
height = {a: BASE_H + PER_HEX * len(HEX["areas"][a]) for a in seg}

out = []
# 1. The flat city, faded, with the ring road.
for a, cs in HEX["areas"].items():
    for cx, cy in cs:
        out.append(poly(hexpts(cx, cy, 0, R * 0.92), fill=COLOUR[a][(cx, cy)], fill_opacity="0.18" if a in seg else "0.55"))
for d in re.findall(r'<path id="ring-n(?:1|3|12)" [^>]*d="([^"]+)"', DRAFT):
    for piece in d.split("M")[1:]:  # each M starts a separate stretch of road
        pts = [tuple(map(float, xy.split(","))) for xy in re.findall(r"[\d.]+,[\d.]+", piece)]
        flat = " L".join(f"{x:.0f},{y * TILT:.0f}" for x, y in pts)
        out.append(f'<path d="M{flat}" fill="none" stroke="{FOREST_DARK}" stroke-width="7" stroke-linejoin="round"/>')
        out.append(f'<path d="M{flat}" fill="none" stroke="{PAPER}" stroke-width="4" stroke-linejoin="round"/>')
# 2. The lifted segment: columns drawn back to front (north first).
cols = sorted(((cy, cx, a) for a in seg for cx, cy in HEX["areas"][a]))
for cy, cx, a in cols:
    hit = bool(tag) and tag in places[a]["tags"]
    col = COLOUR[a][(cx, cy)]
    if tag and not hit:
        col = shade(col, 0.55)  # not a match: softened, so the matches stand out
    top, bot = hexpts(cx, cy, LIFT + height[a]), hexpts(cx, cy, LIFT)
    for k, dark in ((0, 0.62), (1, 0.75)):  # the two south-facing sides: vertices 0-1 and 1-2
        out.append(poly([top[k], top[k + 1], bot[k + 1], bot[k]], fill=shade(col, dark), stroke=FOREST_DARK, stroke_width="0.4", stroke_opacity="0.5"))
    out.append(poly(top, fill=col, stroke=PAPER if hit else FOREST_DARK, stroke_width="1.6" if hit else "0.6"))
# 3. Labels in a column to the right of the segment, each with a leader line to the top of its area's column.
tops = []
for a in seg:
    cs = HEX["areas"][a]
    cx = sum(c[0] for c in cs) / len(cs)
    cy = sum(c[1] for c in cs) / len(cs)
    tops.append((proj(cx, cy, LIFT + height[a]), a))
tops.sort(key=lambda t: t[0][1])
right = max(x for (x, _), _ in tops) + 70
y0 = min(y for (_, y), _ in tops) - 10
for i, ((x, y), a) in enumerate(tops):
    ly = y0 + i * 17
    hit = tag and tag in places[a]["tags"]
    out.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="2.5" fill="{PAPER}"/>')
    out.append(f'<path d="M{x:.0f},{y:.0f} L{right - 40:.0f},{ly:.0f} L{right - 6:.0f},{ly:.0f}" fill="none" stroke="{PAPER}" stroke-width="0.8" stroke-opacity="0.6"/>')
    out.append(f'<text x="{right:.0f}" y="{ly + 4:.0f}" font-family="Inter, Arial, sans-serif" font-size="12" font-weight="{700 if places[a]["major"] else 400}" '
               f'fill="{PAPER}">{places[a]["name"]} ({len(HEX["areas"][a])}){" ★" if hit else ""}</text>')

xs = [float(v) for v in re.findall(r"[ML ](-?[\d.]+),", " ".join(out))]
ys = [float(v) for v in re.findall(r",(-?[\d.]+)", " ".join(out))]
minx, maxx, miny, maxy = min(xs) - 20, max(xs) + 200, min(ys) - 60, max(ys) + 20
title = f'{view["name"]}, lifted out. Height and (number) = hexagons each area touches' + (f'. White outline and ★ = {tag}' if tag else "")
svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{minx:.0f} {miny:.0f} {maxx - minx:.0f} {maxy - miny:.0f}" width="{maxx - minx:.0f}" height="{maxy - miny:.0f}">'
       f'<rect x="{minx:.0f}" y="{miny:.0f}" width="{maxx - minx:.0f}" height="{maxy - miny:.0f}" fill="{FOREST}"/>'
       + "".join(f'<text x="{minx + 16:.0f}" y="{miny + 24 + 18 * i:.0f}" font-family="Inter, Arial, sans-serif" font-size="14" font-weight="{700 if i == 0 else 400}" fill="{PAPER}">{line}</text>'
                 for i, line in enumerate(title.split(". ", 1)))
       + "".join(out) + "</svg>")
path = ROOT / "src" / "map" / f"exploded-{view_id}.svg"
path.write_text(svg + "\n", encoding="utf-8")
print(f"wrote {path.relative_to(ROOT)}: {len(seg)} areas, {len(cols)} hexagon columns")
