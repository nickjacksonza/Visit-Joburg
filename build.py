#!/usr/bin/env python3
"""Static site generator for Visit Joburg. Standard library only.

    python3 build.py            # src/ -> docs/
    python3 tools/check.py      # post-build checks
    cd docs && python3 -m http.server 3057

Pages are src/pages/**.html (front matter + body). Placeholders {{ like_this }}
resolve from src/data/site.json, the front matter and the HTML fragments built
below. Visible lists (attractions, neighbourhoods, FAQs, events) and their JSON-LD
come from the same data, so the two cannot drift apart.
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
IMAGES = {i["name"]: i for i in json.loads((SRC / "data" / "images.json").read_text(encoding="utf-8"))}


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
    return "Free" if float(v) == 0 else f"R{v}"


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
    for a in site["attractions"]:
        tags = "".join(f"<li>{esc(t)}</li>" for t in a["tags"])
        out.append(f'<article class="card" id="{a["id"]}">{img(a["img"], root)}<h3>{esc(a["name"])}</h3>'
                   f'<p class="muted">{esc(a["area"])}</p><p>{esc(a["summary"])}</p><ul class="tag-list">{tags}</ul>'
                   f'<p><a href="{maps_url(a["name"], a["lat"], a["lng"])}">Open in Maps<span class="visually-hidden">: {esc(a["name"])}</span></a></p></article>')
    return "\n".join(out)


def neighbourhoods_html():
    return "\n".join(
        f'<section class="card" id="{n["id"]}"><h3>{esc(n["name"])}</h3><p>{esc(n["summary"])}</p>'
        f'<p class="muted">Good for: {esc(n["for"])}</p>'
        f'<p><a href="{maps_url(n["name"], n["lat"], n["lng"])}">Open in Maps<span class="visually-hidden">: {esc(n["name"])}</span></a></p></section>'
        for n in site["neighbourhoods"])


def posts_html(root=""):
    return "\n".join(f'<article class="card"><h3><a href="{root}blog/{p["slug"]}.html">{esc(p["title"])}</a></h3><p class="muted"><time datetime="{p["date"]}">{fmt_date(p["date"])}</time></p><p>{esc(p["description"])}</p></article>' for p in site["posts"])


def fmt_date(d):
    return datetime.date.fromisoformat(d).strftime("%-d %B %Y")


def upcoming_events():
    """Events whose end time is still ahead, soonest first. Rebuild (the workflow also runs weekly) to drop finished ones."""
    now = datetime.datetime.now(datetime.timezone.utc)
    return sorted((e for e in site["events"] if datetime.datetime.fromisoformat(e["end"]) > now), key=lambda e: e["start"])


def fmt_when(e):
    s, t = datetime.datetime.fromisoformat(e["start"]), datetime.datetime.fromisoformat(e["end"])
    return f'{s.strftime("%A %-d %B %Y")}, {s.strftime("%H:%M")} to {t.strftime("%H:%M")}'


def events_html():
    out = [f'<article class="card" id="{e["id"]}"><h3>{esc(e["name"])}</h3><p><time datetime="{e["start"]}">{fmt_when(e)}</time></p>'
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
        n["includesAttraction"] = [{"@id": attraction_id(a)} for a in site["attractions"]]
    return n


def attraction_node(a):
    t = "TouristAttraction" if a["type"] == "TouristAttraction" else ["TouristAttraction", a["type"]]
    n = {"@type": t, "@id": attraction_id(a), "name": a["name"], "description": a["summary"], "url": attraction_id(a),
         "address": addr(a["street"], a.get("locality")), "geo": geo(a), "hasMap": maps_url(a["name"], a["lat"], a["lng"]),
         "image": img_url(a["img"]), "containedInPlace": {"@id": DEST}}
    if a.get("free"):
        n["isAccessibleForFree"] = True
    return n


def neighbourhood_node(x, url):
    return {"@type": "Place", "@id": f"{url}#{x['id']}", "name": x["name"], "description": x["summary"], "geo": geo(x),
            "hasMap": maps_url(x["name"], x["lat"], x["lng"]), "containedInPlace": {"@id": DEST}}


def faq_node(url):
    return {"@type": "FAQPage", "@id": f"{url}#faq", "url": url, "isPartOf": {"@id": f"{url}#webpage"},
            "mainEntity": [{"@type": "Question", "name": f["q"], "acceptedAnswer": {"@type": "Answer", "text": f["a"]}} for f in site["faqs"]]}


def event_node(e, url):
    return {"@type": "Event", "@id": f"{url}#{e['id']}", "name": e["name"], "description": e["description"], "startDate": e["start"], "endDate": e["end"],
            "eventStatus": "https://schema.org/EventScheduled", "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
            "image": [f"{D}/images/og-default.png"], "url": e["url"],
            "location": {"@type": "Place", "name": e["place"], "address": addr(e["street"]), "containedInPlace": {"@id": DEST}},
            "offers": {"@type": "Offer", "price": e["price"], "priceCurrency": site["currency"], "availability": "https://schema.org/InStock", "url": e["url"]}}


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
        nodes += [attraction_node(a) for a in site["attractions"]]
        webpage["mainEntity"] = {"@type": "ItemList", "numberOfItems": len(site["attractions"]),
                                 "itemListElement": [{"@type": "ListItem", "position": i, "item": {"@id": attraction_id(a)}} for i, a in enumerate(site["attractions"], 1)]}
    elif kind == "neighbourhoods":
        nodes += [neighbourhood_node(x, url) for x in site["neighbourhoods"]]
        webpage["mainEntity"] = {"@type": "ItemList", "itemListElement": [{"@type": "ListItem", "position": i, "item": {"@id": f"{url}#{x['id']}"}} for i, x in enumerate(site["neighbourhoods"], 1)]}
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
            "connect-src 'self' https://*.google-analytics.com https://*.analytics.google.com https://www.googletagmanager.com; "
            "frame-src 'none'; form-action 'self' https://formspree.io; base-uri 'self'; object-src 'none'")
INLINE_JS = re.compile(r"<script>(.*?)</script>", re.S)


def script_hashes(html_text):
    return sorted({"'sha256-" + base64.b64encode(hashlib.sha256(s.encode()).digest()).decode() + "'" for s in INLINE_JS.findall(html_text)})


def url_for(rel):
    return D + "/" + ("" if rel == "index.html" else rel.replace("index.html", "") if rel.endswith("/index.html") else rel)


def build_context(meta, body, rel, root, modified):
    canonical = url_for(rel)
    crumbs = []
    if rel not in ("index.html", "404.html") and not rel.endswith("/index.html"):
        if rel.startswith("blog/"):
            crumbs.append(("Blog", f"{D}/blog.html"))
        crumbs.append((meta.get("crumb", meta["title"]), canonical))
    page = {**meta, "canonical": canonical, "modified": modified, "crumbs": crumbs, "body_": body}
    if rel.startswith("blog/"):
        page["kind"], page["slug_"] = "post", Path(rel).stem
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
        "faq_html": faq_html(), "attractions_html": attractions_html(root), "neighbourhoods_html": neighbourhoods_html(),
        "events_html": events_html(), "posts_html": posts_html(root), "share_html": share_html(canonical, meta["title"]), "foot_social": foot_social(),
        "attraction_count": len(site["attractions"]), "neighbourhood_count": len(site["neighbourhoods"]),
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


SITEMAP_ORDER = ["index.html", "things-to-do.html", "neighbourhoods.html", "getting-around.html", "events.html", "faq.html", "blog.html", "about.html", "contact.html", "accessibility.html"]


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
    for d in ("images", "fonts"):
        if (ROOT / d).exists():
            shutil.copytree(ROOT / d, OUT / d)
    partials = {p.stem: p.read_text(encoding="utf-8") for p in (SRC / "partials").glob("*.html")}
    mod, metas, mds, all_hashes = {}, {}, {}, set()
    for path in sorted((SRC / "pages").rglob("*.html")):
        rel = path.relative_to(SRC / "pages").as_posix()
        meta, body = parse_page(path)
        # 404.html is served at any missing URL, at any depth, so its links must be absolute.
        root = D + "/" if rel == "404.html" else "../" * rel.count("/")
        mod[rel] = max(page_modified(d) for d in (path, SRC / "data" / "site.json"))
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
