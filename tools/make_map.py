#!/usr/bin/env python3
"""Draw the first draft of the base map, src/map/joburg-draft.svg, from open data.

    pip install shapely          # once; only this tool needs it, the site build does not
    python3 tools/fetch_map_sources.py
    python3 tools/make_map.py            # every area found
    python3 tools/make_map.py --major    # main areas only (the first draft)

Reads src/data/neighbourhoods.json, src/map/source/nominatim.json and src/map/source/positions.json. Writes the draft SVG and src/map/audit.md.
The draft is a starting point to refine in Figma, true to geography (1 km = 10 SVG units):

- An area mapped as an outline in OpenStreetMap keeps that outline (data-shape="outline").
- An area mapped only as a point gets a rough cell: the ground nearer to it than to any other area's point,
  kept within 2.5 km of the point (data-shape="rough"). Redraw these by hand where it matters.
- An area or attraction not found is left out and listed in audit.md.

Every shape's id is its id in neighbourhoods.json. Layers: regions, areas, hexes, ring-road, city-boundary, attractions,
labels, outlying, credit.

Ring road: the N1 Western, N3 Eastern and N12 Southern Bypass from src/map/source/roads.json, drawn thick on a dark
casing so it is the first thing a visitor sees, with a route marker on each. Its turnoffs (layer ring-turnoffs: a stop
and exit number at each interchange, full name in data-name) and bridges (layer ring-bridges) come from
src/map/source/ring_details.json. Both carriageways' points are merged into one per turnoff and per bridge.

Hexes: a grid of pointy-top hexagons (HEX_KM from centre to corner) laid over the areas. Each hexagon belongs to the
area its centre falls in, and every area keeps at least one. Each area's hexagons form one shape, id hex-<place id>.
The map page fills these when a toggle (a tag or visitor type) matches the area. Base outlines © OpenStreetMap contributors (ODbL).
"""
import json, math, sys
from pathlib import Path
from shapely.geometry import MultiPoint, Point, mapping, shape
from shapely.geometry import LineString, MultiLineString
from shapely.ops import linemerge, unary_union, voronoi_diagram

ROOT = Path(__file__).resolve().parent.parent
DATA = json.loads((ROOT / "src" / "data" / "neighbourhoods.json").read_text(encoding="utf-8"))
SITE = json.loads((ROOT / "src" / "data" / "site.json").read_text(encoding="utf-8"))
SRC = json.loads((ROOT / "src" / "map" / "source" / "nominatim.json").read_text(encoding="utf-8"))
OUT, AUDIT = ROOT / "src" / "map" / "joburg-draft.svg", ROOT / "src" / "map" / "audit.md"
UNIT = 10          # SVG units per km
MAJOR = "--major" in sys.argv
CELL_KM = 4.0 if MAJOR else 2.5   # a rough cell reaches at most this far from its point (main areas are further apart)
MAPCFG = json.loads((ROOT / "src" / "data" / "map.json").read_text(encoding="utf-8"))
HEX_KM = 0.8      # hexagon size, centre to corner; replaced below by the ring road's width / hexes_across_ring
MAX_KM2 = 250      # an outline bigger than this is not a suburb; treat the match as a point
PALETTE = {"far-north-midrand": "#f5c400", "north-west-randburg": "#18794e", "sandton-rosebank": "#175cd3",
           "central-east-west": "#b42318", "south": "#b54708", "soweto": "#6927da", "outlying": "#5f646d"}

places = DATA["places"]
if MAJOR:  # main areas, the attractions inside them, and the places outside the city
    majors = {p["id"] for p in places if p["major"]}
    places = [p for p in places if p["major"] or p["parent"] in majors or p["region"] == "outlying"]
regions = {r["id"]: r for r in DATA["regions"]}
hits = {pid: dict(v) for pid, v in SRC.items() if v.get("found")}
for p in places:  # a position already in neighbourhoods.json beats a search result
    if p.get("geo") and p["id"] in hits:
        hits[p["id"]].update(lat=p["geo"]["lat"], lng=p["geo"]["lng"], geojson={"type": "Point", "coordinates": [p["geo"]["lng"], p["geo"]["lat"]]})
    elif p.get("geo"):
        hits[p["id"]] = {"found": True, "display_name": "position from neighbourhoods.json", "lat": p["geo"]["lat"], "lng": p["geo"]["lng"],
                         "geojson": {"type": "Point", "coordinates": [p["geo"]["lng"], p["geo"]["lat"]]}}
# A match more than FAR_KM from the city centre (80 km for places outside the city) is the same name somewhere else: drop it.
FAR_KM = 40
CBD = SITE["city"]
for p in places:
    h = hits.get(p["id"])
    if h and math.hypot((h["lng"] - CBD["lng"]) * 100, (h["lat"] - CBD["lat"]) * 111) > (80 if p["region"] == "outlying" else FAR_KM):
        del hits[p["id"]]
_pos = ROOT / "src" / "map" / "source" / "positions.json"
for pid, v in (json.loads(_pos.read_text(encoding="utf-8")) if _pos.exists() else {}).items():
    if not pid.startswith("_") and pid not in hits:  # positions for places the search could not find
        hits[pid] = {"found": True, "display_name": v["source"], "lat": v["lat"], "lng": v["lng"],
                     "geojson": {"type": "Point", "coordinates": [v["lng"], v["lat"]]}}
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

# ---------------------------------------------------------------- hexagon grid for highlighting
# The ring road sets the scale: the whole-city view frames it, and hexes_across_ring hexagons span its width.
_roads_file = ROOT / "src" / "map" / "source" / "roads.json"
RING_BOX = None
if _roads_file.exists():
    _ring = unary_union([proj_geom(s) for r in json.loads(_roads_file.read_text(encoding="utf-8")).values() for s in r["segments"]])
    RING_BOX = _ring.bounds
    HEX_KM = (RING_BOX[2] - RING_BOX[0]) / MAPCFG.get("hexes_across_ring", 20) / math.sqrt(3)



def hexagon(cx, cy, r=HEX_KM):
    return [(cx + r * math.cos(math.radians(30 + 60 * k)), cy + r * math.sin(math.radians(30 + 60 * k))) for k in range(6)]


hex_of = {p["id"]: [] for p in areas}
_w, _h = math.sqrt(3) * HEX_KM, 1.5 * HEX_KM
_minx, _miny, _maxx, _maxy = unary_union(list(shapes.values())).bounds
centres = []
row, y = 0, _miny - _h
while y <= _maxy + _h:
    x = _minx - _w + (_w / 2 if row % 2 else 0)
    while x <= _maxx + _w:
        centres.append((x, y))
        x += _w
    y += _h
    row += 1
owner = {}
for c in centres:
    pt = Point(c)
    for p in areas:  # outlines first (they are real boundaries), then rough cells
        if kinds[p["id"]] == "outline" and shapes[p["id"]].contains(pt):
            owner[c] = p["id"]
            break
    else:
        for p in areas:
            if shapes[p["id"]].contains(pt):
                owner[c] = p["id"]
                break
for c, pid in owner.items():
    hex_of[pid].append(c)
for p in areas:  # a small area with no hexagon takes the nearest one from a neighbour that has more than one
    pid = p["id"]
    if hex_of[pid]:
        continue
    rp = shapes[pid].representative_point()
    for c in sorted(centres, key=lambda c: (c[0] - rp.x) ** 2 + (c[1] - rp.y) ** 2):
        donor = owner.get(c)
        if donor is None or len(hex_of[donor]) > 1:
            if donor:
                hex_of[donor].remove(c)
            owner[c] = pid
            hex_of[pid].append(c)
            break

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

svg.append('<g id="hexes">')
for p in areas:
    d = " ".join("M" + " L".join(f"{(x - ox) * UNIT:.1f},{(y - oy) * UNIT:.1f}" for x, y in hexagon(cx, cy)) + "Z" for cx, cy in hex_of[p["id"]])
    svg.append(f'<path id="hex-{p["id"]}" data-place="{p["id"]}" d="{d}" fill="{PALETTE[p["region"]]}" fill-opacity="0.35" stroke="#faf8f4" stroke-width="1.5"/>')
svg.append("</g>")

# Other freeways and main roads, under the ring road so the ring stays the most prominent line.
_main = ROOT / "src" / "map" / "source" / "main_roads.json"
if _main.exists():
    MR = json.loads(_main.read_text(encoding="utf-8"))
    _frame = shape({"type": "Polygon", "coordinates": [[(ox, oy), (ox + W / UNIT, oy), (ox + W / UNIT, oy + H / UNIT), (ox, oy + H / UNIT), (ox, oy)]]})
    drawn = []
    for key, r in MR.items():
        parts = []
        for seg in r["segments"]:
            g = proj_geom(seg)
            if g is not None:
                parts += list(g.geoms) if g.geom_type == "MultiLineString" else [g]
        if not parts:
            continue
        merged = linemerge(unary_union(parts)).intersection(_frame).simplify(0.05)
        segs = [s for s in (merged.geoms if hasattr(merged, "geoms") else [merged]) if s.geom_type == "LineString" and s.length > 0.15]
        if not segs:
            continue
        d = " ".join("M" + " L".join(f"{(x - ox) * UNIT:.0f},{(y - oy) * UNIT:.0f}" for x, y in s.coords) for s in segs)
        drawn.append((key, r, d, max(segs, key=lambda s: s.length)))
    svg.append('<g id="main-roads">')
    for key, r, d, _ in drawn:
        if r["kind"] == "main":
            svg.append(f'<path id="road-{key}-casing" d="{d}" fill="none" stroke="#5f646d" stroke-opacity="0.7" stroke-width="4.5" stroke-linecap="round" stroke-linejoin="round"/>')
    for key, r, d, _ in drawn:
        if r["kind"] == "main":
            svg.append(f'<path id="road-{key}" data-name="{esc(r["name"])}" d="{d}" fill="none" stroke="#faf8f4" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>')
    for key, r, d, longest in drawn:  # name along the road, at the middle of its longest stretch
        if r["kind"] != "main":
            continue
        a, b = longest.interpolate(0.47, normalized=True), longest.interpolate(0.53, normalized=True)
        ang = math.degrees(math.atan2(b.y - a.y, b.x - a.x))
        if ang > 90 or ang < -90:
            ang -= 180 if ang > 0 else -180
        m = longest.interpolate(0.5, normalized=True)
        mx, my = (m.x - ox) * UNIT, (m.y - oy) * UNIT
        svg.append(f'<text id="road-label-{key}" x="{mx:.0f}" y="{my + 3:.0f}" transform="rotate({ang:.0f} {mx:.0f} {my:.0f})" font-family="Inter, Arial, sans-serif" font-size="8" '
                   f'font-weight="700" text-anchor="middle" fill="#1a1c20" stroke="#faf8f4" stroke-width="2.5" paint-order="stroke">{esc(r["label"])}</text>')
    svg.append("</g>")
    svg.append('<g id="freeways">')
    for key, r, d, _ in drawn:
        if r["kind"] == "freeway":
            svg.append(f'<path id="road-{key}-casing" d="{d}" fill="none" stroke="#1a1c20" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>')
    for key, r, d, _ in drawn:
        if r["kind"] == "freeway":
            svg.append(f'<path id="road-{key}" data-name="{esc(r["name"])}" d="{d}" fill="none" stroke="#f5c400" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>')
    for key, r, d, longest in drawn:
        if r["kind"] != "freeway":
            continue
        m = longest.interpolate(0.5, normalized=True)
        mx, my = (m.x - ox) * UNIT, (m.y - oy) * UNIT
        w = 10 + 7 * len(r["label"])
        svg.append(f'<g id="marker-{key}"><rect x="{mx - w / 2:.0f}" y="{my - 9:.0f}" width="{w}" height="18" rx="4" fill="#175cd3" stroke="#faf8f4" stroke-width="1.5"/>'
                   f'<text x="{mx:.0f}" y="{my + 4:.0f}" font-family="Inter, Arial, sans-serif" font-size="11" font-weight="700" text-anchor="middle" fill="#faf8f4">{esc(r["label"])}</text></g>')
    svg.append("</g>")

_roads = ROOT / "src" / "map" / "source" / "roads.json"
if _roads.exists():
    ROADS = json.loads(_roads.read_text(encoding="utf-8"))
    frame = shape({"type": "Polygon", "coordinates": [[(ox, oy), (ox + W / UNIT, oy), (ox + W / UNIT, oy + H / UNIT), (ox, oy + H / UNIT), (ox, oy)]]})
    lines_d, markers = [], []
    for key, r in ROADS.items():
        parts = []
        for seg in r["segments"]:
            g = proj_geom(seg)
            parts += list(g.geoms) if g.geom_type == "MultiLineString" else [g]
        merged = linemerge(unary_union(parts)).intersection(frame).simplify(0.06)
        segs = list(merged.geoms) if hasattr(merged, "geoms") else [merged]
        d = " ".join("M" + " L".join(f"{(x - ox) * UNIT:.0f},{(y - oy) * UNIT:.0f}" for x, y in s.coords) for s in segs if s.geom_type == "LineString" and s.length > 0.2)
        lines_d.append((key, r, d))
        longest = max((s for s in segs if s.geom_type == "LineString"), key=lambda s: s.length)
        _rd = ROOT / "src" / "map" / "source" / "ring_details.json"
        stops = [Point(proj(j["lng"], j["lat"])) for j in json.loads(_rd.read_text(encoding="utf-8"))["junctions"]] if _rd.exists() else []
        cands = [longest.interpolate(f / 20, normalized=True) for f in range(3, 18)]
        m = max(cands, key=lambda pt: min((pt.distance(s) for s in stops), default=0))  # the stretch furthest from any turnoff
        bx, by = proj(CBD["lng"], CBD["lat"])
        ux, uy = m.x - bx, m.y - by
        n = math.hypot(ux, uy) or 1
        m = Point(m.x + ux / n * 2.4, m.y + uy / n * 2.4)  # just outside the ring, beyond the exit numbers
        markers.append((key, r, (m.x - ox) * UNIT, (m.y - oy) * UNIT))
    svg.append('<g id="ring-road">')
    for key, r, d in lines_d:  # dark casing under each road, then the road on top
        svg.append(f'<path id="ring-{key}-casing" d="{d}" fill="none" stroke="#1a1c20" stroke-width="11" stroke-linecap="round" stroke-linejoin="round"/>')
    for key, r, d in lines_d:
        svg.append(f'<path id="ring-{key}" data-name="{r["number"]} {esc(r["name"])}" d="{d}" fill="none" stroke="#f5c400" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>')
    for key, r, x, y in markers:
        w = 12 + 8 * len(r["number"])
        svg.append(f'<g id="marker-{key}"><rect x="{x - w / 2:.0f}" y="{y - 11:.0f}" width="{w}" height="22" rx="5" fill="#175cd3" stroke="#faf8f4" stroke-width="2"/>'
                   f'<text x="{x:.0f}" y="{y + 5:.0f}" font-family="Inter, Arial, sans-serif" font-size="13" font-weight="700" text-anchor="middle" fill="#faf8f4">{r["number"]}</text></g>')
    svg.append("</g>")

_ring = ROOT / "src" / "map" / "source" / "ring_details.json"
turnoffs, bridges = [], []
if _ring.exists():
    RD = json.loads(_ring.read_text(encoding="utf-8"))
    dist = lambda a, b: math.hypot((a["lng"] - b["lng"]) * KX, (a["lat"] - b["lat"]) * KY)
    for j in RD["junctions"]:  # one turnoff per interchange: same exit number or name nearby, or within 600 m
        refs = set(j["ref"].replace(";", ",").split(",")) - {""}
        for c in turnoffs:
            if dist(j, c[0]) < 0.6 or (dist(j, c[0]) < 2.5 and ((refs & c[1]) or (j["name"] and j["name"] in c[2]))):
                c[0].setdefault("_pts", [c[0]]).append(j); c[1].update(refs)
                if j["name"]: c[2].add(j["name"])
                break
        else:
            turnoffs.append([j, set(refs), {j["name"]} if j["name"] else set()])
    for b in RD["bridges"]:
        if not any(dist(b, c) < 0.35 for c in bridges):
            bridges.append(b)
    def exit_label(c):
        refs = sorted(c[1], key=lambda r: (len(r), r))
        names = sorted(c[2], key=lambda n: (n in ("Johannesburg", "Roodepoort", "Sandton", "Edenvale"), len(n)))  # a road name beats a destination
        return refs, names
    svg.append('<g id="ring-turnoffs">')
    ring_cx, ring_cy = proj(CBD["lng"], CBD["lat"])
    used = set()
    for c in turnoffs:
        pts = c[0].get("_pts", [c[0]])
        lat = sum(q["lat"] for q in pts) / len(pts); lng = sum(q["lng"] for q in pts) / len(pts)
        x, y = proj(lng, lat)
        refs, names = exit_label(c)
        slug = lambda s: "-".join("".join(ch if ch.isalnum() else " " for ch in s.lower()).split())
        tid = f'turnoff-{c[0]["road"]}-{refs[0].lower() if refs else (slug(names[0]) if names else "unnamed")}'
        if tid in used:  # same exit number twice (one interchange, two roads): add the road's name
            tid += "-" + (slug(names[0]) if names else str(len(used)))
        used.add(tid)
        full = (f"Exit {', '.join(refs)}" if refs else "Turnoff") + (f": {names[0]}" if names else "")
        ux, uy = x - ring_cx, y - ring_cy
        n = math.hypot(ux, uy) or 1
        lx, ly = x + ux / n * 1.1, y + uy / n * 1.1  # the exit number sits just outside the ring
        sx, sy = (x - ox) * UNIT, (y - oy) * UNIT
        svg.append(f'<g id="{tid}" data-name="{esc(full)}"><circle cx="{sx:.0f}" cy="{sy:.0f}" r="4" fill="#faf8f4" stroke="#1a1c20" stroke-width="2"/>'
                   + (f'<text x="{(lx - ox) * UNIT:.0f}" y="{(ly - oy) * UNIT + 3:.0f}" font-family="Inter, Arial, sans-serif" font-size="8" font-weight="700" text-anchor="middle" fill="#1a1c20">{esc(refs[0])}</text>' if refs else "")
                   + "</g>")
    svg.append("</g>")
    svg.append('<g id="ring-bridges">')
    for i, b in enumerate(bridges, 1):
        x, y = proj(b["lng"], b["lat"])
        sx, sy = (x - ox) * UNIT, (y - oy) * UNIT
        svg.append(f'<path id="bridge-{b["road"]}-{i}" d="M{sx:.0f},{sy - 3:.0f} L{sx + 3:.0f},{sy:.0f} L{sx:.0f},{sy + 3:.0f} L{sx - 3:.0f},{sy:.0f}Z" fill="#1a1c20"/>')
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
    size, weight = (11, 700) if p["major"] else (8, 400)
    svg.append(f'<text id="label-{p["id"]}" x="{(c.x - ox) * UNIT:.1f}" y="{(c.y - oy) * UNIT:.1f}" font-family="Inter, Arial, sans-serif" '
               f'font-size="{size}" font-weight="{weight}" text-anchor="middle" fill="#1a1c20">{esc(p["name"])}</text>')
svg.append("</g>")

# View frames: a dashed box per view in map.json, for checking what each view shows. The city view frames the ring road.
svg.append('<g id="views">')
for v in MAPCFG["views"]:
    if v["fit"] == "ring-road" and RING_BOX:
        b = RING_BOX
    elif v["fit"] == "all":
        b = unary_union(list(shapes.values())).bounds
    else:
        got = [shapes[a] for a in v["fit"] if a in shapes]
        if not got:
            continue
        b = unary_union(got).bounds
    m = 1.0  # km of margin
    x0, y0, x1, y1 = (b[0] - m - ox) * UNIT, (b[1] - m - oy) * UNIT, (b[2] + m - ox) * UNIT, (b[3] + m - oy) * UNIT
    svg.append(f'<g id="view-{v["id"]}"><rect x="{x0:.0f}" y="{y0:.0f}" width="{x1 - x0:.0f}" height="{y1 - y0:.0f}" fill="none" stroke="#6927da" stroke-width="2" stroke-dasharray="8 4"/>'
               f'<text x="{x0 + 4:.0f}" y="{y0 - 5:.0f}" font-family="Inter, Arial, sans-serif" font-size="11" font-weight="700" fill="#6927da">View: {esc(v["name"])}</text></g>')
svg.append("</g>")

# Places outside the map: an arrow on the edge pointing their way, with the distance from the city centre.
svg.append('<g id="outlying">')
cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
bx, by = proj(CBD["lng"], CBD["lat"])
placed = []
for p in places:
    if p["region"] != "outlying" or p["id"] not in hits:
        continue
    x, y = proj(hits[p["id"]]["lng"], hits[p["id"]]["lat"])
    dx, dy = x - cx, y - cy
    k = min((maxx - cx + PAD * 0.6) / abs(dx) if dx else 1e9, (maxy - cy + PAD * 0.6) / abs(dy) if dy else 1e9)
    ex, ey = cx + dx * k, cy + dy * k
    km = math.hypot(x - bx, y - by)
    ang = math.degrees(math.atan2(dy, dx))
    sx, sy = (ex - ox) * UNIT, (ey - oy) * UNIT
    down = dy >= 0 or sy < 60  # near the top edge, put the label below the arrow so it stays on the map
    ty = sy + 24 if down else sy - 16
    while any(abs(ty - py) < 16 and abs(sx - px) < 220 for px, py in placed):
        ty += 16 if down else -16
    placed.append((sx, ty))
    anchor = "end" if sx > W - 150 else "start" if sx < 150 else "middle"
    svg.append(f'<g id="{p["id"]}" data-name="{esc(p["name"])}"><path d="M-10,-7 L10,0 L-10,7 Z" transform="translate({sx:.0f},{sy:.0f}) rotate({ang:.0f})" fill="#5f646d"/>'
               f'<text x="{sx:.0f}" y="{ty:.0f}" font-family="Inter, Arial, sans-serif" font-size="12" text-anchor="{anchor}" fill="#1a1c20">{esc(p["name"])}, {km:.0f} km from the centre</text></g>')
svg.append("</g>")
svg.append(f'<g id="credit"><text x="{W - 12:.0f}" y="{H - 12:.0f}" font-family="Inter, Arial, sans-serif" font-size="12" text-anchor="end" fill="#5f646d">Base outlines © OpenStreetMap contributors</text></g>')
svg.append("</svg>")
OUT.write_text("\n".join(svg) + "\n", encoding="utf-8")
# The hexagons as data, for tools/make_hex_view.py and, later, the map page: centres in SVG units.
(ROOT / "src" / "map" / "hexes.json").write_text(json.dumps({
    "hex_radius": round(HEX_KM * UNIT, 2), "unit_per_km": UNIT, "width": round(W), "height": round(H),
    "projection": {"lat0": lat0, "lng0": lng0, "kx": KX, "ky": KY, "ox": ox, "oy": oy},
    "areas": {pid: [[round((x - ox) * UNIT, 1), round((y - oy) * UNIT, 1)] for x, y in cs] for pid, cs in hex_of.items()},
}, separators=(",", ":")) + "\n", encoding="utf-8")

# ---------------------------------------------------------------- audit
missing = [p for p in places if p["id"] not in hits]
lines = ["# Map draft audit", "", f"Draft of {'main areas only' if MAJOR else 'every area'}.", "", f"Drawn from src/map/source/nominatim.json by tools/make_map.py. 1 km = {UNIT} SVG units. The draft is {W / UNIT:.0f} by {H / UNIT:.0f} km.", "",
         f"- Areas with an OpenStreetMap outline: {sum(v == 'outline' for v in kinds.values())}",
         f"- Areas drawn as rough cells from a point: {sum(v == 'rough' for v in kinds.values())}",
         f"- Places not found: {len(missing)}",
         f"- Hexagons: {sum(len(v) for v in hex_of.values())}, {HEX_KM * math.sqrt(3):.1f} km across; fewest in one area: {min(len(v) for v in hex_of.values())}", ""]
if missing:
    lines += ["## Not found", "", "Add these by hand in Figma, or fix the name and fetch again.", ""]
    lines += [f"- {p['name']} ({p['kind']}, {regions[p['region']]['name']})" for p in missing] + [""]
if turnoffs:
    lines += ["## Ring road turnoffs", "", "Names as OpenStreetMap has them. Check these, and fill in any that are missing or only name a destination.", ""]
    for c in sorted(turnoffs, key=lambda c: (c[0]["road"], min((int("".join(ch for ch in r if ch.isdigit()) or 0) for r in c[1]), default=0))):
        refs, names = exit_label(c)
        lines.append(f"- {c[0]['road'].upper()}: " + (f"exit {', '.join(refs)}" if refs else "no exit number") + (f", {' / '.join(names)}" if names else ", no name"))
    lines += ["", f"Bridges on the ring road: {len(bridges)}.", ""]
if notes:
    lines += ["## Notes", ""] + [f"- {PLACES_NAME}: {n}" for PLACES_NAME, n in ((next(p['name'] for p in places if p['id'] == k), v) for k, v in notes.items())] + [""]
lines += ["## Check these matches", "", "The search may have found a place with the same name elsewhere. Each line is the place and what it matched.", ""]
lines += [f"- {p['name']}: {hits[p['id']]['display_name'][:110]}" for p in places if p["id"] in hits]
AUDIT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size // 1024} KB), {AUDIT.relative_to(ROOT)}")
print(f"outlines {sum(v == 'outline' for v in kinds.values())}, rough {sum(v == 'rough' for v in kinds.values())}, missing {len(missing)}")
