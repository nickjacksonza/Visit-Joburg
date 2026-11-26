# The base map

The map of Johannesburg is our own SVG. It starts as a draft drawn from open data, is refined in Figma, and is
exported back here as `joburg.svg`. The site will build the map page from that file plus `src/data/neighbourhoods.json`
and `src/data/map.json`.

## Files

| File | What it is |
|------|------------|
| `source/nominatim.json` | OpenStreetMap search results, fetched once by `tools/fetch_map_sources.py` (`--major` for the main areas only). Kept so the draft can be redrawn without the network. |
| `source/positions.json` | Positions for places the search could not find or matched wrongly, each with its source (mostly the place's Wikipedia article). |
| `joburg-draft.svg` | The first draft, drawn by `tools/make_map.py --major`: the 57 main areas, their attractions and arrows to places outside the city. 1 km = 10 units. Do not edit by hand: redraw it, or edit in Figma. |
| `audit.md` | What the draft could and could not match: outlines, rough cells, places not found and the matches to check. |
| `joburg.svg` | The edited base map, exported from Figma. The site reads this one. (Not made yet.) |

## How a shape links to the data

Every shape's `id` is the place's `id` in `neighbourhoods.json`, for example `fourways`. In Figma this is the layer
name. Names, tags, summaries and guides stay in the JSON, so the SVG never repeats them.

- Layer groups: `regions`, `areas`, `city-boundary`, `attractions`, `labels`, `outlying`, `credit`.
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
