#!/usr/bin/env python3
"""Static site generator for Visit Joburg. Standard library only.

    python3 build.py            # src/ -> docs/
    python3 tools/check.py      # post-build checks
    cd docs && python3 -m http.server 3057

Pages are src/pages/**.html (front matter + body). Placeholders {{ like_this }}
resolve from src/data/site.json, the front matter and the HTML fragments built
below. Visible lists (attractions, neighbourhoods, FAQs, events) and their JSON-LD
come from the same data. Events live in content/events.json, which the editor at /editor/ writes, so the two cannot drift apart.
"""
import base64, datetime, hashlib, html, json, re, shutil, subprocess, sys, urllib.parse
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "tools"))
from html2md import main_to_markdown  # noqa: E402
from minify import minify_css, minify_js  # noqa: E402

SRC, OUT = ROOT / "src", ROOT / "docs"
site = json.loads((SRC / "data" / "site.json").read_text(encoding="utf-8"))
D = site["domain"]
ORG, WEB, DEST = f"{D}/#org", f"{D}/#website", f"{D}/#destination"
LANG = site.get("lang", "en")
CITY = site["city"]
esc = html.escape
VERSIONS = {}
# ---------------------------------------------------------------- editable events
EVENTS_FILE = ROOT / "content" / "events.json"
LIMITS = {"name": 80, "description": 300, "place": 60, "street": 80, "url": 200}
BAD_CHARS = re.compile(r"[<>\x00-\x1f\x7f]")
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}$")
WHEN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$")


def load_events():
    """Read and validate content/events.json. Same rules as editor/editor-lib.js.
    A bad edit made in the editor or on GitHub fails the build, so nothing broken goes live."""
    data = json.loads(EVENTS_FILE.read_text(encoding="utf-8"))
    if not isinstance(data.get("timezone"), str) or not re.fullmatch(r"[+-](0\d|1[0-4]):[0-5]\d", data["timezone"]):
        raise SystemExit("events.json: timezone must be an offset like +02:00")
    if len(data["events"]) > 200:
        raise SystemExit("events.json: more than 200 events")
    seen = set()
    for e in data["events"]:
        where = f"events.json: {e.get('name') or e.get('id')}"
        for k, lim in LIMITS.items():
            v = e.get(k)
            if not isinstance(v, str) or not v.strip() or len(v) > lim or BAD_CHARS.search(v):
                raise SystemExit(f"{where}: bad {k}")
        if not e["url"].startswith("https://"):
            raise SystemExit(f"{where}: link must start with https://")
        for k in ("start", "end"):
            if not isinstance(e.get(k), str) or not WHEN.match(e[k]):
                raise SystemExit(f"{where}: {k} must look like 2026-12-05T09:00")
            datetime.datetime.fromisoformat(e[k])  # raises on a date that does not exist
        if e["end"] <= e["start"]:
            raise SystemExit(f"{where}: end must be after start")
        p = e.get("price")
        if isinstance(p, bool) or not isinstance(p, (int, float)) or not 0 <= p <= 100000 or abs(round(p * 100) - p * 100) > 1e-9:
            raise SystemExit(f"{where}: price must be 0 to 100000 with at most two decimals")
        if not isinstance(e.get("published"), bool):
            raise SystemExit(f"{where}: published must be true or false")
        if not SLUG.match(e.get("id", "")) or e["id"] in seen:
            raise SystemExit(f"{where}: missing or duplicate id")
        seen.add(e["id"])
        e["start_iso"], e["end_iso"] = e["start"] + ":00" + data["timezone"], e["end"] + ":00" + data["timezone"]
    return data


EVENTS = load_events()


# ---------------------------------------------------------------- neighbourhoods and the places in them
PLACES_FILE = SRC / "data" / "neighbourhoods.json"
ATTRACTIONS_FILE = SRC / "data" / "attractions.json"


def check_geo(where, x):
    """A position is a centre near Johannesburg plus where it came from, or null and null until the place is mapped."""
    g, src = x.get("geo"), x.get("geo_source")
    if g is None:
        if src is not None:
            raise SystemExit(f"{where}: geo_source must be null while geo is null")
        return
    if not (isinstance(g, dict) and set(g) == {"lat", "lng"} and -27 < g["lat"] < -25 and 27 < g["lng"] < 29):
        raise SystemExit(f"{where}: geo must be null or {{\"lat\": -26.2, \"lng\": 28.0}} near Johannesburg")
    if not isinstance(src, str) or not src.strip() or len(src) > 160 or BAD_CHARS.search(src):
        raise SystemExit(f"{where}: say where the position came from in geo_source (for example \"OpenStreetMap\")")


def check_text(where, x, fields):
    for k, lim in fields:
        if not isinstance(x.get(k, ""), str) or len(x.get(k, "")) > lim or BAD_CHARS.search(x.get(k, "")):
            raise SystemExit(f"{where}: {k} is too long or has < > or control characters")


def load_places():
    """Read and check src/data/neighbourhoods.json: the tag list, the parts of the city and every area the guide plans
    to cover. A bad entry fails the build. Areas start as a name only; fill in tags, geo and summary as each is written up."""
    data = json.loads(PLACES_FILE.read_text(encoding="utf-8"))
    tags, regions = data["tags"], {r["id"]: r for r in data["regions"]}
    places = {}
    for p in data["places"]:
        where = f"neighbourhoods.json: {p.get('name') or p.get('id')}"
        if not isinstance(p.get("id"), str) or not SLUG.match(p["id"]) or p["id"] in places:
            raise SystemExit(f"{where}: missing or duplicate id")
        if not isinstance(p.get("name"), str) or not p["name"].strip() or BAD_CHARS.search(p["name"]):
            raise SystemExit(f"{where}: bad name")
        if p.get("region") not in regions:
            raise SystemExit(f"{where}: unknown region {p.get('region')!r}")
        if not isinstance(p.get("major"), bool):
            raise SystemExit(f"{where}: major (a main area) must be true or false")
        if p.get("map", True) is not True and p.get("map") is not False:
            raise SystemExit(f"{where}: map is false for a place not drawn as itself (such as Soweto, drawn as its townships); leave it out otherwise")
        bad = [x for x in p["tags"] if x not in tags]
        if bad:
            raise SystemExit(f"{where}: unknown tags {bad}. Add them to the tags list at the top of the file first.")
        check_geo(where, p)
        check_text(where, p, (("summary", 300), ("good_for", 120), ("notes", 300)))
        places[p["id"]] = p
    for page in (SRC / "pages" / "neighbourhoods").glob("*.html"):
        if page.stem not in places or not places[page.stem]["summary"]:
            raise SystemExit(f"{page.relative_to(ROOT)}: add {page.stem!r} to neighbourhoods.json with a summary first")
    return tags, regions, places


TYPES = ("TouristAttraction", "Museum", "Park", "LandmarksOrHistoricalBuildings", "Zoo", "StadiumOrArena", "ShoppingCenter")


def load_attractions():
    """Read and check src/data/attractions.json: every attraction once. Each sits in an area (or, outside the city, has
    a direction). Featured ones get a card and schema on the things-to-do page, so they need a street, type and image."""
    data = json.loads(ATTRACTIONS_FILE.read_text(encoding="utf-8"))
    out, seen = [], set()
    for a in data["attractions"]:
        where = f"attractions.json: {a.get('name') or a.get('id')}"
        if not isinstance(a.get("id"), str) or not SLUG.match(a["id"]) or a["id"] in seen or a["id"] in PLACES:
            raise SystemExit(f"{where}: missing or duplicate id (ids must differ from area ids too)")
        seen.add(a["id"])
        if not isinstance(a.get("name"), str) or not a["name"].strip() or BAD_CHARS.search(a["name"]):
            raise SystemExit(f"{where}: bad name")
        if a.get("area") is not None and a["area"] not in PLACES:
            raise SystemExit(f"{where}: area {a['area']!r} is not an area in neighbourhoods.json")
        if a.get("region") not in REGIONS or (a.get("area") and PLACES[a["area"]]["region"] != a["region"]):
            raise SystemExit(f"{where}: region must be a part of the city, the same as its area's")
        bad = [x for x in a.get("tags", []) if x not in TAGS]
        if bad:
            raise SystemExit(f"{where}: unknown tags {bad}. Add them to the tags list in neighbourhoods.json first.")
        check_geo(where, a)
        check_text(where, a, (("summary", 300), ("notes", 300), ("label", 80), ("street", 80)))
        if a.get("featured"):
            if not all(a.get(k) for k in ("geo", "summary", "label", "street", "type", "img")) or a["type"] not in TYPES or a["img"] not in IMAGES:
                raise SystemExit(f"{where}: a featured attraction needs geo, summary, label, street, img (in images.json) and a type from {TYPES}")
        out.append(a)
    return out


TAGS, REGIONS, PLACES = load_places()
AREAS_FILE = ROOT / "content" / "area-lists.json"


def load_areas():
    """Read and check content/area-lists.json, the area lists the owner edits at /editor/area-lists.html: popular names for
    clusters of suburbs (The Parks, Town), each with a colour and where it shows. Same rules as editor/area-lists-lib.js."""
    data = json.loads(AREAS_FILE.read_text(encoding="utf-8"))
    colours, seen = data.get("colours"), set()
    if not isinstance(colours, list) or not colours or not all(isinstance(c, str) and SLUG.match(c) for c in colours):
        raise SystemExit("content/area-lists.json: the colours list is broken")
    if not isinstance(data.get("lists"), list) or len(data["lists"]) > 40:
        raise SystemExit("content/area-lists.json: needs a lists list of at most 40 lists")
    for l in data["lists"]:
        where = f"content/area-lists.json: {l.get('name') or l.get('id')}"
        if not isinstance(l.get("id"), str) or not SLUG.match(l["id"]) or l["id"] in seen:
            raise SystemExit(f"{where}: missing or duplicate id")
        seen.add(l["id"])
        if not isinstance(l.get("name"), str) or not l["name"].strip() or len(l["name"]) > 40 or BAD_CHARS.search(l["name"]):
            raise SystemExit(f"{where}: bad name")
        if not isinstance(l.get("aka"), list) or len(l["aka"]) > 5 or any(not isinstance(a, str) or len(a) > 40 or BAD_CHARS.search(a) for a in l["aka"]):
            raise SystemExit(f"{where}: bad 'also called' names")
        if l.get("colour") not in colours:
            raise SystemExit(f"{where}: colour must be one of {colours}")
        if not isinstance(l.get("picker"), bool) or not isinstance(l.get("panel"), bool):
            raise SystemExit(f"{where}: picker and panel must be true or false")
        bad = [a for a in l.get("areas", []) if a not in PLACES]
        if bad or not l.get("areas") or len(l["areas"]) > 80:
            raise SystemExit(f"{where}: areas must be 1 to 80 area ids from neighbourhoods.json; not found: {bad}")
    return data


AREAS = load_areas()
IMAGES = {i["name"]: i for i in json.loads((SRC / "data" / "images.json").read_text(encoding="utf-8"))}
ATTRACTIONS = load_attractions()
FEATURED = [a for a in ATTRACTIONS if a.get("featured")]  # the things-to-do page: a card and schema each


def img(name, root, eager=False, cls=""):
    """<img> with width, height, alt, srcset and sizes from src/data/images.json. Only the hero is eager."""
    i = IMAGES[name]
    base = f'images/{i["dir"] + "/" if i["dir"] else ""}{name}'
    full = f'{root}{base}.webp {i["w"]}w'
    ss = ", ".join([f'{root}{base}-{w}w.webp {w}w' for w in i["widths"] if w < i["w"]] + [full])
    load = 'fetchpriority="high" decoding="async"' if eager else 'loading="lazy" decoding="async"'
    c = f' class="{cls}"' if cls else ""
    tag = f'<img{c} src="{root}{base}.webp" srcset="{ss}" sizes="{i["sizes"]}" width="{i["w"]}" height="{i["h"]}" alt="{esc(i["alt"])}" {load}>'
    if not (ROOT / f"{base}.avif").exists():
        return tag
    avif = ", ".join(f'{root}{base}-{w}w.avif {w}w' for w in i["widths"] if w < i["w"]) + f', {root}{base}.avif {i["w"]}w'
    return f'<picture><source type="image/avif" srcset="{avif}" sizes="{i["sizes"]}">{tag}</picture>'


def img_url(name):
    i = IMAGES[name]
    return f'{D}/images/{i["dir"] + "/" if i["dir"] else ""}{name}.webp'


# ---------------------------------------------------------------- helpers
def rands(v):
    return "Free" if float(v) == 0 else f"R{v:,.2f}".replace(".00", "").replace(",", " ")


def parse_page(path):
    text = path.read_text(encoding="utf-8")
    meta, body = {}, text
    if text.startswith("---"):
        _, fm, body = text.split("---", 2)
        for line in fm.strip().splitlines():
            k, _, v = line.partition(":")
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            meta[k.strip()] = v
    return meta, body.lstrip("\n")


def page_modified(path):
    """Today if the source has uncommitted edits, else its last commit date."""
    rel = str(path.relative_to(ROOT))
    try:
        run = lambda *a: subprocess.run(a, cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
        if run("git", "status", "--porcelain", "--", rel):
            return datetime.date.today().isoformat()
        day = run("git", "log", "-1", "--format=%cs", "--", rel)
        if day:
            return day
    except (OSError, subprocess.CalledProcessError):
        pass
    return datetime.date.fromtimestamp(path.stat().st_mtime).isoformat()


def maps_url(name, lat, lng):
    return f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"


def addr(street, locality=None):
    return {"@type": "PostalAddress", "streetAddress": street, "addressLocality": locality or CITY["name"],
            "addressRegion": CITY["region"], "addressCountry": CITY["country"]}


def geo(x):
    return {"@type": "GeoCoordinates", "latitude": x["lat"], "longitude": x["lng"]}


# ---------------------------------------------------------------- visible fragments (shared with JSON-LD)
def faq_html():
    return "\n".join(f'<details class="faq"><summary>{esc(f["q"])}</summary><p>{esc(f["a"])}</p></details>' for f in site["faqs"])


def attractions_html(root=""):
    out = []
    for a in FEATURED:
        tags = "".join(f"<li>{esc(TAGS[t])}</li>" for t in a["tags"]) + ("<li>Free</li>" if a.get("free") else "")
        out.append(f'<article class="card" id="{a["id"]}">{img(a["img"], root)}<h3>{esc(a["name"])}</h3>'
                   f'<p class="muted">{esc(a["label"])}</p><p>{esc(a["summary"])}</p><ul class="tag-list">{tags}</ul>'
                   f'<p><a href="{maps_url(a["name"], a["geo"]["lat"], a["geo"]["lng"])}">Open in Maps<span class="visually-hidden">: {esc(a["name"])}</span></a></p></article>')
    return "\n".join(out)


def has_page(p):
    return (SRC / "pages" / "neighbourhoods" / f"{p['id']}.html").exists()


def featured_areas():
    """Areas with a summary, in file order: the ones written up so far."""
    return [p for p in PLACES.values() if p["summary"]]


def places_here(area):
    """The attractions in an area, in attractions.json order."""
    return [a for a in ATTRACTIONS if a["area"] == area["id"]]


def place_link(x, root):
    """Where an attraction in an info box links to: its card on the things-to-do page, if it has one."""
    return f"{root}things-to-do.html#{x['id']}" if x.get("featured") else ""


def info_box(pid, root, level=2):
    """A short fact box about one area, built from neighbourhoods.json. Use {{ info_box }} on an area's own page,
    or {{ info_box_<id> }} (heading level 3) inside a section of any other page."""
    p = PLACES[pid]
    h = f"h{level}"
    rows = [("Part of the city", REGIONS[p["region"]]["name"])]
    if p["tags"]:
        rows.append(("Good for", ", ".join(TAGS[x] for x in p["tags"])))
    items = []
    for x in places_here(p):
        href = place_link(x, root)
        name = esc(x["name"])
        items.append(f'<li><a href="{href}">{name}</a></li>' if href else f"<li>{name}</li>")
    dl = "".join(f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>" for k, v in rows)
    if items:
        dl += f'<dt>Places here</dt><dd><ul>{"".join(items)}</ul></dd>'
    links = []
    if has_page(p) and level != 2:  # level 2 is the box on the area's own page, which needs no link to itself
        links.append(f'<a href="{root}neighbourhoods/{pid}.html">Read the {esc(p["name"])} guide</a>')
    if p["geo"]:
        links.append(f'<a href="{maps_url(p["name"], p["geo"]["lat"], p["geo"]["lng"])}">Open in Maps<span class="visually-hidden">: {esc(p["name"])}</span></a>')
    foot = f'<p>{" &middot; ".join(links)}</p>' if links else ""
    return (f'<aside class="info-box" aria-labelledby="ib-{pid}"><{h} id="ib-{pid}">{esc(p["name"])} at a Glance</{h}>'
            f'<p>{esc(p["summary"])}</p><dl>{dl}</dl>{foot}</aside>')


def neighbourhoods_html(root=""):
    out = []
    for n in featured_areas():
        links = []
        if has_page(n):
            links.append(f'<a href="{root}neighbourhoods/{n["id"]}.html">Read the {esc(n["name"])} guide</a>')
        if n["geo"]:
            links.append(f'<a href="{maps_url(n["name"], n["geo"]["lat"], n["geo"]["lng"])}">Open in Maps<span class="visually-hidden">: {esc(n["name"])}</span></a>')
        good = f'<p class="muted">Good for: {esc(n["good_for"])}</p>' if n.get("good_for") else ""
        out.append(f'<section class="card" id="{n["id"]}"><h3>{esc(n["name"])}</h3><p>{esc(n["summary"])}</p>{good}'
                   f'<p>{" &middot; ".join(links)}</p></section>')
    return "\n".join(out)


def directory_html(root=""):
    """Every area in neighbourhoods.json, grouped by part of the city. Main areas are in bold. Works without script."""
    out = []
    for r in REGIONS.values():
        areas = [p for p in PLACES.values() if p["region"] == r["id"]]
        if not areas:
            continue
        lis = []
        for p in sorted(areas, key=lambda p: p["name"]):
            name = esc(p["name"])
            name = f'<a href="{root}neighbourhoods/{p["id"]}.html">{name}</a>' if has_page(p) else name
            lis.append(f"<li><strong>{name}</strong></li>" if p["major"] else f"<li>{name}</li>")
        out.append(f'<details class="faq"><summary>{esc(r["name"])} ({len(areas)} area{"" if len(areas) == 1 else "s"})</summary><ul class="area-list">{"".join(lis)}</ul></details>')
    return "\n".join(out)


def area_lists_html(root=""):
    """The owner's area lists (content/area-lists.json) that show on the map, as foldable lists of their suburbs."""
    out = []
    for l in AREAS["lists"]:
        if not (l["picker"] or l["panel"]):
            continue
        lis = []
        for a in l["areas"]:
            p = PLACES[a]
            name = esc(p["name"])
            lis.append(f'<li><a href="{root}neighbourhoods/{a}.html">{name}</a></li>' if has_page(p) else f"<li>{name}</li>")
        aka = f'<p>Also called {esc(", ".join(l["aka"]))}.</p>' if l["aka"] else ""
        out.append(f'<details class="faq"><summary>{esc(l["name"])} ({len(lis)} area{"" if len(lis) == 1 else "s"})</summary>{aka}<ul class="area-list">{"".join(lis)}</ul></details>')
    return "\n".join(out)


def posts_html(root=""):
    return "\n".join(f'<article class="card"><h3><a href="{root}blog/{p["slug"]}.html">{esc(p["title"])}</a></h3><p class="muted"><time datetime="{p["date"]}">{fmt_date(p["date"])}</time></p><p>{esc(p["description"])}</p></article>' for p in site["posts"])


def fmt_date(d):
    return datetime.date.fromisoformat(d).strftime("%-d %B %Y")


def upcoming_events():
    """Events whose end time is still ahead, soonest first. Rebuild (the workflow also runs weekly) to drop finished ones."""
    now = datetime.datetime.now(datetime.timezone.utc)
    return sorted((e for e in EVENTS["events"] if e["published"] and datetime.datetime.fromisoformat(e["end_iso"]) > now), key=lambda e: e["start"])


def fmt_when(e):
    s, t = datetime.datetime.fromisoformat(e["start"]), datetime.datetime.fromisoformat(e["end"])
    if s.date() != t.date():
        return f'{s.strftime("%A %-d %B %Y, %H:%M")} to {t.strftime("%A %-d %B %Y, %H:%M")}'
    return f'{s.strftime("%A %-d %B %Y")}, {s.strftime("%H:%M")} to {t.strftime("%H:%M")}'


def events_html():
    out = [f'<article class="card" id="{e["id"]}"><h3>{esc(e["name"])}</h3><p><time datetime="{e["start_iso"]}">{fmt_when(e)}</time></p>'
           f'<p class="muted">{esc(e["street"])}, {esc(e["place"])} &middot; {rands(e["price"])}</p><p>{esc(e["description"])}</p>'
           f'<p><a href="{esc(e["url"])}">Event details<span class="visually-hidden">: {esc(e["name"])}</span></a></p></article>' for e in upcoming_events()]
    return "\n".join(out) if out else "<p>No events are listed right now. Check back soon.</p>"


# ---------------------------------------------------------------- JSON-LD
def org_node(full=False):
    n = {"@type": "Organization", "@id": ORG, "name": site["name"], "url": f"{D}/",
         "logo": {"@type": "ImageObject", "url": f"{D}/images/logo.svg", "width": 112, "height": 112},
         "image": f"{D}/images/og-default.png", "description": site["description"], "email": site["email"],
         "telephone": site["phone_e164"], "sameAs": list(site["social"].values())}
    if full:
        n.update({"foundingDate": site["founded"], "slogan": site["tagline"], "areaServed": {"@id": DEST},
                  "knowsAbout": ["Johannesburg", "Travel in South Africa", "Gauteng"],
                  "contactPoint": {"@type": "ContactPoint", "contactType": "customer service", "email": site["email"],
                                   "telephone": site["phone_e164"], "availableLanguage": ["English"]}})
    return n


def attraction_id(a):
    return f"{D}/things-to-do.html#{a['id']}"


def destination_node(full=False):
    n = {"@type": "TouristDestination", "@id": DEST, "name": CITY["name"], "alternateName": CITY["alternate_names"],
         "geo": geo(CITY), "sameAs": CITY["wikipedia"],
         "containedInPlace": {"@type": "AdministrativeArea", "name": f'{CITY["region"]}, South Africa'}}
    if full:
        n["includesAttraction"] = [{"@id": attraction_id(a)} for a in FEATURED]
    return n


def attraction_node(a):
    t = "TouristAttraction" if a["type"] == "TouristAttraction" else ["TouristAttraction", a["type"]]
    n = {"@type": t, "@id": attraction_id(a), "name": a["name"], "description": a["summary"], "url": attraction_id(a),
         "address": addr(a["street"], a.get("locality")), "geo": geo(a["geo"]), "hasMap": maps_url(a["name"], a["geo"]["lat"], a["geo"]["lng"]),
         "image": img_url(a["img"]), "containedInPlace": {"@id": DEST}}
    if a.get("free"):
        n["isAccessibleForFree"] = True
    return n


def place_id(p):
    """One @id per area: its own page if it has one, else its card on the neighbourhoods page."""
    return f"{D}/neighbourhoods/{p['id']}.html#place" if has_page(p) else f"{D}/neighbourhoods.html#{p['id']}"


def neighbourhood_node(p, full=False):
    n = {"@type": "Place", "@id": place_id(p), "name": p["name"], "description": p["summary"], "containedInPlace": {"@id": DEST}}
    if p.get("aka"):
        n["alternateName"] = p["aka"]
    if p["geo"]:
        n["geo"] = geo(p["geo"])
        n["hasMap"] = maps_url(p["name"], p["geo"]["lat"], p["geo"]["lng"])
    if p["tags"]:
        n["keywords"] = [TAGS[x] for x in p["tags"]]
    if full:
        here = []
        for x in places_here(p):
            if x.get("featured"):  # described on the things-to-do page
                here.append({"@id": attraction_id(x)})
            else:
                here.append({"@type": "Place", "name": x["name"], **({"description": x["summary"]} if x["summary"] else {})})
        if here:
            n["containsPlace"] = here
    return n


def faq_node(url):
    return {"@type": "FAQPage", "@id": f"{url}#faq", "url": url, "isPartOf": {"@id": f"{url}#webpage"},
            "mainEntity": [{"@type": "Question", "name": f["q"], "acceptedAnswer": {"@type": "Answer", "text": f["a"]}} for f in site["faqs"]]}


def event_node(e, url):
    return {"@type": "Event", "@id": f"{url}#{e['id']}", "name": e["name"], "description": e["description"], "startDate": e["start_iso"], "endDate": e["end_iso"],
            "eventStatus": "https://schema.org/EventScheduled", "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
            "image": [f"{D}/images/og-default.png"], "url": e["url"],
            "location": {"@type": "Place", "name": e["place"], "address": addr(e["street"]), "containedInPlace": {"@id": DEST}},
            "offers": {"@type": "Offer", "price": f'{e["price"]:.2f}', "priceCurrency": EVENTS["currency"], "availability": "https://schema.org/InStock", "url": e["url"]}}


def graph(page):
    url, kind = page["canonical"], page.get("kind", "page")
    wp_type = {"about": "AboutPage", "contact": "ContactPage", "blog": "CollectionPage", "events": "CollectionPage",
               "attractions": "CollectionPage", "neighbourhoods": "CollectionPage", "faq": "FAQPage"}.get(kind, "WebPage")
    webpage = {"@type": wp_type, "@id": f"{url}#webpage", "url": url, "name": page["title"], "description": page["description"],
               "inLanguage": LANG, "dateModified": page["modified"], "isPartOf": {"@id": WEB}, "about": {"@id": DEST},
               "publisher": {"@id": ORG},
               "primaryImageOfPage": {"@type": "ImageObject", "url": f"{D}/images/og-default.png", "width": 1200, "height": 630}}
    nodes = [org_node(kind == "about"), {"@type": "WebSite", "@id": WEB, "url": f"{D}/", "name": site["name"], "inLanguage": LANG, "publisher": {"@id": ORG}},
             webpage, destination_node(kind in ("home", "attractions"))]

    if kind == "home":
        webpage["mainEntity"] = {"@id": DEST}
    elif kind == "about":
        webpage["about"] = {"@id": ORG}
        webpage["mainEntity"] = {"@id": ORG}
    elif kind == "attractions":
        nodes += [attraction_node(a) for a in FEATURED]
        webpage["mainEntity"] = {"@type": "ItemList", "numberOfItems": len(FEATURED),
                                 "itemListElement": [{"@type": "ListItem", "position": i, "item": {"@id": attraction_id(a)}} for i, a in enumerate(FEATURED, 1)]}
    elif kind == "neighbourhoods":
        areas = featured_areas()
        nodes += [neighbourhood_node(x) for x in areas]
        webpage["mainEntity"] = {"@type": "ItemList", "itemListElement": [{"@type": "ListItem", "position": i, "item": {"@id": place_id(x)}} for i, x in enumerate(areas, 1)]}
    elif kind == "neighbourhood":
        p = PLACES[page["place"]]
        nodes.append(neighbourhood_node(p, full=True))
        webpage["about"] = webpage["mainEntity"] = {"@id": place_id(p)}
    elif kind == "faq":
        # The FAQPage is the WebPage itself here, so its questions go on the same node.
        webpage["mainEntity"] = faq_node(url)["mainEntity"]
        webpage["speakable"] = {"@type": "SpeakableSpecification", "cssSelector": [".faq summary", ".faq p"]}
    elif kind == "events":
        evs = upcoming_events()
        nodes += [event_node(e, url) for e in evs]
        webpage["mainEntity"] = {"@type": "ItemList", "itemListElement": [{"@type": "ListItem", "position": i, "item": {"@id": f"{url}#{e['id']}"}} for i, e in enumerate(evs, 1)]}
    elif kind == "blog":
        webpage["mainEntity"] = {"@type": "ItemList", "itemListElement": [{"@type": "ListItem", "position": i, "url": f"{D}/blog/{p['slug']}.html", "name": p["title"]} for i, p in enumerate(site["posts"], 1)]}
    elif kind == "post":
        post = next(p for p in site["posts"] if p["slug"] == page["slug_"])
        words = len(re.findall(r"\w+", re.sub(r"<[^>]+>", " ", page["body_"])))
        nodes.append({"@type": "BlogPosting", "@id": f"{url}#article", "headline": post["title"], "description": post["description"], "url": url,
                      "datePublished": post["date"] + "T00:00:00+02:00", "dateModified": post["updated"] + "T00:00:00+02:00", "wordCount": words,
                      "inLanguage": LANG, "image": img_url(post["img"]), "author": {"@id": ORG}, "publisher": {"@id": ORG},
                      "about": {"@id": DEST}, "isPartOf": {"@id": WEB}, "mainEntityOfPage": {"@id": f"{url}#webpage"}})

    if page.get("crumbs"):
        crumbs = [("Home", f"{D}/")] + page["crumbs"]
        nodes.append({"@type": "BreadcrumbList", "@id": f"{url}#breadcrumb",
                      "itemListElement": [{"@type": "ListItem", "position": i, "name": n, "item": u} for i, (n, u) in enumerate(crumbs, 1)]})
        webpage["breadcrumb"] = {"@id": f"{url}#breadcrumb"}
    return {"@context": "https://schema.org", "@graph": nodes}


# ---------------------------------------------------------------- head, footer, analytics, nav
ICONS = {
    "facebook": '<path d="M14 8h3V4h-3c-2.8 0-4 1.8-4 4.3V10H7v4h3v8h4v-8h3l1-4h-4V8.6c0-.4.3-.6.6-.6z"/>',
    "instagram": '<path d="M7 3h10a4 4 0 0 1 4 4v10a4 4 0 0 1-4 4H7a4 4 0 0 1-4-4V7a4 4 0 0 1 4-4zm0 2a2 2 0 0 0-2 2v10c0 1.1.9 2 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2zm5 3.5a3.5 3.5 0 1 1 0 7 3.5 3.5 0 0 1 0-7zm0 2a1.5 1.5 0 1 0 0 3 1.5 1.5 0 0 0 0-3zM17.3 5.7a1 1 0 1 1 0 2 1 1 0 0 1 0-2z"/>',
    "linkedin": '<path d="M5 3a2 2 0 1 1 0 4 2 2 0 0 1 0-4zM3 9h4v12H3zm6 0h4v1.7c.6-1 1.9-2 3.9-2 4.1 0 4.1 2.8 4.1 6.1V21h-4v-5.5c0-1.4 0-3-1.9-3s-2.1 1.4-2.1 2.9V21H9z"/>',
    "x": '<path d="M17.8 3h3.1l-6.8 7.8L22 21h-6.2l-4.8-6.3L5.4 21H2.3l7.3-8.3L2 3h6.4l4.4 5.8zm-1.1 16.2h1.7L7.4 4.7H5.6z"/>',
    "whatsapp": '<path d="M12 2a10 10 0 0 0-8.6 15.1L2 22l5-1.3A10 10 0 1 0 12 2zm0 18.2a8.2 8.2 0 0 1-4.2-1.2l-.3-.2-3 .8.8-2.9-.2-.3A8.2 8.2 0 1 1 12 20.2zm4.5-6.1c-.2-.1-1.5-.7-1.7-.8s-.4-.1-.6.1l-.8 1c-.1.2-.3.2-.5.1a6.7 6.7 0 0 1-3.3-2.9c-.3-.4.3-.4.8-1.4.1-.2 0-.3 0-.4l-.8-1.8c-.2-.5-.4-.4-.6-.4h-.5c-.2 0-.4.1-.6.3-.2.2-.8.8-.8 2s.8 2.3.9 2.5c.1.2 1.6 2.5 4 3.5 1.5.6 2.1.7 2.8.6.5-.1 1.5-.6 1.7-1.2.2-.6.2-1.1.2-1.2l-.4-.2z"/>',
    "email": '<path d="M3 5h18a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1zm1 3.2V17h16V8.2l-8 5.3zM5.2 7 12 11.5 18.8 7z"/>',
}


def svg(name):
    return f'<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" focusable="false">{ICONS[name]}</svg>'


def share_html(url, title):
    """Plain share links: no third-party script, no tracking, works without JavaScript."""
    u, t = urllib.parse.quote(url, safe=""), urllib.parse.quote(title)
    links = [("whatsapp", "WhatsApp", f"https://wa.me/?text={t}%20{u}"),
             ("facebook", "Facebook", f"https://www.facebook.com/sharer/sharer.php?u={u}"),
             ("x", "X", f"https://x.com/intent/post?url={u}&amp;text={t}"),
             ("linkedin", "LinkedIn", f"https://www.linkedin.com/sharing/share-offsite/?url={u}"),
             ("email", "email", f"mailto:?subject={t}&amp;body={u}")]
    return '<ul class="share">' + "".join(f'<li><a href="{h}" aria-label="Share on {n}" rel="noopener" target="_blank">{svg(k)}</a></li>' if k != "email" else f'<li><a href="{h}" aria-label="Share by email">{svg(k)}</a></li>' for k, n, h in links) + "</ul>"


def foot_social():
    names = {"facebook": "Facebook", "instagram": "Instagram", "linkedin": "LinkedIn", "x": "X"}
    return '<ul class="share">' + "".join(f'<li><a href="{u}" aria-label="{names[k]}" rel="me noopener">{svg(k)}</a></li>' for k, u in site["social"].items()) + "</ul>"


def analytics():
    """Consent Mode v2 defaults (denied) inline. gtag.js loads on first interaction or 8 s after load, or only after Accept when
    analytics_requires_consent is true. Empty until ga4_id is set."""
    g = site.get("ga4_id")
    if not g:
        return ""
    return ("<script>window.__analytics=1;window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}"
            "gtag('consent','default',{ad_storage:'denied',ad_user_data:'denied',ad_personalization:'denied',analytics_storage:'denied',wait_for_update:500});"
            f"gtag('js',new Date());gtag('config','{esc(g)}');var d=0,l=function(){{if(d)return;d=1;var s=document.createElement('script');s.async=true;"
            f"s.src='https://www.googletagmanager.com/gtag/js?id={esc(g)}';document.head.appendChild(s)}};window.__loadGtag=l;"
            + ("window.__requireConsent=1;</script>" if site.get("analytics_requires_consent") else
               "['pointerdown','keydown','scroll','touchstart'].forEach(function(e){addEventListener(e,l,{once:true,passive:true})});"
               "addEventListener('load',function(){setTimeout(l,8000)});</script>"))


def nav_html(root, current):
    href = lambda h: (root or "./") if h == "index.html" else root + h
    return "".join(f'<a href="{href(n["href"])}"{" aria-current=page" if n["href"] == current else ""}>{esc(n["label"])}</a>' for n in site["nav"])


# Content Security Policy. Inline scripts are allowed by hash only; build() adds the hashes it finds.
CSP_BASE = ("default-src 'self'; script-src 'self' {hashes} https://www.googletagmanager.com; style-src 'self'; "
            "img-src 'self' data: https://www.googletagmanager.com https://*.google-analytics.com; font-src 'self'; "
            "connect-src 'self' https://api.github.com https://*.google-analytics.com https://*.analytics.google.com https://www.googletagmanager.com; "
            "frame-src 'none'; form-action 'self' https://formspree.io; base-uri 'self'; object-src 'none'")
INLINE_JS = re.compile(r"<script>(.*?)</script>", re.S)


def script_hashes(html_text):
    return sorted({"'sha256-" + base64.b64encode(hashlib.sha256(s.encode()).digest()).decode() + "'" for s in INLINE_JS.findall(html_text)})


def url_for(rel):
    return D + "/" + ("" if rel == "index.html" else rel.replace("index.html", "") if rel.endswith("/index.html") else rel)


# ---------------------------------------------------------------- the map
# The site uses the Figma export (src/map/joburg.svg) once it exists, and the open-data draft until then. Shape ids are
# place ids in both, so nothing else changes when the export arrives.
MAP_SRC = SRC / "map" / ("joburg.svg" if (SRC / "map" / "joburg.svg").exists() else "joburg-draft.svg")
SVG_NS = "http://www.w3.org/2000/svg"
MAP_CREDIT = json.loads((SRC / "data" / "map.json").read_text(encoding="utf-8"))["credit"]
MAP = (0, 0, [])


def build_map():
    """Write docs/map/joburg.svg, a web copy of the base map without the guide-only layers (the dashed view frames) and
    the notes for editors. Returns the map's size and the ids of the areas that have hexagons."""
    import xml.etree.ElementTree as ET
    ET.register_namespace("", SVG_NS)
    tree = ET.fromstring(MAP_SRC.read_text(encoding="utf-8"))
    for g in [g for g in tree if g.get("id") in ("views",)]:
        tree.remove(g)
    for el in tree.iter():
        for a in [a for a in el.attrib if a.startswith("data-")]:
            del el.attrib[a]
    tree.set("role", "img")
    out = OUT / "map"
    out.mkdir(exist_ok=True)
    (out / "joburg.svg").write_text(ET.tostring(tree, encoding="unicode"), encoding="utf-8")
    # The 420 m hexagons as compact data (centre and colour), loaded only when a visitor zooms into a suburb.
    hx = json.loads((SRC / "map" / "hexes.json").read_text(encoding="utf-8"))
    reg = hx.get("levels", {}).get("region")
    if reg:
        data = {"r": round(reg["hex_radius"] * 0.92, 2),
                "areas": {pid: [[x, y, c[1:]] for (x, y), c in zip(cs, reg["colours"][pid])] for pid, cs in reg["areas"].items()}}
        (out / "region.json").write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    hexes = tree.find(f"{{{SVG_NS}}}g[@id='hexes']")
    ids = [g.get("id")[4:] for g in hexes] if hexes is not None else []
    w, h = (round(float(x)) for x in tree.get("viewBox").split()[2:])
    return w, h, [i for i in ids if i in PLACES]


def map_html(root):
    """The home-page map: a plain picture that needs no script, and a suburb picker that js/map.js wakes up. The picker
    lists every area on the map, grouped by part of the city; each option carries what the info panel shows."""
    w, h, ids = MAP
    opts, popular = [], []
    lists = []
    for l in AREAS["lists"]:  # the owner's area lists: only the suburbs drawn on the map
        here = [a for a in l["areas"] if a in ids]
        if here:
            lists.append((l, f'data-name="{esc(l["name"])}" data-areas="{" ".join(here)}" data-colour="{l["colour"]}"'
                             + (f' data-aka="{esc(", ".join(l["aka"]))}"' if l["aka"] else "")))
    popular = [f'<option value="group:{l["id"]}" {attrs}>{esc(l["name"])}</option>' for l, attrs in lists if l["picker"]]
    if popular:
        opts.append(f'<optgroup label="Popular areas">{"".join(popular)}</optgroup>')
    if (SRC / "map" / "source" / "gautrain.json").exists():  # the hexagons that hold a Gautrain station, raised in a gold to purple gradient
        opts.append(f'<optgroup label="Transport"><option value="gautrain" data-name="Gautrain stations" data-href="{root}gautrain.html">Gautrain stations</option></optgroup>')
    panel = "".join(f'<li><button type="button" class="map-list hl-{l["colour"]}" data-list="group:{l["id"]}" {attrs}>{esc(l["name"])}</button></li>'
                    for l, attrs in lists if l["panel"])
    if (SRC / "map" / "source" / "gautrain.json").exists():
        panel += '<li><button type="button" class="map-list hl-gautrain" data-list="gautrain" data-name="Gautrain stations">Gautrain stations</button></li>'
    for rid, r in REGIONS.items():
        here = sorted((PLACES[i] for i in ids if PLACES[i]["region"] == rid), key=lambda p: p["name"])
        if not here:
            continue
        o = f'<option value="all:{rid}" data-name="{esc(r["name"])}">All of {esc(r["name"])}</option>'
        o += "".join(f'<option value="{p["id"]}" data-region="{rid}" data-summary="{esc(p["summary"])}"'
                    + (f' data-href="{root}neighbourhoods/{p["id"]}.html"' if has_page(p) else "") + f'>{esc(p["name"])}</option>' for p in here)
        opts.append(f'<optgroup label="{esc(r["name"])}">{o}</optgroup>')
    return {
        "map_lists": f'<ul class="map-lists">{panel}</ul>' if panel else "",
        "map_controls": f'<div class="map-pick"><label for="map-area">Pick an area</label><select id="map-area"><option value="">Choose an area</option>{"".join(opts)}</select>'
                        f'<button type="button" class="btn btn-ghost" id="map-out" hidden>Whole city</button></div>'
                        f'<div class="map-info" id="map-info" aria-live="polite"></div>',
        "map_figure": f'<figure class="map" id="map"><img src="{root}map/joburg.svg" width="{w}" height="{h}" loading="lazy" decoding="async" '
                      f'alt="Map of Johannesburg: the main suburbs shaded in hexagons, with the ring road of the N1, N3 and N12 around the city, the main roads and the Gautrain line.">'
                      f'<figcaption>Draft map: shapes are approximate. The orange line is the Gautrain. Round icons mark attractions. {esc(MAP_CREDIT)}.</figcaption></figure>'
                      f'<script src="{root}js/map.js?v={VERSIONS["map_js"]}" defer></script>'}


def build_context(meta, body, rel, root, modified):
    canonical = url_for(rel)
    crumbs = []
    if rel not in ("index.html", "404.html") and not rel.endswith("/index.html"):
        if rel.startswith("blog/"):
            crumbs.append(("Blog", f"{D}/blog.html"))
        if rel.startswith("neighbourhoods/"):
            crumbs.append(("Neighbourhoods", f"{D}/neighbourhoods.html"))
        crumbs.append((meta.get("crumb", meta["title"]), canonical))
    page = {**meta, "canonical": canonical, "modified": modified, "crumbs": crumbs, "body_": body}
    if rel.startswith("blog/"):
        page["kind"], page["slug_"] = "post", Path(rel).stem
    if rel.startswith("neighbourhoods/"):
        page["kind"], page["place"] = "neighbourhood", Path(rel).stem
    ctx = {**{k: v for k, v in site.items() if isinstance(v, (str, int))}, **meta}
    post = next((p for p in site["posts"] if rel == f'blog/{p["slug"]}.html'), None)
    ctx.update({
        "lang": LANG, "og_locale": site.get("og_locale", "en_US"), "chrome_lang": "", "hreflang": "",
        "font_preload": f'<link rel="preload" href="{root}fonts/cal-sans/cal-sans-400-latin.woff2" as="font" type="font/woff2" crossorigin>',
        "root": root, "canonical": canonical, "date_modified": fmt_date(modified), "title_full": f'{meta["title"]} | {site["name"]}',
        "og_image": f"{D}/images/og-default.png", "md_href": Path(rel).stem + ".md",
        "body_class": meta.get("body_class", ""), "nav": nav_html(root, rel if "/" not in rel else ""),
        "jsonld": json.dumps(graph(page), ensure_ascii=False, separators=(",", ":")),
        "css_v": VERSIONS["css"], "js_v": VERSIONS["js"], "analytics": analytics(),
        "site_verification": f'<meta name="google-site-verification" content="{esc(site["google_site_verification"])}">' if site["google_site_verification"] else "",
        "phone_link": f'<a href="tel:{site["phone_e164"]}">{esc(site["phone"])}</a>', "year": datetime.date.today().year,
        "robots": meta.get("robots", "index, follow, max-image-preview:large"),
        "hero_preload": (f'<link rel="preload" as="image" type="image/avif" href="{root}images/hero-800w.avif" imagesrcset="{root}images/hero-480w.avif 480w, {root}images/hero-800w.avif 800w, {root}images/hero.avif 1200w" imagesizes="{IMAGES["hero"]["sizes"]}" fetchpriority="high">' if meta.get("hero") == "true" else ""),
        "faq_html": faq_html(), "attractions_html": attractions_html(root), "neighbourhoods_html": neighbourhoods_html(root), "directory_html": directory_html(root), "area_lists_html": area_lists_html(root),
        "events_html": events_html(), "posts_html": posts_html(root), "share_html": share_html(canonical, meta["title"]), "foot_social": foot_social(),
        "attraction_count": len(FEATURED), "neighbourhood_count": sum(1 for p in featured_areas() if p["tags"]),
        **(map_html(root) if rel == "index.html" else {"map_controls": "", "map_figure": "", "map_lists": ""}),
        "area_count": len(PLACES), "region_count": len(REGIONS), "mapped_count": sum(1 for p in PLACES.values() if p["geo"]),
        "info_box": info_box(Path(rel).stem, root) if rel.startswith("neighbourhoods/") else "",
        **{f"info_box_{pid}": info_box(pid, root, level=3) for pid, p in PLACES.items() if p["summary"]},
        "img_hero": img("hero", root, eager=True), "img_card_history": img("card-history", root),
        "img_card_neighbourhoods": img("card-neighbourhoods", root), "img_card_outdoors": img("card-outdoors", root),
        "img_post": img(post["img"], root, eager=True) if post else "",
        "post_date": fmt_date(post["date"]) if post else "", "post_date_iso": post["date"] if post else "",
    })
    return ctx


def render(t, ctx):
    sub = lambda m: str(ctx.get(m.group(1).strip(), m.group(0)))
    for _ in range(2):
        t = re.sub(r"\{\{\s*([\w.-]+)\s*\}\}", sub, t)
    return t


SITEMAP_ORDER = ["index.html", "things-to-do.html", "neighbourhoods.html", "getting-around.html", "gautrain.html", "events.html", "faq.html", "blog.html", "about.html", "contact.html", "accessibility.html"]


def write_sitemap(mod, meta, mds):
    """sitemap.xml lists every indexable HTML page. The Markdown copies are listed in llms.txt (for AI agents) instead,
    and are served with a canonical Link header pointing to the HTML page, so they never compete with it in search."""
    names = sorted((n for n in mod if n != "404.html" and "noindex" not in meta[n].get("robots", "")), key=lambda n: (SITEMAP_ORDER.index(n) if n in SITEMAP_ORDER else 99, n))
    rows = [f"  <url><loc>{url_for(n)}</loc><lastmod>{mod[n]}</lastmod></url>" for n in names]
    (OUT / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(rows) + "\n</urlset>\n", encoding="utf-8")
    llms = [f"# {site['name']}", "", f"> {site['description']}", "",
            "Every page is also available as Markdown at the same address with `.md` in place of `.html` (the home page is `/index.md`). `llms-full.txt` holds all pages in one file.", "", "## Pages", ""]
    llms += [f"- [{meta[n]['title']}]({url_for(n)}): {meta[n]['description']}" for n in names]
    llms += ["", "## Notes for AI systems", "", f"{site['name']} is an independent guide, not an official tourism body. Contact details are placeholders until launch. Check opening hours and prices with each attraction before you visit."]
    (OUT / "llms.txt").write_text("\n".join(llms) + "\n", encoding="utf-8")
    (OUT / "llms-full.txt").write_text("\n\n---\n\n".join(mds[n] for n in names), encoding="utf-8")
    (OUT / "humans.txt").write_text(f"/* TEAM */\nSite: {site['name']}\nContact: {site['email']}\n\n/* SITE */\nBuilt with: Python 3 (standard library), HTML, CSS, JSON-LD\nLast update: {max(mod.values())}\n", encoding="utf-8")
    print(f"  wrote sitemap.xml ({len(rows)} urls), llms.txt, llms-full.txt, humans.txt")


def build():
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "css").mkdir(parents=True)
    (OUT / "js").mkdir()
    (OUT / ".nojekyll").write_text("")
    css = minify_css((ROOT / "css" / "styles.css").read_text(encoding="utf-8"))
    js = minify_js((ROOT / "js" / "scripts.js").read_text(encoding="utf-8"))
    VERSIONS["css"], VERSIONS["js"] = (hashlib.sha256(x.encode()).hexdigest()[:8] for x in (css, js))
    (OUT / "css" / "site.css").write_text(css, encoding="utf-8")
    (OUT / "js" / "scripts.js").write_text(js, encoding="utf-8")
    map_js = minify_js((ROOT / "js" / "map.js").read_text(encoding="utf-8"))
    VERSIONS["map_js"] = hashlib.sha256(map_js.encode()).hexdigest()[:8]
    (OUT / "js" / "map.js").write_text(map_js, encoding="utf-8")
    global MAP
    MAP = build_map()
    if (ROOT / "editor").exists():  # the owner's events editor, served at /editor/ (noindex, not in the sitemap)
        shutil.copytree(ROOT / "editor", OUT / "editor")
    for d in ("images", "fonts", "downloads"):
        if (ROOT / d).exists():
            shutil.copytree(ROOT / d, OUT / d)
    partials = {p.stem: p.read_text(encoding="utf-8") for p in (SRC / "partials").glob("*.html")}
    mod, metas, mds, all_hashes = {}, {}, {}, set()
    for path in sorted((SRC / "pages").rglob("*.html")):
        rel = path.relative_to(SRC / "pages").as_posix()
        meta, body = parse_page(path)
        # 404.html is served at any missing URL, at any depth, so its links must be absolute.
        root = D + "/" if rel == "404.html" else "../" * rel.count("/")
        deps = [path, SRC / "data" / "site.json"] + ([EVENTS_FILE] if rel == "events.html" else [])
        mod[rel] = max(page_modified(d) for d in deps)
        ctx = build_context(meta, body, rel, root, mod[rel])
        doc = partials["head"] + '<body class="{{ body_class }}">\n' + partials["header"] + '<main id="main">\n' + body + "</main>\n" + partials["footer"] + "</body>\n</html>\n"
        out = OUT / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        text = render(doc, ctx)
        hashes = script_hashes(text)
        all_hashes.update(hashes)
        text = text.replace("<!--CSP-->", f'<meta http-equiv="Content-Security-Policy" content="{CSP_BASE.format(hashes=" ".join(hashes))}">')
        out.write_text(text, encoding="utf-8")
        md = main_to_markdown(text, ctx["canonical"]) + f"\nSource: {ctx['canonical']}\n"
        out.with_suffix(".md").write_text(md, encoding="utf-8")
        metas[rel], mds[rel] = meta, md
        print(f"  built {rel}")
    write_sitemap(mod, metas, mds)
    if site.get("cname"):
        (OUT / "CNAME").write_text(site["cname"] + "\n")
    # Header CSP adds what a <meta> policy can't: frame-ancestors and upgrade-insecure-requests.
    csp = CSP_BASE.format(hashes=" ".join(sorted(all_hashes))) + "; frame-ancestors 'none'; upgrade-insecure-requests"
    md_rules = "".join(f"\n/{n[:-5]}.md\n  Link: <{url_for(n)}>; rel=\"canonical\"\n  X-Robots-Tag: noindex\n" for n in mod if n != "404.html")
    fill = lambda t: t.replace("__DOMAIN__", D).replace("__CSP__", csp).replace("__EMAIL__", site["email"])
    for f in ("robots.txt", "_headers", ".htaccess"):
        t = fill((SRC / "static" / f).read_text(encoding="utf-8"))
        if f == "_headers":
            t += md_rules
        (OUT / f).write_text(t, encoding="utf-8")
    (OUT / ".well-known").mkdir()
    (OUT / ".well-known" / "security.txt").write_text(fill((SRC / "static" / "security.txt").read_text(encoding="utf-8")), encoding="utf-8")
    print(f"Done: {len(mod)} pages -> docs/")


if __name__ == "__main__":
    build()
