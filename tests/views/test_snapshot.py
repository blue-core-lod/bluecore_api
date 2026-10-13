"""Every record in a database export against the models, and the fields being
moved onto them against the dict builders they replace.

Opt-in: set BLUECORE_SNAPSHOT to a gzipped CSV dump of resource_base (uri, type,
data, no header). Skipped otherwise, and never run in CI, since the export is a
copy of a whole environment and does not belong in the repo.

The templates are unchanged by moving a field onto the model, so a field that
builds the same values from the model as from the dict renders the same page.
That is what this checks, for every Work, Instance and Hub in the export.
"""

import csv
import gzip
import json
import os
import pathlib
import sys
from collections.abc import Callable

import pytest
from pydantic import ValidationError

from bluecore_api.schemas import bibframe

SNAPSHOT = os.environ.get("BLUECORE_SNAPSHOT")

pytestmark = pytest.mark.skipif(
    not SNAPSHOT or not pathlib.Path(SNAPSHOT).is_file(),
    reason="set BLUECORE_SNAPSHOT to a resource_base CSV export",
)

MODELS = {"works": bibframe.Work, "instances": bibframe.Instance, "hubs": bibframe.Hub}

LABEL_KEYS = ("rdfs:label", "mads:authoritativeLabel")


def _rows():
    csv.field_size_limit(sys.maxsize)
    with gzip.open(SNAPSHOT or "", "rt", newline="") as f:
        for uri, kind, data in csv.reader(f):
            yield uri, kind, json.loads(data)


def _label(data: dict) -> str | None:
    """Roughly what vocabulary.build_label_map reads from an OtherResource.

    Both builders are handed the same map, so it only has to be realistic, not
    exact, for a difference between them to be a real one.
    """
    for key in LABEL_KEYS:
        for value in data.get(key, []):
            text = value.get("@value") if isinstance(value, dict) else value
            if isinstance(text, str) and text:
                return text
    return None


# The fields being moved onto the model right now: each one's key in the
# record, then what the dict builder made of the record and what the model
# builder makes of it, for example
#
#     "classification": (
#         lambda data, lm: fields._classification_values(data.get("classification"), lm),
#         lambda r, data, lm: fields.classification_values(r.classification, lm),
#     ),
#
# A field leaves this table when its dict builder is deleted, so it is a tool
# for making a move, not a lasting regression test. Empty, this still checks
# that every record in the export reads into its model.
MOVED: dict[str, tuple[Callable, Callable]] = {}


def _as_read(values: object) -> object:
    """Values with every run of whitespace collapsed, as a browser renders them.

    So that trimming a stray space a record holds -- a call number's
    "1996  .P4", an unknown date's "    ~/    ~" -- does not count as a change.
    """
    if isinstance(values, str):
        return " ".join(values.split())
    if isinstance(values, list):
        return [_as_read(v) for v in values]
    if isinstance(values, dict):
        return {k: _as_read(v) for k, v in values.items()}
    return values


def test_moved_fields_build_the_same_values_from_the_model():
    # two passes rather than holding every record, since an export of stage
    # runs to a million rows
    label_map: dict[str, str] = {}
    for _, kind, data in _rows():
        if kind == "other_resources":
            label = _label(data)
            if label and isinstance(data.get("@id"), str):
                label_map[data["@id"]] = label

    checked = 0
    unreadable: list[str] = []
    differ: list[str] = []
    for uri, kind, data in _rows():
        if kind not in MODELS:
            continue
        checked += 1
        if data.get("@context") != bibframe.CURRENT_CONTEXT:
            unreadable.append(f"{uri}: context {data.get('@context')!r}")
            continue
        try:
            resource = MODELS[kind].model_validate(data)
        except ValidationError as e:
            unreadable.append(f"{uri}: {e.errors()[0]['msg']}")
            continue
        for key, (from_dict, from_model) in MOVED.items():
            expected = from_dict(data, label_map)
            actual = from_model(resource, data, label_map)
            if _as_read(expected) != _as_read(actual):
                differ.append(f"{uri} {key}\n  dict:  {expected}\n  model: {actual}")

    print(f"\n{checked} records, {len(label_map)} labels, fields: {', '.join(MOVED)}")
    assert not unreadable, f"{len(unreadable)} unreadable:\n" + "\n".join(
        unreadable[:20]
    )
    assert not differ, f"{len(differ)} differ:\n" + "\n".join(differ[:20])
