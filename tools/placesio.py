"""Read and write src/data/neighbourhoods.json and src/data/attractions.json in their usual layout: one place per line,
so a change shows as one changed line on GitHub. Used by the map tools that fill in positions."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLACES = ROOT / "src" / "data" / "neighbourhoods.json"
ATTRACTIONS = ROOT / "src" / "data" / "attractions.json"


def _line(d):
    return "    " + json.dumps(d, ensure_ascii=False)


def _rows(items):
    return [_line(x) + ("," if i < len(items) - 1 else "") for i, x in enumerate(items)]


def load():
    return json.loads(PLACES.read_text(encoding="utf-8")), json.loads(ATTRACTIONS.read_text(encoding="utf-8"))


def save(places, attractions):
    p = ["{", '  "tags": ' + json.dumps(places["tags"], ensure_ascii=False) + ",", '  "regions": ['] + _rows(places["regions"])
    p += ["  ],", '  "places": ['] + _rows(places["places"]) + ["  ]", "}"]
    PLACES.write_text("\n".join(p) + "\n", encoding="utf-8")
    a = ["{", '  "attractions": ['] + _rows(attractions["attractions"]) + ["  ]", "}"]
    ATTRACTIONS.write_text("\n".join(a) + "\n", encoding="utf-8")
