#!/usr/bin/env python3
"""Draw a street-level detail view of a dense area, in the same coordinates as the base map.

    python3 tools/make_detail.py sandton --fetch   # once: streets in the box from OpenStreetMap's main API
    python3 tools/make_detail.py sandton           # draw src/map/detail-sandton.svg

Boxes are listed in DETAILS below (west, south, east, north). --fetch keeps only the streets (type, name, points) in
src/map/source/detail-<id>.json. The drawing follows the black-and-white poster style: every street in black, wider
for bigger roads. On top: the hexagon outlines of the areas in the box, the freeways, the attractions and area names.
1 km = 10 units, the same as joburg-draft.svg, so a detail view lines up with the base map.
Street data © OpenStreetMap contributors (ODbL).
"""
import json, math, re, sys, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DETAILS = {"sandton": {"name": "Sandton centre", "bbox": (28.035, -26.122, 28.075, -26.092)}}
AGENT = "visit-joburg-map-draft/0.1 (static site build tool)"
# Line widths in SVG units (1 unit = 100 m): a primary road draws about 22 m wide, a service lane about 4 m.
WIDTH = {"motorway": 0.32, "trunk": 0.26, "primary": 0.22, "secondary": 0.17, "tertiary": 0.13, "motorway_link": 0.14, "trunk_link": 0.12,
         "primary_link": 0.11, "secondary_link": 0.10, "tertiary_link": 0.09, "residential": 0.07, "unclassified": 0.07, "living_street": 0.06, "service": 0.035}

key = sys.argv[1] if len(sys.argv) > 1 else "sandton"
spec = DETAILS[key]
src = ROOT / "src" / "map" / "source" / f"detail-{key}.json"
if "--fetch" in sys.argv:
    w, s, e, n = spec["bbox"]
    req = urllib.request.Request(f"https://api.openstreetmap.org/api/0.6/map.json?bbox={w},{s},{e},{n}", headers={"User-Agent": AGENT})
    with urllib.request.urlopen(req, timeout=180) as r:
        els = json.load(r)["elements"]
    nodes = {e["id"]: (round(e["lon"], 6), round(e["lat"], 6)) for e in els if e["type"] == "node"}
    streets = [{"type": e["tags"]["highway"], "name": e["tags"].get("name", ""), "pts": [nodes[i] for i in e["nodes"] if i in nodes]}
               for e in els if e["type"] == "way" and e.get("tags", {}).get("highway") in WIDTH]
    src.write_text(json.dumps({"bbox": spec["bbox"], "streets": streets}, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"wrote {src.relative_to(ROOT)}: {len(streets)} streets")

HEX = json.loads((ROOT / "src" / "map" / "hexes.json").read_text())
P = HEX["projection"]
U = HEX["unit_per_km"]
DATA = json.loads((ROOT / "src" / "data" / "neighbourhoods.json").read_text())
places = {p["id"]: p for p in DATA["places"]}
DRAFT = (ROOT / "src" / "map" / "joburg-draft.svg").read_text()
det = json.loads(src.read_text())


def xy(lng, lat):
    return ((lng - P["lng0"]) * P["kx"] - P["ox"]) * U, (-(lat - P["lat0"]) * P["ky"] - P["oy"]) * U


w, s, e, n = det["bbox"]
x0, y1 = xy(w, s)
x1, y0 = xy(e, n)
out = [f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{x1 - x0:.1f}" height="{y1 - y0:.1f}" fill="#faf8f4"/>']
# Hexagons of the areas in the box, as faint coloured outlines under the streets.
R = HEX["hex_radius"]
inbox = lambda x, y: x0 - R < x < x1 + R and y0 - R < y < y1 + R
for a, cs in HEX["areas"].items():
    for cx, cy in cs:
        if inbox(cx, cy):
            pts = [(cx + R * math.cos(math.radians(30 + 60 * k)), cy + R * math.sin(math.radians(30 + 60 * k))) for k in range(6)]
            out.append(f'<path id="hex-{a}-{cx:.0f}-{cy:.0f}" d="M{" L".join(f"{x:.2f},{y:.2f}" for x, y in pts)}Z" fill="#175cd3" fill-opacity="0.06" stroke="#175cd3" stroke-opacity="0.45" stroke-width="0.05"/>')
# Streets, smallest first so bigger roads draw on top.
for st in sorted(det["streets"], key=lambda st: WIDTH[st["type"]]):
    if len(st["pts"]) < 2:
        continue
    d = "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in (xy(*p) for p in st["pts"]))
    out.append(f'<path d="{d}" fill="none" stroke="#1a1c20" stroke-width="{WIDTH[st["type"]]}" stroke-linecap="round" stroke-linejoin="round"/>')
# Freeways and the ring road from the base map, on top in yellow.
for m in re.finditer(r'<path id="(road-(?:m1|m2|ben-schoeman|r21)|ring-n(?:1|3|12))" [^>]*d="([^"]+)"', DRAFT):
    out.append(f'<path d="{m.group(2)}" fill="none" stroke="#f5c400" stroke-width="0.45" stroke-opacity="0.85" stroke-linejoin="round"/>')
# Attractions and area names inside the box.
for m in re.finditer(r'<circle id="([^"]+)" data-name="([^"]+)" cx="([\d.]+)" cy="([\d.]+)"', DRAFT):
    cx, cy = float(m.group(3)), float(m.group(4))
    if inbox(cx, cy):
        out.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="0.22" fill="#b54708" stroke="#faf8f4" stroke-width="0.08"/>'
                   f'<text x="{cx + 0.35:.2f}" y="{cy - 0.3:.2f}" font-family="Inter, Arial, sans-serif" font-size="0.42" font-weight="700" fill="#b54708" stroke="#faf8f4" stroke-width="0.1" paint-order="stroke">{m.group(2)}</text>')
for a, cs in HEX["areas"].items():
    mx = sum(c[0] for c in cs) / len(cs); my = sum(c[1] for c in cs) / len(cs)
    if inbox(mx, my):
        out.append(f'<text x="{mx:.2f}" y="{my:.2f}" font-family="Inter, Arial, sans-serif" font-size="0.6" font-weight="700" letter-spacing="0.08" text-anchor="middle" fill="#175cd3" stroke="#faf8f4" stroke-width="0.15" paint-order="stroke">{places[a]["name"].upper()}</text>')
out.append(f'<text x="{x1 - 0.2:.2f}" y="{y1 - 0.2:.2f}" font-family="Inter, Arial, sans-serif" font-size="0.3" text-anchor="end" fill="#5f646d">Streets © OpenStreetMap contributors</text>')
W, H = x1 - x0, y1 - y0
svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0:.1f} {y0:.1f} {W:.1f} {H:.1f}" width="{W * 25:.0f}" height="{H * 25:.0f}">'
       f'<clipPath id="box"><rect x="{x0:.1f}" y="{y0:.1f}" width="{W:.1f}" height="{H:.1f}"/></clipPath><g clip-path="url(#box)">' + "".join(out) + "</g></svg>")
path = ROOT / "src" / "map" / f"detail-{key}.svg"
path.write_text(svg + "\n", encoding="utf-8")
print(f"wrote {path.relative_to(ROOT)} ({path.stat().st_size // 1024} KB), {W / U:.1f} by {H / U:.1f} km")
