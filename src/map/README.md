# The base map

The map of Johannesburg is our own SVG. It starts as a draft drawn from open data, is refined in Figma, and is
exported back here as `joburg.svg`. The home page builds its map from that file (or the draft until then), plus
`src/data/neighbourhoods.json`, `content/area-lists.json` and `src/data/map.json`.

## Files

| File | What it is |
|------|------------|
| `source/nominatim.json` | OpenStreetMap search answers, kept by `tools/fetch_map_sources.py` so the map can be redrawn without the network. The tool copies each found centre into the place's `geo` (with `geo_source`); the map tool uses this file only for area outlines. |
| `source/roads.json` | The ring road's motorway segments (N1 Western, N3 Eastern and N12 Southern Bypass), fetched with `tools/fetch_map_sources.py --roads`. |
| `source/ring_details.json` | The ring road's turnoffs (motorway junction points, with name and exit number) and bridges, from OpenStreetMap's main data API with `tools/fetch_map_sources.py --ring`. |
| `joburg-draft.svg` | The draft, drawn by `tools/make_map.py` from every area and attraction with a position (`geo` in `src/data/neighbourhoods.json` and `attractions.json`), with arrows to places outside the city. 1 km = 10 units. Do not edit by hand: redraw it, or edit in Figma. |
| `audit.md` | Outlines found, places still without a position, the ring road turnoffs to check, and where each position came from. |
| `joburg.svg` | The edited base map, exported from Figma. The site reads this one. (Not made yet.) |

## How a shape links to the data

Every shape's `id` is the place's `id` in `neighbourhoods.json`, for example `fourways`. In Figma this is the layer
name. Names, tags, summaries and guides stay in the JSON, so the SVG never repeats them.

- Layer groups, bottom to top: `regions`, `hexes`, `areas` (outlines only), `main-roads`, `freeways`, `ring-road`, `ring-turnoffs`, `ring-bridges`, `city-boundary`, `attractions`, `labels`, `outlying`, `credit`.
- `hexes` holds the highlight shapes: one shape per area, `hex-<place id>`, made of the hexagons (about 1.4 km across)
  whose centres fall in that area. Every area has at least one. The map page fills them when a toggle matches.
  Gaps between areas narrower than about 6 km (`FILL_KM` in `tools/make_map.py`), such as between Soweto and Diepkloof
  or round Kelvin and Woodmead, join the nearest area, so the hexagons cover the city without holes.
- `ring-road` is the map's main landmark: `ring-n1`, `ring-n3` and `ring-n12`, each over a dark casing, with route
  markers `marker-n1`, `marker-n3` and `marker-n12`. It stays above the area shading in every view.
- `ring-turnoffs` has one stop per interchange, `turnoff-<road>-<exit number>` (for example `turnoff-n1-100`), showing
  the exit number. The full name is in `data-name` in the draft. Both directions of traffic are merged into one stop.
  `ring-bridges` marks the bridges on the ring road, `bridge-<road>-<n>`. `audit.md` lists every turnoff to check.
- `main-roads` holds the main roads (`road-<key>`, white over a dark casing, name along the road as `road-label-<key>`)
  and, thinner and underneath, the inner-city and Soweto streets: Commissioner, Main, Kerk and Smit Streets, Albertina
  Sisulu Road and Vilakazi Street. Their names crowd at city scale, so they are for the Central and Soweto views.
- Region shapes are named `region-<region id>`, labels `label-<place id>`.
- `data-shape="outline"` means the shape came from an OpenStreetMap outline. `data-shape="rough"` means it is a rough
  cell around a single point: the ground nearer that point than any other, at most 2.5 km out (4 km in the main-areas
  draft). Redraw rough shapes
  where it matters.
- The look: a forest-green base (`#1c4a2e`) with the hexagons as a colour wheel on top. Each hexagon's hue is its compass
  direction from the city centre (north red, then clockwise through orange, yellow, green, blue, indigo and violet), and
  its richness grows with distance, from soft grey at the centre to full colour about 14 km out (`wheel()` in
  `tools/make_map.py`). The ring road is white on dark green so it stands out from every colour.
- Hexagons come in levels (`hex_levels` in `src/data/map.json`), smaller as you zoom in: the city level has 20 across
  the ring road (about 1 km each, about 960 in all), the region level has 50 across (about 420 m each, about 5,900, in
  `hexes-region.svg`, groups `hex-region-<place id>`) for views such as Sandton and Rosebank, and the detail level has
  200 across (about 100 m each). The detail
  level would be about 96,000 hexagons over the whole map, too heavy for a page or for Figma, so it is drawn only in
  detail views (`tools/make_detail.py`) and loads only for the part of the map on screen.
- When an SVG from these tools is imported into Figma, set every text layer's outline (stroke) to Outside. Figma ignores
  the SVG setting that puts the outline behind the letters, so labels otherwise turn into blobs.
- `views` holds a dashed frame per view in `src/data/map.json`, as a guide. The city view frames the ring road, and
  `hexes_across_ring` sets the hexagon size from the ring road's width (20 across: about 1 km each).
- `hexes.json` keeps every hexagon's centre and colour, and the map's projection, for the other tools and the map page.
- Prototypes: `exploded-sandton-rosebank.svg` (`tools/make_hex_view.py`) lifts a view out of the city as columns of
  hexagons, and `detail-sandton.svg` (`tools/make_detail.py`) shows street-level detail of a dense area.

## Refine in Figma, then export

1. Open the [Visit Joburg Map](https://www.figma.com/design/PKTBz5zCVfH6QHb0Z3uoOf) file in Figma. Its "Read me" page repeats these steps. Edit shapes on the Map page. Keep each layer's name as it is.
2. To add an area, draw it inside the `areas` group and name the layer with the place's id from `neighbourhoods.json`.
3. To stretch a busy part of the city (for example the centre), scale those shapes together. Keep the rest true to scale.
4. Select the `Joburg base map` frame, then Export > SVG, with "Include 'id' attribute" turned on.
5. Save the file here as `joburg.svg` and commit it.

## Credit

The draft outlines and points are © OpenStreetMap contributors, under the Open Database License. Keep the credit line
on the map. Public map services (Google Maps, OpenStreetMap, Wikipedia) may be used to look up an address or a place's
position, with the source recorded in `geo_source`. Shapes, artwork and tiles from someone else's map are never traced or
copied.
