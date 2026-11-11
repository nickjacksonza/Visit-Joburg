#!/usr/bin/env python3
"""Post-build checks on docs/. Exits 1 on any failure.

Per HTML page: lang, title and description length, one canonical, one h1, heading order, main landmark,
JSON-LD parses with unique @ids, images have width, height and alt, form fields are labelled, unique ids,
internal links resolve. Site-wide: sitemap URLs exist, every page has a .md copy, robots.txt names the sitemap.
"""
import json, re, sys
from html.parser import HTMLParser
from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent / "docs"
bad = 0


class P(HTMLParser):
    def __init__(s):
        super().__init__(); s.h = []; s.imgs = []; s.links = []; s.ld = False; s.ldtext = []; s.ids = []; s.lang = None
        s.title = ""; s.in_title = False; s.desc = None; s.canon = 0; s.main = 0; s.fields = []; s.labels = set(); s.lbl = 0
    def handle_starttag(s, t, a):
        a = dict(a)
        if t == "html": s.lang = a.get("lang")
        if t == "title": s.in_title = True
        if t == "meta" and a.get("name") == "description": s.desc = a.get("content", "")
        if t == "link" and a.get("rel") == "canonical": s.canon += 1
        if t == "main": s.main += 1
        if re.fullmatch(r"h[1-6]", t): s.h.append(int(t[1]))
        if t == "img": s.imgs.append(a)
        if "id" in a: s.ids.append(a["id"])
        if t == "label": s.lbl += 1
        if t in ("input", "textarea", "select") and a.get("type") not in ("hidden", "submit"):
            s.fields.append((a, s.lbl > 0))
        if t == "label" and a.get("for"): s.labels.add(a["for"])
        if t == "link" and a.get("rel") in ("canonical", "alternate", "icon"): return
        for k in ("href", "src"):
            if a.get(k): s.links.append(a[k])
        if t == "script" and a.get("type") == "application/ld+json": s.ld = True
    def handle_endtag(s, t):
        if t == "script": s.ld = False
        if t == "title": s.in_title = False
        if t == "label": s.lbl -= 1
    def handle_data(s, d):
        if s.ld: s.ldtext.append(d)
        if s.in_title: s.title += d


def err(m):
    global bad; bad += 1; print("FAIL", m)


# Required properties by schema type, following Google's structured data guidelines. Checked on every node,
# including nested ones. A type listed here missing a property fails the build.
REQUIRED = {
    "Organization": ["name", "url"], "WebSite": ["name", "url"], "WebPage": ["name", "url"], "Person": ["name"],
    "BreadcrumbList": ["itemListElement"], "ListItem": ["position"],
    "FAQPage": ["mainEntity"], "Question": ["name", "acceptedAnswer"], "Answer": ["text"],
    "Review": ["author", "reviewBody", "itemReviewed"], "Rating": ["ratingValue", "bestRating"], "AggregateRating": ["ratingValue", "reviewCount"],
    "Product": ["name", "offers"], "Offer": ["price", "priceCurrency"],
    "Event": ["name", "startDate", "location", "eventStatus", "eventAttendanceMode"],
    "JobPosting": ["title", "description", "datePosted", "validThrough", "hiringOrganization", "jobLocation"],
    "VideoObject": ["name", "description", "thumbnailUrl", "uploadDate"],
    "BlogPosting": ["headline", "datePublished", "author", "image"],
    "Course": ["name", "description", "provider", "offers", "hasCourseInstance"], "CourseInstance": ["courseMode"],
    "VacationRental": ["name", "identifier", "image", "latitude", "longitude", "containsPlace"],
    "HowTo": ["name", "step"], "HowToStep": ["text"], "Menu": ["hasMenuSection"], "MenuItem": ["name", "offers"],
    "MedicalCondition": ["name"], "RealEstateListing": ["name", "url"],
    "TouristDestination": ["name", "geo"], "TouristAttraction": ["name", "address", "geo"], "Place": ["name"],
}
LOCAL = {"LocalBusiness", "ProfessionalService", "CafeOrCoffeeShop", "IceCreamShop", "MedicalClinic", "IndividualPhysician", "Dentist", "Attorney",
         "AccountingService", "HairSalon", "SportsActivityLocation", "RealEstateAgent", "Plumber", "LodgingBusiness", "VeterinaryCare"}
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2})?(Z|[+-]\d{2}:\d{2}))?$")


def check_node(n, name):
    if isinstance(n, list):
        for x in n: check_node(x, name)
        return
    if not isinstance(n, dict): return
    types = n.get("@type", [])
    types = types if isinstance(types, list) else [types]
    if "@type" in n:  # nodes that are only {"@id": ...} references are checked where they are defined
        for t in types:
            need = REQUIRED.get(t, []) + (["name", "address"] if t in LOCAL else [])
            for prop in need:
                if prop not in n: err(f"{name}: {t} missing {prop}")
            if t == "VacationRental" and len(n.get("image", [])) < 8: err(f"{name}: VacationRental needs 8+ images")
    for key in ("startDate", "endDate", "datePublished", "dateModified", "datePosted", "validThrough", "uploadDate"):
        if isinstance(n.get(key), str) and not ISO.match(n[key]): err(f"{name}: {key} not ISO 8601 ({n[key]})")
    for v in n.values():
        if isinstance(v, (dict, list)): check_node(v, name)


import datetime
sec = (DOCS / ".well-known" / "security.txt").read_text(encoding="utf-8")
exp = datetime.datetime.fromisoformat(re.search(r"Expires: (\S+)", sec).group(1).replace("Z", "+00:00"))
days = (exp - datetime.datetime.now(datetime.timezone.utc)).days
if not 30 <= days <= 366: err(f"security.txt: Expires is {days} days away; keep it between 30 and 366")

for f in sorted(DOCS.rglob("*.html")):
    name = f.relative_to(DOCS).as_posix(); p = P(); p.feed(f.read_text(encoding="utf-8"))
    if not p.lang: err(f"{name}: no lang")
    if not 10 <= len(p.title) <= 70: err(f"{name}: title length {len(p.title)}")
    if p.desc is None or not 50 <= len(p.desc) <= 170: err(f"{name}: description length {None if p.desc is None else len(p.desc)}")
    if p.canon != 1: err(f"{name}: {p.canon} canonical links")
    if p.main != 1: err(f"{name}: {p.main} main landmarks")
    if p.h.count(1) != 1: err(f"{name}: {p.h.count(1)} h1")
    for a, b in zip(p.h, p.h[1:]):
        if b > a + 1: err(f"{name}: heading jumps from h{a} to h{b}")
    if len(p.ids) != len(set(p.ids)): err(f"{name}: duplicate ids")
    try:
        g = json.loads("".join(p.ldtext))["@graph"]
        check_node(g, name)
        ids = [n["@id"] for n in g if "@id" in n]
        if len(ids) != len(set(ids)): err(f"{name}: duplicate @id")
    except Exception as e:
        err(f"{name}: JSON-LD {e}")
    for i in p.imgs:
        if not (i.get("width") and i.get("height")): err(f"{name}: img without size {i.get('src')}")
        if "alt" not in i: err(f"{name}: img without alt {i.get('src')}")
        for u in re.findall(r"(\S+)\s+\d+w", i.get("srcset", "")):
            if not (f.parent / u).exists(): err(f"{name}: srcset file missing {u}")
    for a, wrapped in p.fields:
        if not wrapped and a.get("id") not in p.labels and not a.get("aria-label"): err(f"{name}: unlabelled field {a.get('name')}")
    for l in p.links:
        if re.match(r"(https?:|mailto:|tel:|data:|#)", l): continue
        path = l.split("#")[0].split("?")[0]
        if path in ("", "./", "../", "/"): continue
        target = DOCS / path.lstrip("/") if path.startswith("/") else f.parent / path
        if not target.exists(): err(f"{name}: missing {l}")
    if not f.with_suffix(".md").exists(): err(f"{name}: no .md copy")
    txt = f.read_text(encoding="utf-8")
    if re.search(r'\sstyle="', txt): err(f"{name}: inline style attribute (blocked by the CSP)")
    if 'http-equiv="Content-Security-Policy"' not in txt: err(f"{name}: no CSP meta")
    if 'content="noindex' in txt and f"/{name}<" in (DOCS / "sitemap.xml").read_text(encoding="utf-8"): err(f"{name}: noindex page in sitemap")

# Home page: 600+ words of copy, and the page title's key words in the h1 and in at least two h2s.
home = (DOCS / "index.html").read_text(encoding="utf-8")
words = len(re.findall(r"\w+", (DOCS / "index.md").read_text(encoding="utf-8")))
if words < 600: err(f"index.html: {words} words, want 600+")
title = re.search(r"<title>(.*?) \|", home).group(1)
keys = [w.lower() for w in re.findall(r"[A-Za-z]{5,}", title)][:3]
h1 = re.search(r"<h1>(.*?)</h1>", home, re.S).group(1).lower()
h2s = [h.lower() for h in re.findall(r"<h2[^>]*>(.*?)</h2>", home, re.S)]
if not all(k in h1 for k in keys[:2]): err(f"index.html: h1 lacks title words {keys[:2]}")
if sum(any(k in h for k in keys) for h in h2s) < 2: err("index.html: title words in fewer than two h2s")

# Colour contrast: every palette colour used as text must reach 4.5:1 on the page background, in both schemes.
css = (DOCS.parent / "css" / "styles.css").read_text(encoding="utf-8")
def lum(h):
    h = h.lstrip("#"); c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= .03928 else ((x + .055) / 1.055) ** 2.4 for x in c]
    return .2126 * c[0] + .7152 * c[1] + .0722 * c[2]
def ratio(a, b):
    x, y = sorted([lum(a), lum(b)]); return (y + .05) / (x + .05)
light = dict(re.findall(r"--(\w+):(#[0-9a-f]{6})", css.split("@media (prefers-color-scheme:dark)")[0]))
dark = {**light, **dict(re.findall(r"--(\w+):(#[0-9a-f]{6})", css.split("@media (prefers-color-scheme:dark){:root{")[1].split("}}")[0]))}
for scheme, t in (("light", light), ("dark", dark)):
    bg = t["offwhite"] if scheme == "light" else t["offblack"]
    for name in ("red", "orange", "green", "blue", "violet", "grey", "offblack" if scheme == "light" else "offwhite"):
        if ratio(t[name], bg) < 4.5: err(f"contrast ({scheme}): {name} on background {ratio(t[name], bg):.2f}")
    if ratio("#1a1c20", t["yellow"]) < 4.5: err(f"contrast ({scheme}): text on yellow")
    if ratio(bg, t["violet"]) < 4.5: err(f"contrast ({scheme}): background colour on violet")

sm = (DOCS / "sitemap.xml").read_text(encoding="utf-8")
for loc in re.findall(r"<loc>(.*?)</loc>", sm):
    path = re.sub(r"^https?://[^/]+/?", "", loc) or "index.html"
    if path.endswith("/"): path += "index.html"
    if not (DOCS / path).exists(): err(f"sitemap: {loc} not built")
if ".md</loc>" in sm: err("sitemap: lists .md files")
if "__" in (DOCS / "_headers").read_text() + (DOCS / ".htaccess").read_text(): err("headers: unreplaced placeholder")
if "Sitemap:" not in (DOCS / "robots.txt").read_text(encoding="utf-8"): err("robots.txt: no Sitemap line")
print("FAILED" if bad else "all checks passed")
sys.exit(1 if bad else 0)
