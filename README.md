# Visit Joburg

An independent visitor's guide to Johannesburg. A fast, accessible static site built from the [my-site](https://github.com/nickjacksonza/my-site) schema, SEO and speed template, with an interactive map of the city drawn from our own SVG.

The aim is 100 in every Lighthouse category, clean Rich Results Test output, and pages that answer engines can read. Working rules for anyone editing the code, people or Claude, are in [`CLAUDE.md`](CLAUDE.md).

## Quick start

    python3 build.py                        # src/ -> docs/ (Python 3 standard library only)
    python3 tools/check.py                  # headings, images, links, JSON-LD, contrast, sitemap, map colours
    python3 tools/check_schema_vocab.py     # every schema.org type and property exists (needs network)
    node tools/test_editor.js               # the two editors' rules, and that saves don't reformat their files
    cd docs && python3 -m http.server 3057  # then open http://localhost:3057

Run the build and the checks before every commit, and commit `docs/` with your changes. GitHub Pages serves `docs/` from `main`.

## How the site is put together

| Folder | What's in it |
|--------|--------------|
| `src/pages/` | One HTML file per page, with front matter (title, description, kind). `kind` picks the page's schema. |
| `src/partials/` | The head, header and footer shared by every page. |
| `src/data/` | Data the developer edits (see below). |
| `content/` | Data the owner edits in the browser, through the editors at `/editor/`. |
| `src/map/` | The base map: the draft SVG, its sources and the hexagon data. See [`src/map/README.md`](src/map/README.md). |
| `css/`, `js/` | Readable sources. The build minifies them and adds a content hash to each URL. |
| `editor/` | The owner's editors: events and area lists. |
| `tools/` | Checks, tests, image placeholders and the one-off map tools. |
| `docs/` | The built site. Generated: never edit by hand. |

`build.py` reads everything, checks it, and writes `docs/`. A bad entry in any data file stops the build with a plain message, so the live site keeps its last good version.

## The data files

| File | Holds | Edited by |
|------|-------|-----------|
| `src/data/site.json` | Site settings: name, contact details, nav, city, FAQs, blog posts, analytics ids | Developer |
| `src/data/neighbourhoods.json` | The tag list, the 9 parts of the city and every area (196): position, summary, tags | Developer |
| `src/data/attractions.json` | Every attraction once (28). Featured ones get a card and schema on the things-to-do page | Developer |
| `src/data/map.json` | Map settings: hexagon sizes, the Figma view frames, the landmark and the credit | Developer |
| `src/data/images.json` | Each image, its sizes and alt text | Developer |
| `content/events.json` | Events | Owner, at `/editor/` |
| `content/area-lists.json` | Area lists: popular names for groups of suburbs (The Parks, Town) and themes (Nightlife), each with a colour | Owner, at `/editor/area-lists.html` |

Each file keeps one item per line, so a change shows as one line on GitHub. A place is named in one file only, and every other file refers to it by `id`.

**Positions.** Each area and attraction has one `geo` (its centre) and a `geo_source` saying where the position came from. Examples are "OpenStreetMap", "Wikipedia: Kliptown" or "Owner: the corner of Waterfall Avenue and Athole Avenue". `geo` stays `null` until a place has been looked up. Never guess a position.

## Neighbourhoods and info boxes

- An area with a `summary` gets a card on the neighbourhoods page. Every area appears in the list at the foot of that page, grouped by part of the city. Main areas (`major`) are in bold.
- An area guide is a page at `src/pages/neighbourhoods/<id>.html` with `{{ info_box }}` after the lead paragraph. Braamfontein and Fourways are the examples.
- The info box shows the area's summary, part of the city, tags and the attractions in it. Any page can show one with `{{ info_box_<id> }}`.
- The neighbourhoods page also lists the area lists, so the groups on the map can be read without script.

## The map

The home page shows the map in a full-width green band.

- **Without script:** it's a plain picture.
- **The picker:** choosing an area list, a part of the city or a single suburb zooms in and lifts that area's hexagons as see-through columns. Tapping a suburb on the map picks it too.
- **The Area lists panel:** shows the owner's lists as colour-coded buttons.
- **Zooming in:** the map swaps its 1 km hexagons for 420 m ones.
- **Loading:** the map and its data load only when someone first uses the map.

The map file is our own SVG, true to geography (1 km = 10 units). `tools/make_map.py` draws the draft from OpenStreetMap data and the positions in the data files. The draft is refined in the Figma file "Visit Joburg Map" and will come back as `src/map/joburg.svg`. Every shape's id is its place id. The map tools need the network and `pip install shapely`; the site build never runs them.

    python3 tools/fetch_map_sources.py      # look up places without a position, and fill in geo
    python3 tools/fetch_map_sources.py --corner "Waterfall Avenue" "Athole Avenue"   # where two streets meet
    python3 tools/make_map.py               # redraw the draft map, hexagons and audit (src/map/audit.md)

`src/map/audit.md` lists the places still without a position and the source of every position.

## The editors

Both editors live under `/editor/`, use one password, and save by committing their JSON file to `main`. The "Rebuild docs" workflow then rebuilds and publishes the site in one to three minutes. GitHub Pages can't password-protect a page, so the password unlocks an encrypted GitHub token kept in `editor/sealed.json`.

- **Events** (`/editor/`): add, change, hide or remove events.
- **Area lists** (`/editor/area-lists.html`): name a list, give it other names, pick its colour and its suburbs, and choose whether it shows in the picker, the Area lists panel, or neither.

To turn the editors on:

1. Create a fine-grained GitHub token for this repository only, with Contents: Read and write, and Actions: Read-only.
2. Open `/editor/#setup` on the live site, paste the token and choose a password of 16 or more characters.
3. The page saves only the encrypted token. After the rebuild, the password opens both editors.

## Pages

| Page | Schema |
|------|--------|
| Home | WebPage, TouristDestination (Johannesburg), Organization, WebSite |
| Things to do | CollectionPage, TouristAttraction (with Museum, Park and others), ItemList |
| Neighbourhoods and area guides | CollectionPage, Place |
| Getting around | WebPage |
| Events | CollectionPage, Event (finished events drop off at build time) |
| FAQ | FAQPage with speakable |
| Blog and posts | CollectionPage, BlogPosting |
| About, Contact, Accessibility, 404 | AboutPage, ContactPage, WebPage |

Every page has breadcrumbs, a `.md` twin, and an entry in `sitemap.xml`, `llms.txt` and `llms-full.txt`.

## Before launch

- Set `domain` (and `cname` if needed) in `site.json`, plus the real email, phone, social links and Formspree ID.
- Set up the editors, replace the sample events and remove `robots: noindex, follow` from `src/pages/events.html`.
- Replace the placeholder images and `images/og-default.png`.
- Replace the draft map with the Figma export (`src/map/joburg.svg`).
- Confirm the About page's statements on who writes the guide and how listings are chosen.
- Follow the launch checklist in the template's `speed-seo.html`.

## Deploy

- **GitHub Pages:** Settings, Pages, deploy from `main`, folder `/docs`. `.github/workflows/rebuild-docs.yml` rebuilds `docs/` after edits made on GitHub, and weekly so past events drop off. Merging to `main` is a live deploy.
- **Shared hosting:** upload everything inside `docs/`. `.htaccess` adds caching, compression and security headers. `_headers` does the same on Cloudflare Pages or Netlify.

Fonts: Cal Sans is under the SIL Open Font License (`fonts/cal-sans/OFL.txt`). Map data © OpenStreetMap contributors, under the Open Database License.
