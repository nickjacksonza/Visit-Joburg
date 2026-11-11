# Visit Joburg

An independent visitor's guide to Johannesburg, built from the my-site schema, SEO and speed template. Aim: 100 in Lighthouse (performance, accessibility, best practices, SEO), clean Rich Results Test output, and pages that answer engines can read.

## Build

    python3 build.py                        # src/ -> docs/ (standard library only)
    python3 tools/check.py                  # must pass before every commit
    python3 tools/check_schema_vocab.py     # schema.org names (needs network)
    node tools/test_editor.js               # after editor or events JSON changes
    cd docs && python3 -m http.server 3057  # preview
    pip install pillow && python3 tools/make_images.py   # placehold.co WebP/AVIF placeholders into images/

## Rules

- `docs/` is generated and committed. Rebuild and commit it with every change to `src/`, `content/`, `css/`, `js/`, `editor/` or `images/`. Never edit `docs/` by hand.
- `src/data/site.json` is the single source for anything on more than one page (contact details, city, attractions, neighbourhoods, FAQs, posts, analytics ids). Visible lists and their JSON-LD are built from it, so they stay in step. `src/data/images.json` lists each image, its sizes and alt text.
- Pages are `src/pages/**.html` with front matter (`title`, `description`, `kind`, optional `robots`, `crumb`, `hero`, `body_class`). `kind` picks the schema built in `graph()` in `build.py`: `home`, `attractions`, `neighbourhoods`, `events`, `faq`, `blog`, `about`, `contact`. Pages under `blog/` are posts and need a matching entry in `posts`.
- Every internal link and asset path is relative to the page depth (`{{ root }}`). Never hardcode a leading `/`.
- No inline `style=""` attributes and no inline event handlers: the Content Security Policy blocks them. Inline `<script>` blocks are allowed only because `build.py` hashes them into the policy.
- `example.com` appears only in `site.json` (`domain`, `email`, placeholder URLs); static files use `__DOMAIN__`, `__EMAIL__` and `__CSP__`, which `build.py` fills in.
- Pages that must stay out of search set `robots: noindex, ...`; they are left out of the sitemap and `llms.txt`. `events.html` is noindex until real events replace the samples.
- No iframes or third-party scripts that load on page load. The CSP sets `frame-src 'none'`; widen it only for a click-to-load embed.

## Events editor

- `content/events.json` is the single source for events. Do not copy it into `src/data/`. `build.py` (`load_events`) validates it with the same rules as `editor/editor-lib.js`; a bad edit fails the build.
- The file keeps one event per line, soonest first. Times are local (`2026-12-05T09:00`); `timezone` adds the offset at build. Events with `published: false`, or that have ended, are left off the page and out of the schema.
- `editor/` is the owner's editor (static, served at `/editor/`, noindex, not in the sitemap or the `tools/check.py` page checks). It holds only `editor/sealed.json`, the encrypted token. Never commit a token.
- After changing `editor/editor-lib.js` or the JSON layout, run `node tools/test_editor.js`. It checks that saving does not reformat the file.
- Saves commit the JSON to `main`; `rebuild-docs.yml` rebuilds `docs/` and publishes. The workflow name must stay "Rebuild docs" because the editor follows that run.

## Content

- Facts about places must be checkable and slow to change. Do not list opening hours or prices for attractions; tell visitors to check with the place.
- Never invent reviews, ratings, awards or events. The site is not an official tourism body and must not suggest it is.
- Attractions use `TouristAttraction`, with a second type (`Museum`, `Park`, `LandmarksOrHistoricalBuildings`) when one fits. All places link to the `TouristDestination` node by `@id`.

## Design

- Colours come only from the tokens in `css/styles.css`: `--red --orange --yellow --green --blue --violet --offblack --offwhite --grey`, each with a dark-scheme value. `tools/check.py` checks contrast for both schemes. Yellow is a background only, with off-black text.
- Headings use Cal Sans (`--display`); body text uses the system stack.
- No auto-playing sliders or carousels. Nothing moves without the visitor asking.

## Quality bar for any page

- One `h1`, headings in order, a unique `title` (10 to 70 characters with the site name) and `description` (50 to 170), one canonical.
- Every image: `width`, `height`, `alt`, `srcset` and `sizes`. Only the hero is eager. All others are lazy.
- Schema describes only what is visible on the page. Nodes link by `@id`.
- Contrast 4.5 to 1, visible focus, 44 px targets, labelled form fields, a skip link, reduced-motion support. No script is needed to read content or use the nav.
- Third-party scripts load on first interaction or after 8 seconds. Analytics starts with consent denied.

## Deploy

- GitHub Pages: deploy from branch `main`, folder `/docs`. Merging to `main` is a live deploy. Only the owner merges.

## Voice

Plain words, concrete nouns, contractions where natural. South African English spelling (neighbourhood, colour) and `en-ZA`. No emoji. Avoid "X, not Y" constructions and em dashes. Follow ISO 24495-1 plain-language guidance.
