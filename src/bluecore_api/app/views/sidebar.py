"""Builds the sidebar: how a record links to the records around it.

Has Instance, Instance of, and a section per relationship term. The Hub-Work link
lives in the JSON-LD, not a foreign key, so it is read from both ends.
"""

from typing import Any
from urllib.parse import urlparse

from bluecore_models.models import Hub, Instance, ResourceBase, Work
from sqlalchemy import text as sql_text
from sqlalchemy.orm import object_session

from bluecore_api.app.views import nodes, vocabulary

# Finds the Works pointing at a Hub; works.hub_id is never populated, so their
# bf:relation is searched instead. This form is used because only it can take a
# GIN jsonb_path_ops index (0.22 ms vs 24.3 ms on 50k rows).
_WORKS_FOR_HUB_SQL = sql_text(
    "jsonb_path_query_array(resource_base.data, "
    "'$.relation[*].associatedResource.\"@id\"') @> to_jsonb(cast(:hub_uri as text))"
)


def add_section(
    sidebar: list[dict[str, Any]], label: str, values: list[dict[str, Any]]
) -> None:
    """Add values, folding them into an open section of the same name.

    A transcribed seriesStatement and a bf:relation both belong under Series.
    """
    for section in sidebar:
        if section["label"] == label:
            section["values"] = nodes.dedupe(section["values"] + values)
            return
    sidebar.append({"label": label, "values": values})


def _instance_label(data: dict[str, Any]) -> str:
    """Names an Instance by its imprint: "Hershey, PA: IGI Global, [2025]".

    Its title is its Work's, so only the imprint tells two Instances apart.
    """
    statement = nodes.scalar(data.get("publicationStatement", "")).strip()
    if statement:
        return statement
    for activity in nodes.as_list(data.get("provisionActivity")):
        if not isinstance(activity, dict):
            continue
        parts = [
            text
            for text in (
                nodes.scalar(activity.get(key, "")).strip()
                for key in ("bflc:simplePlace", "bflc:simpleAgent", "bflc:simpleDate")
            )
            if text
        ]
        if len(parts) > 1:
            return f"{parts[0]}: {', '.join(parts[1:])}"
        if parts:
            return parts[0]
    return nodes.access_point(data)


def _record_label(record: ResourceBase) -> str:
    """The text naming a record wherever it is linked from."""
    if isinstance(record, Instance):
        return _instance_label(record.data)
    return nodes.access_point(record.data)


def record_link(record: ResourceBase) -> dict[str, Any]:
    """The one way a sidebar links to a record, so it reads the same everywhere.

    Instances by imprint, everything else by access point.
    """
    return nodes.value(_record_label(record), record.uri)


def _relation_value(
    node: dict[str, Any], enumeration: str, records: dict[str, ResourceBase]
) -> dict[str, Any] | None:
    """One line under a relation's heading.

    A record we hold is named from its own data, since ingestion leaves only a
    bare uri here. One described in place keeps its label, and links only if it
    has a uri.
    """
    uri = node.get("@id") if isinstance(node.get("@id"), str) else None
    record = records.get(uri) if uri else None
    external = False
    if record is not None:
        text, href = _record_label(record), record.uri
    else:
        text, href = nodes.title_of(node), uri
        if uri and urlparse(uri).netloc == nodes.LC_ID_HOST:
            # not a record we hold: LC's readable page for it, in a new tab
            href, external = nodes.source_record_url(uri), True
    if enumeration:
        text = f"{text} {enumeration}".strip()
    if not text:
        return None
    value = nodes.value(text, href)
    if external:
        value["external"] = True
    return value


def relation_sections(
    resource: Hub | Work, label_map: dict[str, str]
) -> list[dict[str, Any]]:
    """Groups a record's bf:relation into a section per relationship term.

    A Work's Series holds the transcribed statement and the Hub controlling it; a
    described Hub gets "Series of", "Translated as" and so on, as LC does.
    """
    relations = [
        r for r in nodes.as_list(resource.data.get("relation")) if isinstance(r, dict)
    ]
    if not relations:
        return []

    uris = [
        node["@id"]
        for relation in relations
        for node in nodes.as_list(relation.get("associatedResource"))
        if isinstance(node, dict) and isinstance(node.get("@id"), str)
    ]
    # Either end can be any record type, so resolve against resource_base in one
    # query for the whole page.
    session = object_session(resource)
    records: dict[str, ResourceBase] = {}
    if uris and session is not None:
        records = {
            row.uri: row
            for row in session.query(ResourceBase)
            .where(ResourceBase.uri.in_(uris))
            .all()
        }

    sections: dict[str, list[dict[str, Any]]] = {}
    for relation in relations:
        label = vocabulary.relationship_label(relation, label_map)
        enumeration = nodes.scalar(relation.get("seriesEnumeration", "")).strip()
        for node in nodes.as_list(relation.get("associatedResource")):
            if not isinstance(node, dict):
                continue
            value = _relation_value(node, enumeration, records)
            if value is not None:
                sections.setdefault(label, []).append(value)
    return [
        {"label": label, "values": nodes.dedupe(sections[label])}
        for label in sorted(sections, key=vocabulary.section_order)
        if sections[label]
    ]


def works_for_hub(hub: Hub) -> list[Work]:
    """The Works pointing at this Hub.

    A Hub holds no pointer down to its Works, so their own relations are searched.
    """
    session = object_session(hub)
    if session is None or not hub.uri:
        return []
    return (
        session.query(Work).where(_WORKS_FOR_HUB_SQL.bindparams(hub_uri=hub.uri)).all()
    )
