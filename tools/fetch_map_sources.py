#!/usr/bin/env python3
"""Fetch the open data the draft map is drawn from, once, and keep it in the repo.

    python3 tools/fetch_map_sources.py            # only places not yet in the cache
    python3 tools/fetch_map_sources.py --refresh  # fetch every place again
    python3 tools/fetch_map_sources.py --retry    # look again for places not found, using addresses (see below)
    python3 tools/fetch_map_sources.py --roads    # the ring road (N1 Western, N3 Eastern and N12 Southern Bypass) to src/map/source/roads.json
    python3 tools/fetch_map_sources.py --main-roads   # other freeways and the main roads to src/map/source/main_roads.json
    python3 tools/fetch_map_sources.py --ring     # the ring road's turnoffs and bridges to src/map/source/ring_details.json (run --roads first)
    python3 tools/fetch_map_sources.py --major    # only the main areas, the attractions in them, the places outside the city and the city boundary

Looks up every place in src/data/neighbourhoods.json with OpenStreetMap's Nominatim search, plus the City of
Johannesburg boundary, and saves the answers to src/map/source/nominatim.json. Nominatim allows at most one request a
second, so a full run takes about four minutes. tools/make_map.py then builds the draft SVG from this file
without the network.

The data is © OpenStreetMap contributors, under the Open Database License (ODbL). Keep the credit line on the map,
and keep this file open if it is published.
"""
import json, sys, time, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "map" / "source" / "nominatim.json"
API = "https://nominatim.openstreetmap.org/search"
AGENT = "visit-joburg-map-draft/0.1 (static site build tool)"
# Greater Johannesburg, west, north, east, south. Places in the city are looked up inside this box only.
VIEWBOX = "27.75,-25.90,28.30,-26.40"
AREA_CLASSES = {("place", t) for t in ("suburb", "neighbourhood", "quarter", "town", "village", "hamlet", "city_block", "locality", "city")} | {("boundary", "administrative")}
EXTRA = {"_city": ("City of Johannesburg Metropolitan Municipality", None)}


def search(q, bounded=True, **extra):
    params = {"q": q, "format": "jsonv2", "polygon_geojson": 1, "polygon_threshold": 0.0002, "limit": 8, "countrycodes": "za"}
    if bounded:
        params.update({"viewbox": VIEWBOX, "bounded": 1})
    params.update(extra)  # a road can narrow the box
    req = urllib.request.Request(f"{API}?{urllib.parse.urlencode(params)}", headers={"User-Agent": AGENT})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def pick(results, kind):
    """For an area, prefer a suburb-like place with an outline, then any suburb-like place. For an attraction, the first hit."""
    if kind == "area":
        areas = [r for r in results if (r["category"], r["type"]) in AREA_CLASSES]
        with_shape = [r for r in areas if r["geojson"]["type"] in ("Polygon", "MultiPolygon")]
        return (with_shape or areas or [None])[0]
    return results[0] if results else None


ADDRESS_KEYS = ("suburb", "quarter", "neighbourhood", "city_district", "town", "village", "hamlet")


def by_address(name, bounded):
    """Many suburbs are not mapped as places, only named in the addresses of things inside them. Take the middle point
    (median) of up to 20 such addresses as a rough centre, and mark it as approximate."""
    res = search(f"{name}, Johannesburg" if bounded else name, bounded, addressdetails=1, limit=20)
    pts = [(float(r["lat"]), float(r["lon"])) for r in res
           if any((r.get("address") or {}).get(k, "").lower() == name.lower() for k in ADDRESS_KEYS)]
    if not pts:
        return None
    lats, lngs = sorted(p[0] for p in pts), sorted(p[1] for p in pts)
    lat, lng = lats[len(lats) // 2], lngs[len(lngs) // 2]
    return {"found": True, "approx": True, "name": name, "display_name": f"median of {len(pts)} addresses in {name}", "osm": None,
            "class": "address", "type": "median", "lat": lat, "lng": lng, "geojson": {"type": "Point", "coordinates": [lng, lat]}}


def keep(r, q):
    if not r:
        return {"query": q, "found": False}
    return {"query": q, "found": True, "name": r.get("name"), "display_name": r["display_name"], "osm": f'{r["osm_type"]}/{r["osm_id"]}',
            "class": r["category"], "type": r["type"], "lat": float(r["lat"]), "lng": float(r["lon"]), "geojson": r["geojson"]}


RING = {"n1": ("N1", "Western Bypass"), "n3": ("N3", "Eastern Bypass"), "n12": ("N12", "Southern Bypass")}
# Other roads drawn on the map: (id, label on the map, name in OpenStreetMap, kind). Freeways are drawn thicker than main roads.
OTHER_ROADS = [
    ("ben-schoeman", "N1", "Ben Schoeman Highway", "freeway"),
    ("m1", "M1", "M1", "freeway"),
    ("m2", "M2", "M2", "freeway"),
    ("r21", "R21", "R21", "freeway"),
    ("winnie-mandela", "Winnie Mandela Dr", "Winnie Mandela Drive", "main"),
    ("jan-smuts", "Jan Smuts Ave", "Jan Smuts Avenue", "main"),
    ("bram-fischer", "Bram Fischer Dr", "Bram Fischer Drive", "main"),
    ("louis-botha", "Louis Botha Ave", "Louis Botha Avenue", "main"),
    ("ontdekkers", "Ontdekkers Rd", "Ontdekkers Road", "main"),
    ("malibongwe", "Malibongwe Dr", "Malibongwe Drive", "main"),
    ("rivonia", "Rivonia Rd", "Rivonia Road", "main"),
    ("beyers-naude", "Beyers Naudé Dr", "Beyers Naudé Drive", "main"),
    ("oxford", "Oxford Rd", "Oxford Road", "main"),
    ("empire", "Empire Rd", "Empire Road", "main"),
    ("main-reef", "Main Reef Rd", "Main Reef Road", "main"),
    ("witkoppen", "Witkoppen Rd", "Witkoppen Road", "main"),
    ("katherine", "Katherine St", "Katherine Street", "main"),
    ("hendrik-potgieter", "Hendrik Potgieter Rd", "Hendrik Potgieter Road", "main"),
    ("marlboro", "Marlboro Dr", "Marlboro Drive", "main"),
    ("linksfield", "Linksfield Rd", "Linksfield Road", "main"),
    ("chris-hani", "Chris Hani Rd", "Chris Hani Road", "main"),
    ("joe-slovo", "Joe Slovo Dr", "Joe Slovo Drive", "main"),
    # Streets: thinner, for the Central and Soweto views. A common name is searched only inside its own box
    # (west, south, east, north), so a Main Street elsewhere is not picked up.
    ("commissioner", "Commissioner St", "Commissioner Street", "street", "27.95,-26.23,28.12,-26.18"),
    ("main-street", "Main St", "Main Street", "street", "28.02,-26.215,28.07,-26.195"),
    ("kerk", "Kerk St", "Kerk Street", "street", "28.02,-26.215,28.07,-26.19"),
    ("albertina-sisulu", "Albertina Sisulu Rd", "Albertina Sisulu Road", "street", "27.95,-26.23,28.12,-26.18"),
    ("smit", "Smit St", "Smit Street", "street", "28.01,-26.20,28.07,-26.18"),
    ("vilakazi", "Vilakazi St", "Vilakazi Street", "street", "27.88,-26.25,27.93,-26.225"),
]
MAIN_TYPES = {"motorway", "trunk", "primary", "secondary", "tertiary", "motorway_link", "trunk_link", "primary_link"}


def fetch_named(name, types, max_pages=25, box=None):
    """Every road segment with this exact name (or ref), paging past Nominatim's 50-result limit. A short name such as
    R21 also matches many unrelated places, so paging stops after max_pages."""
    seen, lines, ids = [], [], []
    for _ in range(max_pages):
        extra = {"exclude_place_ids": ",".join(seen)} if seen else {}
        if box:
            extra["viewbox"] = box
        res = search(name, True, limit=50, extratags=1, **extra)
        new = [r for r in res if str(r["place_id"]) not in seen]
        if not new:
            break
        for r in new:
            seen.append(str(r["place_id"]))
            ref = ((r.get("extratags") or {}).get("ref") or "").split(";")
            if r["category"] == "highway" and r["type"] in types and r["geojson"]["type"] in ("LineString", "MultiLineString") and (r.get("name") == name or name in ref):
                lines.append(r["geojson"])
                if r["osm_type"] == "way":
                    ids.append(r["osm_id"])
        time.sleep(1.1)
    return lines, ids


def fetch_other_roads():
    """Saves after each road and skips roads already in the file, so a stopped run picks up where it left off."""
    path = OUT.parent / "main_roads.json"
    out = json.loads(path.read_text(encoding="utf-8")) if path.exists() and "--refresh" not in sys.argv else {}
    for key, label, name, kind, *box in OTHER_ROADS:
        if key in out:
            continue
        types = {"motorway", "trunk"} if kind == "freeway" else MAIN_TYPES | ({"residential", "unclassified", "living_street", "pedestrian"} if kind == "street" else set())
        lines, ids = fetch_named(name, types, box=box[0] if box else None)
        out[key] = {"label": label, "name": name, "kind": kind, "ways": ids, "segments": lines}
        path.write_text(json.dumps(out, separators=(",", ":")) + "\n", encoding="utf-8")
        print(f"  {label} ({name}): {len(lines)} segments", flush=True)
    print(f"wrote {path.relative_to(ROOT)}")


def fetch_roads():
    """Every motorway segment named after each bypass, paging past Nominatim's 50-result limit."""
    out = {}
    for key, (number, name) in RING.items():
        seen, lines, ids = [], [], []
        while True:
            extra = {"exclude_place_ids": ",".join(seen)} if seen else {}
            res = search(name, True, limit=50, **extra)
            new = [r for r in res if str(r["place_id"]) not in seen]
            if not new:
                break
            for r in new:
                seen.append(str(r["place_id"]))
                if r["category"] == "highway" and r["geojson"]["type"] in ("LineString", "MultiLineString") and r.get("name") == name:
                    lines.append(r["geojson"])
                    if r["osm_type"] == "way":
                        ids.append(r["osm_id"])
            time.sleep(1.1)
        out[key] = {"number": number, "name": name, "ways": ids, "segments": lines}
        print(f"  {number} {name}: {len(lines)} segments")
    path = OUT.parent / "roads.json"
    path.write_text(json.dumps(out, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)}")


OSM_API = "https://api.openstreetmap.org/api/0.6"


def osm_get(kind, ids):
    """Fetch OSM elements in batches from the main API (ways or nodes), politely, one request a second."""
    out = []
    step = 100 if kind == "ways" else 250
    for i in range(0, len(ids), step):
        url = f"{OSM_API}/{kind}.json?{kind}={','.join(map(str, ids[i:i + step]))}"
        req = urllib.request.Request(url, headers={"User-Agent": AGENT})
        with urllib.request.urlopen(req, timeout=90) as r:
            out += json.load(r)["elements"]
        time.sleep(1.0)
    return out


def fetch_ring():
    """Turnoffs (motorway junction points, with the road's name and exit number) and bridges on the ring road."""
    roads = json.loads((OUT.parent / "roads.json").read_text(encoding="utf-8"))
    way_road = {w: k for k, r in roads.items() for w in r["ways"]}
    ways = osm_get("ways", sorted(way_road))
    node_ids = sorted({n for w in ways for n in w.get("nodes", [])})
    print(f"  {len(ways)} ways, {len(node_ids)} points")
    nodes = {n["id"]: n for n in osm_get("nodes", node_ids)}
    road_of_node = {}
    for w in ways:
        for n in w.get("nodes", []):
            road_of_node.setdefault(n, way_road[w["id"]])
    junctions = [{"road": road_of_node[n["id"]], "name": n["tags"].get("name") or n["tags"].get("exit_to") or "", "ref": n["tags"].get("ref", ""),
                  "lat": n["lat"], "lng": n["lon"], "osm": f'node/{n["id"]}'}
                 for n in nodes.values() if n.get("tags", {}).get("highway") == "motorway_junction"]
    bridges = []
    for w in ways:
        tags = w.get("tags", {})
        if tags.get("bridge") in (None, "no"):
            continue
        pts = [nodes[n] for n in w.get("nodes", []) if n in nodes]
        if not pts:
            continue
        mid = pts[len(pts) // 2]
        bridges.append({"road": way_road[w["id"]], "name": tags.get("bridge:name") or tags.get("name", ""), "kind": tags.get("bridge"),
                        "lat": mid["lat"], "lng": mid["lon"], "osm": f'way/{w["id"]}'})
    path = OUT.parent / "ring_details.json"
    path.write_text(json.dumps({"junctions": junctions, "bridges": bridges}, indent=0, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)}: {len(junctions)} junction points, {len(bridges)} bridge segments")


def main():
    if "--roads" in sys.argv:
        return fetch_roads()
    if "--main-roads" in sys.argv:
        return fetch_other_roads()
    if "--ring" in sys.argv:
        return fetch_ring()
    data = json.loads((ROOT / "src" / "data" / "neighbourhoods.json").read_text(encoding="utf-8"))
    cache = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() and "--refresh" not in sys.argv else {}
    jobs = [(pid, q, None) for pid, (q, _) in EXTRA.items()]
    majors = {p["id"] for p in data["places"] if p["major"]}
    for p in data["places"]:
        if "--major" in sys.argv and not (p["major"] or p["parent"] in majors or p["region"] == "outlying"):
            continue
        outside = p["region"] == "outlying"
        q = p["name"] if outside or p["kind"] == "attraction" else f'{p["name"]}, Johannesburg'
        jobs.append((p["id"], q, p))
    retry = "--retry" in sys.argv
    todo = [j for j in jobs if j[0] not in cache or (retry and not cache[j[0]].get("found"))]
    print(f"{len(todo)} to fetch, {len(jobs) - len(todo)} cached")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    for n, (pid, q, p) in enumerate(todo, 1):
        kind = p["kind"] if p else "area"
        bounded = not (p and p["region"] == "outlying") and pid != "_city"
        try:
            res = search(q, bounded)
            if not pick(res, kind) and p and p["kind"] == "area":  # some suburbs sit just outside the city's name
                time.sleep(1.1)
                q = f'{p["name"]}, Gauteng'
                res = search(q, bounded)
            cache[pid] = keep(pick(res, kind), q)
            if retry and not cache[pid]["found"] and p:
                time.sleep(1.1)
                cache[pid] = by_address(p["name"], bounded) or cache[pid]
        except Exception as e:  # keep going; a failed place is fetched again on the next run
            print(f"  {pid}: {e}")
        if n % 20 == 0:
            OUT.write_text(json.dumps(cache, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"  {n}/{len(todo)}")
        time.sleep(1.1)
    OUT.write_text(json.dumps(cache, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    found = [k for k, v in cache.items() if v.get("found")]
    print(f"approximate (from addresses): {sum(1 for v in cache.values() if v.get('approx'))}")
    shaped = [k for k in found if cache[k]["geojson"]["type"] in ("Polygon", "MultiPolygon")]
    print(f"done: {len(found)} found, {len(shaped)} with an outline, {len(cache) - len(found)} not found")


if __name__ == "__main__":
    main()
