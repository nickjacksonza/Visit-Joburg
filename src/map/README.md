# The base map

The map of Johannesburg is our own SVG. It starts as a draft drawn from open data, is refined in Figma, and is
exported back here as `joburg.svg`. The site will build the map page from that file plus `src/data/neighbourhoods.json`
and `src/data/map.json`.

## Files

| File | What it is |
|------|------------|
| `source/nominatim.json` | OpenStreetMap search results, fetched once by `tools/fetch_map_sources.py` (`--major` for the main areas only). Kept so the draft can be redrawn without the network. |
| `source/roads.json` | The ring road's motorway segments (N1 Western, N3 Eastern and N12 Southern Bypass), fetched with `tools/fetch_map_sources.py --roads`. |
| `source/ring_details.json` | The ring road's turnoffs (motorway junction points, with name and exit number) and bridges, from OpenStreetMap's main data API with `tools/fetch_map_sources.py --ring`. |
| `source/positions.json` | Positions for places the search could not find or matched wrongly, each with its source (mostly the place's Wikipedia article). |
| `joburg-draft.svg` | The first draft, drawn by `tools/make_map.py --major`: the 57 main areas, their attractions and arrows to places outside the city. 1 km = 10 units. Do not edit by hand: redraw it, or edit in Figma. |
| `audit.md` | What the draft could and could not match: outlines, rough cells, places not found and the matches to check. |
| `joburg.svg` | The edited base map, exported from Figma. The site reads this one. (Not made yet.) |

## How a shape links to the data

Every shape's `id` is the place's `id` in `neighbourhoods.json`, for example `fourways`. In Figma this is the layer
name. Names, tags, summaries and guides stay in the JSON, so the SVG never repeats them.

- Layer groups, bottom to top: `regions`, `areas`, `hexes`, `ring-road`, `ring-turnoffs`, `ring-bridges`, `city-boundary`, `attractions`, `labels`, `outlying`, `credit`.
- `hexes` holds the highlight shapes: one shape per area, `hex-<place id>`, made of the hexagons (about 1.4 km across)
  whose centres fall in that area. Every area has at least one. The map page fills them when a toggle matches.
- `ring-road` is the map's main landmark: `ring-n1`, `ring-n3` and `ring-n12`, each over a dark casing, with route
  markers `marker-n1`, `marker-n3` and `marker-n12`. It stays above the area shading in every view.
- `ring-turnoffs` has one stop per interchange, `turnoff-<road>-<exit number>` (for example `turnoff-n1-100`), showing
  the exit number. The full name is in `data-name` in the draft. Both directions of traffic are merged into one stop.
  `ring-bridges` marks the bridges on the ring road, `bridge-<road>-<n>`. `audit.md` lists every turnoff to check.
- Region shapes are named `region-<region id>`, labels `label-<place id>`.
- `data-shape="outline"` means the shape came from an OpenStreetMap outline. `data-shape="rough"` means it is a rough
  cell around a single point: the ground nearer that point than any other, at most 2.5 km out (4 km in the main-areas
  draft). Redraw rough shapes
  where it matters.
- Colours in the SVG are only for editing. The site replaces them with its own colour tokens.

## Refine in Figma, then export

1. Open the [Visit Joburg Map](https://www.figma.com/design/PKTBz5zCVfH6QHb0Z3uoOf) file in Figma. Its "Read me" page repeats these steps. Edit shapes on the Map page. Keep each layer's name as it is.
2. To add an area, draw it inside the `areas` group and name the layer with the place's id from `neighbourhoods.json`.
3. To stretch a busy part of the city (for example the centre), scale those shapes together. Keep the rest true to scale.
4. Select the `Joburg base map` frame, then Export > SVG, with "Include 'id' attribute" turned on.
5. Save the file here as `joburg.svg` and commit it.

## Credit

The draft outlines and points are © OpenStreetMap contributors, under the Open Database License. Keep the credit line
on the map. Reference maps under someone else's copyright (such as printed or watermarked maps) may be used to check
names and positions, but not traced.
