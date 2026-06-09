#!/usr/bin/env python
"""Download a Library of Congress *.cbd.xml resource and convert it to JSON-LD.

Usage:
    uv run python scripts/cbd_to_jsonld.py <CBD_XML_URL>

Example:
    uv run python scripts/cbd_to_jsonld.py https://id.loc.gov/resources/instances/22442890.cbd.xml

Given a URL ending in ``<INSTANCE_ID>.cbd.xml``, the CBD (RDF/XML) is fetched,
parsed with rdflib, and framed into the Blue Core batch shape — an array with
one framed document per Work, matching ``sample/batch.jsonld``. The result is
written to ``sample/<INSTANCE_ID>.jsonld`` (override with ``--out-dir``) so it
can be loaded with ``uv run bluecore load-file``.

Must be run via ``uv run`` so the ``bluecore_models`` framing helpers are
importable.
"""

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

import rdflib
from bluecore_models.bluecore_graph import BluecoreGraph
from bluecore_models.namespaces import BF
from bluecore_models.utils.graph import frame_jsonld

# matches the trailing "<id>.cbd.xml" portion of a LoC resource URL
INSTANCE_ID_RE = re.compile(r"([^/]+?)\.cbd\.xml$", re.IGNORECASE)

# default output location: the repo's sample/ directory (scripts/ is one level down)
DEFAULT_OUT_DIR = Path(__file__).resolve().parent.parent / "sample"


def instance_id_from_url(url: str) -> str:
    """Pull the instance id out of a ``.../<id>.cbd.xml`` URL."""
    match = INSTANCE_ID_RE.search(url)
    if not match:
        raise ValueError(f"URL does not look like a *.cbd.xml resource: {url}")
    return match.group(1)


def download(url: str) -> bytes:
    """Fetch the CBD XML, requesting RDF/XML explicitly."""
    request = urllib.request.Request(
        url, headers={"Accept": "application/rdf+xml, application/xml"}
    )
    with urllib.request.urlopen(request) as response:
        return response.read()


def cbd_xml_to_batch(xml_bytes: bytes) -> list[dict]:
    """Parse RDF/XML and frame it into the Blue Core batch shape.

    Returns a list with one framed JSON-LD document per named Work in the
    graph, the same structure as ``sample/batch.jsonld``. Blank-node Works
    (e.g. the embedded "other physical format" stub) are skipped — they're
    pulled in as nested resources of the Work that references them.
    """
    graph = rdflib.Graph()
    graph.parse(data=xml_bytes, format="xml")

    bluecore_graph = BluecoreGraph(graph)
    jsonld_data = json.loads(graph.serialize(format="json-ld"))

    batch = []
    for work in bluecore_graph.works():
        uri = work.value(predicate=rdflib.RDF.type, object=BF.Work)
        if uri is None or isinstance(uri, rdflib.BNode):
            # only named Works become top-level batch documents
            continue
        batch.append(frame_jsonld(str(uri), jsonld_data))

    return batch


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="LoC *.cbd.xml resource URL")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help="directory to write <INSTANCE_ID>.jsonld into (default: the repo's sample/ dir)",
    )
    args = parser.parse_args(argv)

    instance_id = instance_id_from_url(args.url)

    print(f"Downloading {args.url} ...", file=sys.stderr)
    xml_bytes = download(args.url)

    print("Converting CBD XML to framed JSON-LD ...", file=sys.stderr)
    batch = cbd_xml_to_batch(xml_bytes)
    if not batch:
        print("No named Work found in the CBD — nothing written.", file=sys.stderr)
        return 1

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / f"{instance_id}.jsonld"
    out_path.write_text(json.dumps(batch, indent=2), encoding="utf-8")

    print(f"Wrote {out_path} ({len(batch)} work(s))", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
