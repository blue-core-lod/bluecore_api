"""Builds the sidebar: how a record links to the records around it.

Has Instance, Instance of, and a section per relationship term. The Hub-Work link
is a foreign key, set at ingest from bf:expressionOf, so it is read from there.
"""

from collections.abc import Mapping
from urllib.parse import urlparse

from bluecore_models.models import Hub, Instance, ResourceBase, Work
from sqlalchemy.orm import object_session

from bluecore_api.app.views import nodes, vocabulary


def add_section(
    sidebar: list[dict[str, object]], label: str, values: list[dict[str, object]]
) -> None:
    """Adds values under a heading, reusing that heading if it is already open.

    Two different properties can belong under one heading -- a transcribed
    seriesStatement and a bf:relation both read as Series -- and the reader
    should see it once, not twice.
    """
    for section in sidebar:
        if section["label"] == label:
            existing = section["values"]
            combined = (existing if isinstance(existing, list) else []) + values
            section["values"] = nodes.dedupe(combined)
            return
    sidebar.append({"label": label, "values": values})


def _instance_label(data: Mapping[str, object]) -> str:
    """Names an Instance by its imprint: "Hershey, PA: IGI Global, [2025]".

    Every Instance of a Work repeats that Work's title, so the title cannot tell
    two printings apart and the publisher and date have to.
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
    """The text that names a record in a link, whichever page the link is on."""
    if isinstance(record, Instance):
        return _instance_label(record.data)  # ty: ignore[invalid-argument-type]
    return nodes.access_point(record.data)  # ty: ignore[invalid-argument-type]


def record_link(record: ResourceBase) -> dict[str, object]:
    """Builds every sidebar link, so a record reads the same on every page.

    Instances are named by their imprint, everything else by its access point.
    """
    return nodes.value(_record_label(record), record.uri)


def _relation_value(
    node: Mapping[str, object], enumeration: str, records: dict[str, ResourceBase]
) -> dict[str, object] | None:
    """One line under a relation's heading, linked when there is somewhere to go.

    Ingestion leaves only a bare uri behind, so a record we hold is named from
    its own data. One described in place keeps the label written here, and a
    transcribed statement -- which has no uri at all -- stays plain text.
    """
    uri = nodes.link_uri(node.get("@id"))
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


def _records_by_uri(resource: ResourceBase, uris: list[str]) -> dict[str, ResourceBase]:
    """The records we hold for those uris, looked up in one query."""
    session = object_session(resource)
    if not uris or session is None:
        return {}
    return {
        row.uri: row
        for row in session.query(ResourceBase).where(ResourceBase.uri.in_(uris)).all()
    }


def linked_records(resource: ResourceBase, key: str) -> list[dict[str, object]]:
    """Sidebar values for a key that points straight at other records by uri.

    Covers both ends of the Hub-Work pair -- expressionOf going up and
    hasExpression coming back down -- and names each target from its own record,
    since the data holds nothing but a uuid.
    """
    candidates = [
        n
        for n in nodes.as_list(resource.data.get(key))  # ty: ignore[unresolved-attribute]
        if isinstance(n, dict)
    ]
    records = _records_by_uri(
        resource, [u for n in candidates if (u := nodes.link_uri(n.get("@id")))]
    )
    values = [_relation_value(n, "", records) for n in candidates]
    return nodes.dedupe([v for v in values if v is not None])


def relation_sections(
    resource: Hub | Work, label_map: dict[str, str]
) -> list[dict[str, object]]:
    """Groups a record's bf:relation into one sidebar section per relationship.

    A Work's Series section holds both the series as printed and the Hub that
    controls it. A fully described Hub points back the other way, so it gets a
    section each for "Series of", "Translated as", "Part of" and the rest.
    """
    relations = [
        r
        for r in nodes.as_list(resource.data.get("relation"))  # ty: ignore[unresolved-attribute]
        if isinstance(r, dict) and not vocabulary.is_exempt_relation(r)
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

    sections: dict[str, list[dict[str, object]]] = {}
    for relation in relations:
        labels = vocabulary.relationship_labels(relation, label_map)
        enumeration = nodes.scalar(relation.get("seriesEnumeration", "")).strip()
        for node in nodes.as_list(relation.get("associatedResource")):
            if not isinstance(node, dict):
                continue
            value = _relation_value(node, enumeration, records)
            if value is None:
                continue
            for label in labels:
                sections.setdefault(label, []).append(value)
    return [
        {"label": label, "values": nodes.dedupe(sections[label])}
        for label in sorted(sections, key=vocabulary.section_order)
        if sections[label]
    ]


def works_for_hub(hub: Hub) -> list[Work]:
    """The Works linked to this Hub by works.hub_id.

    Ingest sets the foreign key from bf:expressionOf, adding the inverse of a
    bf:hasExpression first, so either direction in the payload arrives here. A
    Hub with no session of its own has no Works to report, which is empty rather
    than an error.
    """
    return list(hub.works)
