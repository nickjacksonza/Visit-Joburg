#!/usr/bin/env python3
"""Fetch the open data the draft map is drawn from, once, and keep it in the repo.

    python3 tools/fetch_map_sources.py            # only places not yet in the cache
    python3 tools/fetch_map_sources.py --refresh  # fetch every place again
    python3 tools/fetch_map_sources.py --retry    # look again for places not found, using addresses (see below)
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
    params = {**extra, "q": q, "format": "jsonv2", "polygon_geojson": 1, "polygon_threshold": 0.0002, "limit": 8, "countrycodes": "za"}
    if bounded:
        params.update({"viewbox": VIEWBOX, "bounded": 1})
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


def main():
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
