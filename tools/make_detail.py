#!/usr/bin/env python3
"""Draw a street-level detail view of a dense area, in the same coordinates as the base map.

    python3 tools/make_detail.py sandton --fetch   # once: streets in the box from OpenStreetMap's main API
    python3 tools/make_detail.py sandton           # draw src/map/detail-sandton.svg

Boxes are listed in DETAILS below (west, south, east, north). --fetch keeps only the streets (type, name, points) in
src/map/source/detail-<id>.json. The drawing is the black-and-white poster style turned negative on the forest: every street
in white, wider for bigger roads, over the base map's colour-wheel hexagons. On top: the hexagon outlines of the areas in the box, the freeways, the attractions and area names.
1 km = 10 units, the same as joburg-draft.svg, so a detail view lines up with the base map.
Street data © OpenStreetMap contributors (ODbL).
"""
import colorsys, json, math, re, sys, urllib.request
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
FOREST, FOREST_DARK, PAPER, INK = "#1c4a2e", "#10291a", "#faf8f4", "#1a1c20"
out = [f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{x1 - x0:.1f}" height="{y1 - y0:.1f}" fill="{FOREST}"/>']
# Detail hexagons: the fine level from map.json (hexes_across_ring at the "detail" level, about 100 m each). Each belongs
# to the area of the nearest city-level hexagon and takes its colour from the same colour wheel as the base map.
R = HEX["hex_radius"]
inbox = lambda x, y: x0 - R < x < x1 + R and y0 - R < y < y1 + R
MAPCFG = json.loads((ROOT / "src" / "data" / "map.json").read_text())
across = next(l["hexes_across_ring"] for l in MAPCFG["hex_levels"] if l["level"] == "detail")
city_across = next(l["hexes_across_ring"] for l in MAPCFG["hex_levels"] if l["level"] == "city")
r = R * city_across / across                       # fine hexagon, centre to corner, in SVG units
SITE = json.loads((ROOT / "src" / "data" / "site.json").read_text())
cbx, cby = xy(SITE["city"]["lng"], SITE["city"]["lat"])


def wheel(x, y):  # the same colour wheel as tools/make_map.py, in SVG units (10 per km)
    dx, dy = x - cbx, y - cby
    bearing = (math.degrees(math.atan2(dx, -dy)) + 360) % 360
    k = min(1.0, math.hypot(dx, dy) / 140)
    rr, gg, bb = colorsys.hls_to_rgb(bearing / 360, 0.80 - 0.22 * k, 0.08 + 0.72 * k)
    return "#" + "".join(f"{round(v * 255):02x}" for v in (rr, gg, bb))


coarse = [(c[0], c[1], a) for a, cs in HEX["areas"].items() for c in cs if inbox(c[0], c[1])]
fine = 0
row, y = 0, y0 - r
while y <= y1 + r:
    x = x0 - r * math.sqrt(3) + (r * math.sqrt(3) / 2 if row % 2 else 0)
    while x <= x1 + r * math.sqrt(3):
        near = min(coarse, key=lambda c: (c[0] - x) ** 2 + (c[1] - y) ** 2) if coarse else None
        if near and (near[0] - x) ** 2 + (near[1] - y) ** 2 < (1.2 * R) ** 2:
            pts = [(x + r * 0.9 * math.cos(math.radians(30 + 60 * k)), y + r * 0.9 * math.sin(math.radians(30 + 60 * k))) for k in range(6)]
            out.append(f'<path d="M{" L".join(f"{px:.2f},{py:.2f}" for px, py in pts)}Z" fill="{wheel(x, y)}" fill-opacity="0.55" data-place="{near[2]}"/>')
            fine += 1
        x += r * math.sqrt(3)
    y += 1.5 * r
    row += 1
print(f"  {fine} detail hexagons, {2 * r * math.sqrt(3) / 2 * 100:.0f} m across")
# Streets, smallest first so bigger roads draw on top.
for st in sorted(det["streets"], key=lambda st: WIDTH[st["type"]]):
    if len(st["pts"]) < 2:
        continue
    d = "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in (xy(*p) for p in st["pts"]))
    out.append(f'<path d="{d}" fill="none" stroke="{PAPER}" stroke-width="{WIDTH[st["type"]]}" stroke-linecap="round" stroke-linejoin="round"/>')
# Freeways and the ring road from the base map, on top in yellow.
for m in re.finditer(r'<path id="(road-(?:m1|m2|ben-schoeman|r21)|ring-n(?:1|3|12))" [^>]*d="([^"]+)"', DRAFT):
    out.append(f'<path d="{m.group(2)}" fill="none" stroke="{FOREST_DARK}" stroke-width="0.5" stroke-opacity="0.9" stroke-linejoin="round"/>')
# Attractions and area names inside the box.
for m in re.finditer(r'<circle id="([^"]+)" data-name="([^"]+)" cx="([\d.]+)" cy="([\d.]+)"', DRAFT):
    cx, cy = float(m.group(3)), float(m.group(4))
    if inbox(cx, cy):
        out.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="0.22" fill="{INK}" stroke="{PAPER}" stroke-width="0.08"/>'
                   f'<text x="{cx + 0.35:.2f}" y="{cy - 0.3:.2f}" font-family="Inter, Arial, sans-serif" font-size="0.42" font-weight="700" fill="{PAPER}" stroke="{FOREST_DARK}" stroke-width="0.12" paint-order="stroke">{m.group(2)}</text>')
for a, cs in HEX["areas"].items():
    mx = sum(c[0] for c in cs) / len(cs); my = sum(c[1] for c in cs) / len(cs)
    if inbox(mx, my):
        out.append(f'<text x="{mx:.2f}" y="{my:.2f}" font-family="Inter, Arial, sans-serif" font-size="0.6" font-weight="700" letter-spacing="0.08" text-anchor="middle" fill="{INK}" stroke="{PAPER}" stroke-width="0.15" paint-order="stroke">{places[a]["name"].upper()}</text>')
out.append(f'<text x="{x1 - 0.2:.2f}" y="{y1 - 0.2:.2f}" font-family="Inter, Arial, sans-serif" font-size="0.3" text-anchor="end" fill="{PAPER}" fill-opacity="0.8">Streets © OpenStreetMap contributors</text>')
W, H = x1 - x0, y1 - y0
svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0:.1f} {y0:.1f} {W:.1f} {H:.1f}" width="{W * 25:.0f}" height="{H * 25:.0f}">'
       f'<clipPath id="box"><rect x="{x0:.1f}" y="{y0:.1f}" width="{W:.1f}" height="{H:.1f}"/></clipPath><g clip-path="url(#box)">' + "".join(out) + "</g></svg>")
path = ROOT / "src" / "map" / f"detail-{key}.svg"
path.write_text(svg + "\n", encoding="utf-8")
print(f"wrote {path.relative_to(ROOT)} ({path.stat().st_size // 1024} KB), {W / U:.1f} by {H / U:.1f} km")
