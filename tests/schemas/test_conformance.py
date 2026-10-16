"""The bibframe-json models against bibframe-json's conformance corpus.

Every document the corpus accepts, the models must read. The ones it rejects
are left to bibframe_json.validate: a stored record cannot be one of them,
since bluecore-models frames every write into the shape, so tolerating them
here would only be legacy handling with nothing to handle.

Skipped when the corpus is not on disk: bibframe-json is a sibling checkout,
not something this application installs with its conformance cases.
"""

import json
import pathlib

import pytest

from bluecore_api.schemas import bibframe

CORPUS = pathlib.Path(__file__).parents[3] / "bibframe-json" / "conformance"

pytestmark = pytest.mark.skipif(
    not CORPUS.is_dir(), reason=f"no conformance corpus at {CORPUS}"
)


def cases(kind: str, verdict: str) -> list[pathlib.Path]:
    return sorted((CORPUS / kind / verdict).glob("*.json")) if CORPUS.is_dir() else []


ALL_CASES = [case for kind in ("linked", "bounded") for case in cases(kind, "accept")]


def parse(document: dict) -> bibframe.Resource:
    """Read a document as the type it claims, the most specific first, since a
    Hub is typed both Work and Hub."""
    types = document.get("@type") or []
    for name, model in (("Hub", bibframe.Hub), ("Instance", bibframe.Instance)):
        if name in types:
            return model.model_validate(document)
    return bibframe.Work.model_validate(document)


def test_the_corpus_was_actually_found():
    """Guards the skipif: a corpus that moved would otherwise check nothing."""
    assert cases("linked", "accept") and cases("bounded", "accept")


@pytest.mark.parametrize(
    "case", ALL_CASES, ids=lambda p: f"{p.parent.parent.name}/{p.stem}"
)
def test_the_models_read_every_case(case):
    parse(json.loads(case.read_text())["document"])
