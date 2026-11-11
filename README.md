# Visit Joburg

An independent visitor's guide to Johannesburg. A fast, accessible static site built from the [my-site](https://github.com/nickjacksonza/my-site) schema, SEO and speed template.

## Quick start

    python3 build.py                        # src/ -> docs/ (Python 3, no packages)
    python3 tools/check.py                  # headings, images, links, JSON-LD, contrast, sitemap
    python3 tools/check_schema_vocab.py     # every schema.org type and property exists (needs network)
    cd docs && python3 -m http.server 3057  # then open http://localhost:3057

1. Edit shared content in `src/data/site.json`: attractions, neighbourhoods, FAQs, posts, contact details. Events live in `content/events.json` (see below).
2. Edit pages in `src/pages/`, styles in `css/styles.css`, script in `js/scripts.js`.
3. Run the build and the checks. Commit `docs/` with your changes.
4. Swap the placeholder images for real photos: put a file at `images/<dir>/<name>.webp` at the size in `src/data/images.json`, then run `pip install pillow && python3 tools/make_images.py --no-fetch`.

## Events editor

Events come from `content/events.json`. Edit that file on GitHub, or use the editor at `/editor/`: sign in with a password, then add, change, hide or remove events and press "Save and publish". The editor commits the file to `main`, and the "Rebuild docs" workflow rebuilds and publishes the site in one to three minutes. A bad edit fails the build, so the live site keeps the last good version.

To turn the editor on:

1. Create a fine-grained GitHub token for this repository only, with Contents: Read and write, and Actions: Read-only.
2. Open `/editor/#setup` on the live site, paste the token and choose a password of 16 or more characters.
3. The page saves only the encrypted token to `editor/sealed.json`. After the rebuild, the password opens the editor.

Set the owner, repo and branch in `editor/config.js`. Run `node tools/test_editor.js` after changing `editor/editor-lib.js`. The editor needs the GitHub Pages deploy with `rebuild-docs.yml`.

## Pages

| Page | Schema |
|------|--------|
| Home | WebPage, TouristDestination (Johannesburg), Organization, WebSite |
| Things to do | CollectionPage, TouristAttraction (with Museum, Park and LandmarksOrHistoricalBuildings), ItemList |
| Neighbourhoods | CollectionPage, Place, ItemList |
| Getting around | WebPage |
| Events | CollectionPage, Event (finished events drop off at build time) |
| FAQ | FAQPage with speakable |
| Blog and posts | CollectionPage, BlogPosting |
| About, Contact, Accessibility, 404 | AboutPage, ContactPage, WebPage |

Every page has breadcrumbs, a `.md` twin, and an entry in `sitemap.xml`, `llms.txt` and `llms-full.txt`.

## Before launch

- Set `domain` (and `cname` if needed) in `site.json`, plus the real email, phone, social links and Formspree ID.
- Set up the events editor, replace the sample events and remove `robots: noindex, follow` from `src/pages/events.html`.
- Replace the placeholder images and `images/og-default.png`.
- Confirm the About page's statements on who writes the guide and how listings are chosen.
- Follow the launch checklist in the template's `speed-seo.html`.

## Deploy

- **GitHub Pages:** Settings, Pages, deploy from `main`, folder `/docs`. `.github/workflows/rebuild-docs.yml` rebuilds `docs/` after edits made on GitHub, and weekly so past events drop off.
- **Shared hosting:** upload everything inside `docs/`. `.htaccess` adds caching, compression and security headers. `_headers` does the same on Cloudflare Pages or Netlify.

Fonts: Cal Sans is under the SIL Open Font License (`fonts/cal-sans/OFL.txt`).
