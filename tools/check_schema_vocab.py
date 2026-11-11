#!/usr/bin/env python3
"""Check every JSON-LD type and property in docs/ against the current schema.org vocabulary.

    python3 tools/check_schema_vocab.py

Downloads the vocabulary (about 1 MB) each run, so it needs network access. Catches typos and
made-up types or properties that tools/check.py cannot see. Exits 1 on any unknown name.
"""
import json, re, sys, urllib.request
from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent / "docs"
URL = "https://schema.org/version/latest/schemaorg-current-https.jsonld"
with urllib.request.urlopen(URL, timeout=60) as r:
    graph = json.load(r)["@graph"]
kind = lambda n: n["@type"] if isinstance(n["@type"], list) else [n["@type"]]
classes = {n["@id"].split(":", 1)[1] for n in graph if "rdfs:Class" in kind(n)}
props = {n["@id"].split(":", 1)[1] for n in graph if "rdf:Property" in kind(n)}
bad = set()


def walk(n, page):
    if isinstance(n, list):
        for x in n: walk(x, page)
    elif isinstance(n, dict):
        for t in (n.get("@type") if isinstance(n.get("@type"), list) else [n.get("@type")] if "@type" in n else []):
            if t not in classes: bad.add(f"{page}: unknown type {t}")
        for k, v in n.items():
            if not k.startswith("@") and k not in props: bad.add(f"{page}: unknown property {k}")
            walk(v, page)


pages = [f for f in DOCS.rglob("*.html") if "editor" not in f.relative_to(DOCS).parts]
for f in pages:
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', f.read_text(encoding="utf-8"), re.S):
        walk(json.loads(block), f.relative_to(DOCS).as_posix())
for b in sorted(bad): print("FAIL", b)
print(f"{len(pages)} pages, {len(classes)} types and {len(props)} properties in the vocabulary: " + ("FAILED" if bad else "all names known"))
sys.exit(1 if bad else 0)
