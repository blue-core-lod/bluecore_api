#!/usr/bin/env python
"""Download a Library of Congress *.cbd.xml resource and convert it to JSON-LD.

Usage:
    uv run python scripts/cbd_to_jsonld.py <CBD_XML_URL>

Example:
    uv run python scripts/cbd_to_jsonld.py https://id.loc.gov/resources/instances/22442890.cbd.xml

Given a URL ending in ``<INSTANCE_ID>.cbd.xml``, the CBD (RDF/XML) is fetched,
parsed with rdflib, and written out as ``<INSTANCE_ID>.jsonld`` in the repo's
``sample/`` directory (override with ``--out-dir``).
"""

import argparse
import re
import sys
import urllib.request
from pathlib import Path

from rdflib import Graph

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


def cbd_xml_to_jsonld(xml_bytes: bytes) -> str:
    """Parse RDF/XML and re-serialize as pretty JSON-LD."""
    graph = Graph()
    graph.parse(data=xml_bytes, format="xml")
    return graph.serialize(format="json-ld", indent=2)


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

    print("Converting CBD XML to JSON-LD ...", file=sys.stderr)
    jsonld = cbd_xml_to_jsonld(xml_bytes)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / f"{instance_id}.jsonld"
    out_path.write_text(jsonld, encoding="utf-8")

    print(f"Wrote {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
