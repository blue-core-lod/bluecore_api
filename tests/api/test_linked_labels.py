"""expand=true labels the Works, Instances and Hubs a resource links to (#361).

The editor names a linked resource only by `<uri> rdfs:label`, so each link
needs one or it loads unlabeled and fails "Label required" on every reload.
"""

import rdflib
import sqlalchemy
from bluecore_models.models import Instance, ResourceBase, Work
from bluecore_models.utils.graph import load_jsonld
from rdflib import RDFS, Literal, URIRef

WORK_UUID = "0b4e0e8a-1b1a-4c3e-9d6f-361000000001"
INSTANCE_UUID = "0b4e0e8a-1b1a-4c3e-9d6f-361000000002"
WORK_URI = f"https://bluecore.info/works/{WORK_UUID}"
INSTANCE_URI = f"https://bluecore.info/instances/{INSTANCE_UUID}"


def _add_pair(db_session, work_title=None, instance_title=None):
    """A Work and its Instance, linked both ways in their data and the database."""
    work_data = {
        "@id": WORK_URI,
        "@type": "Work",
        "hasInstance": {"@id": INSTANCE_URI},
    }
    if work_title is not None:
        work_data["title"] = work_title
    work = Work(id=1, uuid=WORK_UUID, uri=WORK_URI, data=work_data)
    db_session.add(work)

    instance_data = {
        "@id": INSTANCE_URI,
        "@type": "Instance",
        "instanceOf": {"@id": WORK_URI},
    }
    if instance_title is not None:
        instance_data["title"] = instance_title
    db_session.add(
        Instance(
            id=2, uuid=INSTANCE_UUID, uri=INSTANCE_URI, work=work, data=instance_data
        )
    )
    db_session.commit()
    return work_data, instance_data


def _graph(client, path: str) -> rdflib.Graph:
    response = client.get(path, headers={"Accept": "application/vnd.sinopia+json"})
    assert response.status_code == 200
    return load_jsonld(response.json()["data"])


def _labels(graph: rdflib.Graph, uri: str) -> list:
    return list(graph.objects(URIRef(uri), RDFS.label))


def test_work_labels_its_instance(client, db_session):
    work_data, _ = _add_pair(
        db_session,
        instance_title={
            "@type": "Title",
            "mainTitle": {"@value": "Pride and prejudice", "@language": "en"},
        },
    )

    expanded = _graph(client, f"/works/{WORK_UUID}?expand=true")
    assert _labels(expanded, INSTANCE_URI) == [
        Literal("Pride and prejudice", lang="en")
    ]

    plain = _graph(client, f"/works/{WORK_UUID}")
    assert _labels(plain, INSTANCE_URI) == []
    assert len(plain) == len(load_jsonld(work_data))


def test_instance_labels_its_work(client, db_session):
    _, instance_data = _add_pair(
        db_session, work_title={"@type": "Title", "mainTitle": "Emma"}
    )

    expanded = _graph(client, f"/instances/{INSTANCE_UUID}?expand=true")
    assert _labels(expanded, WORK_URI) == [Literal("Emma")]

    plain = _graph(client, f"/instances/{INSTANCE_UUID}")
    assert _labels(plain, WORK_URI) == []
    assert len(plain) == len(load_jsonld(instance_data))


def test_malformed_language_tag_is_dropped(client, db_session):
    _, instance_data = _add_pair(db_session)
    # bluecore_models' after_insert hook parses data with rdflib, which rejects
    # "en_US", so write the bad tag with a Core UPDATE that skips the hook, as a
    # row loaded outside the ORM would have it.
    instance_data["title"] = {
        "@type": "Title",
        "mainTitle": {"@value": "Pride and prejudice", "@language": "en_US"},
    }
    db_session.execute(
        sqlalchemy.update(ResourceBase.__table__)
        .where(ResourceBase.__table__.c.uri == INSTANCE_URI)
        .values(data=instance_data)
    )
    db_session.commit()
    db_session.expire_all()

    expanded = _graph(client, f"/works/{WORK_UUID}?expand=true")
    assert _labels(expanded, INSTANCE_URI) == [Literal("Pride and prejudice")]


def test_untitled_instance_gets_no_label(client, db_session):
    _add_pair(db_session)

    expanded = _graph(client, f"/works/{WORK_UUID}?expand=true")
    assert _labels(expanded, INSTANCE_URI) == []


def test_main_title_chosen_over_variant(client, db_session):
    _add_pair(
        db_session,
        work_title=[
            {"@type": "VariantTitle", "mainTitle": "First impressions"},
            {"@type": "Title", "mainTitle": "Pride and prejudice"},
        ],
    )

    expanded = _graph(client, f"/instances/{INSTANCE_UUID}?expand=true")
    assert _labels(expanded, WORK_URI) == [Literal("Pride and prejudice")]


def test_variant_title_is_the_fallback(client, db_session):
    _add_pair(
        db_session,
        work_title={"@type": "VariantTitle", "mainTitle": "First impressions"},
    )

    expanded = _graph(client, f"/instances/{INSTANCE_UUID}?expand=true")
    assert _labels(expanded, WORK_URI) == [Literal("First impressions")]


def test_turtle_expand_labels_linked_work(client, db_session):
    _add_pair(db_session, work_title={"@type": "Title", "mainTitle": "Emma"})

    response = client.get(
        f"/instances/{INSTANCE_UUID}?expand=true", headers={"Accept": "text/turtle"}
    )
    assert response.status_code == 200
    graph = rdflib.Graph().parse(data=response.text, format="turtle")
    assert _labels(graph, WORK_URI) == [Literal("Emma")]
