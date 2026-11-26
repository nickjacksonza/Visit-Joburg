#!/usr/bin/env python3
"""Draw the first draft of the base map, src/map/joburg-draft.svg, from open data.

    pip install shapely          # once; only this tool needs it, the site build does not
    python3 tools/fetch_map_sources.py
    python3 tools/make_map.py            # every area found
    python3 tools/make_map.py --major    # main areas only (the first draft)

Reads src/data/neighbourhoods.json and src/map/source/nominatim.json. Writes the draft SVG and src/map/audit.md.
The draft is a starting point to refine in Figma, true to geography (1 km = 10 SVG units):

- An area mapped as an outline in OpenStreetMap keeps that outline (data-shape="outline").
- An area mapped only as a point gets a rough cell: the ground nearer to it than to any other area's point,
  kept within 2.5 km of the point (data-shape="rough"). Redraw these by hand where it matters.
- An area or attraction not found is left out and listed in audit.md.

Every shape's id is its id in neighbourhoods.json. Layers: regions, areas, city-boundary, attractions, labels,
outlying, credit. Base outlines © OpenStreetMap contributors (ODbL).
"""
import json, math, sys
from pathlib import Path
from shapely.geometry import MultiPoint, Point, mapping, shape
from shapely.ops import unary_union, voronoi_diagram

ROOT = Path(__file__).resolve().parent.parent
DATA = json.loads((ROOT / "src" / "data" / "neighbourhoods.json").read_text(encoding="utf-8"))
SITE = json.loads((ROOT / "src" / "data" / "site.json").read_text(encoding="utf-8"))
SRC = json.loads((ROOT / "src" / "map" / "source" / "nominatim.json").read_text(encoding="utf-8"))
OUT, AUDIT = ROOT / "src" / "map" / "joburg-draft.svg", ROOT / "src" / "map" / "audit.md"
UNIT = 10          # SVG units per km
MAJOR = "--major" in sys.argv
CELL_KM = 4.0 if MAJOR else 2.5   # a rough cell reaches at most this far from its point (main areas are further apart)
MAX_KM2 = 250      # an outline bigger than this is not a suburb; treat the match as a point
PALETTE = {"far-north-midrand": "#f5c400", "north-west-randburg": "#18794e", "sandton-rosebank": "#175cd3",
           "central-east-west": "#b42318", "south": "#b54708", "soweto": "#6927da", "outlying": "#5f646d"}

places = DATA["places"]
regions = {r["id"]: r for r in DATA["regions"]}
hits = {pid: v for pid, v in SRC.items() if v.get("found")}
if MAJOR:  # main areas, the attractions inside them, and the places outside the city
    majors = {p["id"] for p in places if p["major"]}
    places = [p for p in places if p["major"] or p["parent"] in majors or p["region"] == "outlying"]
in_city = [p for p in places if p["region"] != "outlying" and p["id"] in hits]
lat0 = sum(hits[p["id"]]["lat"] for p in in_city) / len(in_city)
lng0 = sum(hits[p["id"]]["lng"] for p in in_city) / len(in_city)
KX, KY = 111.32 * math.cos(math.radians(lat0)), 110.57


def proj(lng, lat):
    """Equirectangular projection centred on the city, in km. Error over 60 km is well under 1%."""
    return ((lng - lng0) * KX, -(lat - lat0) * KY)


def proj_geom(g):
    def ring(cs):
        return [proj(x, y) for x, y in cs]
    gj = g if isinstance(g, dict) else mapping(g)
    t = gj["type"]
    if t == "Point":
        return Point(proj(*gj["coordinates"]))
    if t == "Polygon":
        return shape({"type": "Polygon", "coordinates": [ring(r) for r in gj["coordinates"]]})
    if t == "MultiPolygon":
        return shape({"type": "MultiPolygon", "coordinates": [[ring(r) for r in poly] for poly in gj["coordinates"]]})
    if t in ("LineString", "MultiLineString"):
        return shape({"type": t, "coordinates": ring(gj["coordinates"]) if t == "LineString" else [ring(l) for l in gj["coordinates"]]})
    return None


# ---------------------------------------------------------------- areas: outlines where mapped, rough cells elsewhere
areas = [p for p in in_city if p["kind"] == "area"]
pts, outlines, notes = {}, {}, {}
for p in areas:
    h = hits[p["id"]]
    pts[p["id"]] = Point(proj(h["lng"], h["lat"]))
    g = proj_geom(h["geojson"])
    if g is not None and g.geom_type in ("Polygon", "MultiPolygon"):
        if g.area <= MAX_KM2:
            outlines[p["id"]] = g.buffer(0)
        else:
            notes[p["id"]] = f"outline of {g.area:.0f} km² is too big for one area; drawn as a rough cell"

study = unary_union([pt.buffer(CELL_KM + 0.5) for pt in pts.values()] + list(outlines.values())).buffer(1).buffer(-1)
cells = voronoi_diagram(MultiPoint(list(pts.values())), envelope=study.envelope.buffer(5))
cell_of = {}
for c in cells.geoms:
    for pid, pt in pts.items():
        if c.contains(pt):
            cell_of[pid] = c
            break
taken = unary_union(list(outlines.values())) if outlines else None
shapes, kinds = {}, {}
for p in areas:
    pid = p["id"]
    if pid in outlines:
        shapes[pid], kinds[pid] = outlines[pid], "outline"
        continue
    g = cell_of[pid].intersection(pts[pid].buffer(CELL_KM)).intersection(study)
    if taken is not None:
        g = g.difference(taken)
    if g.is_empty:  # the point sits inside another area's outline: keep a small disc so it can still be found
        g = pts[pid].buffer(0.4)
    shapes[pid], kinds[pid] = g, "rough"

# ---------------------------------------------------------------- SVG
allg = unary_union(list(shapes.values()) + [study])
minx, miny, maxx, maxy = allg.bounds
PAD = 6  # km of margin, room for the edge markers
ox, oy = minx - PAD, miny - PAD
W, H = (maxx - minx + 2 * PAD) * UNIT, (maxy - miny + 2 * PAD) * UNIT


def xy(x, y):
    return f"{(x - ox) * UNIT:.0f},{(y - oy) * UNIT:.0f}"


def path_d(g):
    g = g.simplify(0.05, preserve_topology=True)  # 50 m: plenty for a draft, and keeps the file small
    polys = [g] if g.geom_type == "Polygon" else list(getattr(g, "geoms", []))
    out = []
    for poly in polys:
        if poly.geom_type != "Polygon" or poly.is_empty:
            continue
        for ring in [poly.exterior, *poly.interiors]:
            cs = list(ring.coords)[:-1]
            out.append("M" + " L".join(xy(*c) for c in cs) + "Z")
    return " ".join(out)


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")


svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.0f} {H:.0f}" width="{W:.0f}" height="{H:.0f}">',
       f'<rect id="background" width="{W:.0f}" height="{H:.0f}" fill="#faf8f4"/>']

svg.append('<g id="regions">')
for rid, r in regions.items():
    members = [shapes[p["id"]] for p in areas if p["region"] == rid]
    if members:
        g = unary_union(members).buffer(0.15).buffer(-0.15)
        svg.append(f'<path id="region-{rid}" data-name="{esc(r["name"])}" d="{path_d(g)}" fill="{PALETTE[rid]}" fill-opacity="0.10" stroke="{PALETTE[rid]}" stroke-width="3"/>')
svg.append("</g>")

svg.append('<g id="areas">')
for p in areas:
    pid = p["id"]
    c = PALETTE[p["region"]]
    svg.append(f'<path id="{pid}" data-name="{esc(p["name"])}" data-region="{p["region"]}" data-shape="{kinds[pid]}"'
               f'{" data-major=\"true\"" if p["major"] else ""} d="{path_d(shapes[pid])}" fill="{c}" fill-opacity="{0.22 if kinds[pid] == "outline" else 0.12}" '
               f'stroke="#1a1c20" stroke-opacity="0.45" stroke-width="{1 if kinds[pid] == "outline" else 0.6}"'
               f'{" stroke-dasharray=\"3 2\"" if kinds[pid] == "rough" else ""}/>')
svg.append("</g>")

city = SRC.get("_city", {})
if city.get("found"):
    g = proj_geom(city["geojson"])
    if g is not None and g.geom_type in ("Polygon", "MultiPolygon"):
        svg.append(f'<g id="city-boundary"><path id="city-of-johannesburg" d="{path_d(g)}" fill="none" stroke="#1a1c20" stroke-width="2.5" stroke-dasharray="10 5" stroke-opacity="0.6"/></g>')

svg.append('<g id="attractions">')
seen = set()
for p in places:
    if p["kind"] != "attraction" or p["region"] == "outlying":
        continue
    a = next((a for a in SITE["attractions"] if a["id"] == p.get("attraction_id")), None)
    if a:
        x, y = proj(a["lng"], a["lat"])
    elif p["id"] in hits:
        x, y = proj(hits[p["id"]]["lng"], hits[p["id"]]["lat"])
    else:
        continue
    seen.add(p.get("attraction_id"))
    svg.append(f'<circle id="{p["id"]}" data-name="{esc(p["name"])}" cx="{(x - ox) * UNIT:.1f}" cy="{(y - oy) * UNIT:.1f}" r="6" fill="#b54708" stroke="#faf8f4" stroke-width="2"/>')
for a in SITE["attractions"]:  # the detailed things-to-do attractions not already listed under an area
    if a["id"] in seen or (MAJOR and a.get("neighbourhood") not in {p["id"] for p in areas}):
        continue
    x, y = proj(a["lng"], a["lat"])
    if not (minx - PAD < x < maxx + PAD and miny - PAD < y < maxy + PAD):
        continue
    svg.append(f'<circle id="{a["id"]}" data-name="{esc(a["name"])}" cx="{(x - ox) * UNIT:.1f}" cy="{(y - oy) * UNIT:.1f}" r="6" fill="#b54708" stroke="#faf8f4" stroke-width="2"/>')
svg.append("</g>")

svg.append('<g id="labels">')
for p in areas:
    c = shapes[p["id"]].representative_point()
    size, weight = (15, 700) if p["major"] else (10, 400)
    svg.append(f'<text id="label-{p["id"]}" x="{(c.x - ox) * UNIT:.1f}" y="{(c.y - oy) * UNIT:.1f}" font-family="Inter, Arial, sans-serif" '
               f'font-size="{size}" font-weight="{weight}" text-anchor="middle" fill="#1a1c20">{esc(p["name"])}</text>')
svg.append("</g>")

# Places outside the map: an arrow on the edge pointing their way.
svg.append('<g id="outlying">')
cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
for p in places:
    if p["region"] != "outlying" or p["id"] not in hits:
        continue
    x, y = proj(hits[p["id"]]["lng"], hits[p["id"]]["lat"])
    dx, dy = x - cx, y - cy
    k = min((maxx - cx + PAD * 0.5) / abs(dx) if dx else 1e9, (maxy - cy + PAD * 0.5) / abs(dy) if dy else 1e9)
    ex, ey = cx + dx * k, cy + dy * k
    km = math.hypot(x - ex, y - ey)
    ang = math.degrees(math.atan2(dy, dx))
    sx, sy = (ex - ox) * UNIT, (ey - oy) * UNIT
    svg.append(f'<g id="{p["id"]}" data-name="{esc(p["name"])}"><path d="M-10,-7 L10,0 L-10,7 Z" transform="translate({sx:.1f},{sy:.1f}) rotate({ang:.0f})" fill="#5f646d"/>'
               f'<text x="{sx:.1f}" y="{sy + 24:.1f}" font-family="Inter, Arial, sans-serif" font-size="13" text-anchor="middle" fill="#1a1c20">{esc(p["name"])} ({km:.0f} km)</text></g>')
svg.append("</g>")
svg.append(f'<g id="credit"><text x="{W - 12:.0f}" y="{H - 12:.0f}" font-family="Inter, Arial, sans-serif" font-size="12" text-anchor="end" fill="#5f646d">Base outlines © OpenStreetMap contributors</text></g>')
svg.append("</svg>")
OUT.write_text("\n".join(svg) + "\n", encoding="utf-8")

# ---------------------------------------------------------------- audit
missing = [p for p in places if p["id"] not in hits]
lines = ["# Map draft audit", "", f"Draft of {'main areas only' if MAJOR else 'every area'}.", "", f"Drawn from src/map/source/nominatim.json by tools/make_map.py. 1 km = {UNIT} SVG units. The draft is {W / UNIT:.0f} by {H / UNIT:.0f} km.", "",
         f"- Areas with an OpenStreetMap outline: {sum(v == 'outline' for v in kinds.values())}",
         f"- Areas drawn as rough cells from a point: {sum(v == 'rough' for v in kinds.values())}",
         f"- Places not found: {len(missing)}", ""]
if missing:
    lines += ["## Not found", "", "Add these by hand in Figma, or fix the name and fetch again.", ""]
    lines += [f"- {p['name']} ({p['kind']}, {regions[p['region']]['name']})" for p in missing] + [""]
if notes:
    lines += ["## Notes", ""] + [f"- {PLACES_NAME}: {n}" for PLACES_NAME, n in ((next(p['name'] for p in places if p['id'] == k), v) for k, v in notes.items())] + [""]
lines += ["## Check these matches", "", "The search may have found a place with the same name elsewhere. Each line is the place and what it matched.", ""]
lines += [f"- {p['name']}: {hits[p['id']]['display_name'][:110]}" for p in places if p["id"] in hits]
AUDIT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size // 1024} KB), {AUDIT.relative_to(ROOT)}")
print(f"outlines {sum(v == 'outline' for v in kinds.values())}, rough {sum(v == 'rough' for v in kinds.values())}, missing {len(missing)}")
