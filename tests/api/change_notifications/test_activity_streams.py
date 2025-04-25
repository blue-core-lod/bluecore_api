from __future__ import annotations
from bluecore.app.change_notifications.activity_streams import ActivityStreamsGenerator
from bluecore.app.resource_manager.resource_manager import ResourceManager
from bluecore.schemas import (
    ActivityStreamsChangeSetSchema,
    ActivityStreamsEntryPointSchema,
    InstanceCreateSchema,
    InstanceUpdateSchema,
    WorkCreateSchema,
    WorkUpdateSchema,
)
from bluecore.utils.constants import BCType, BFType
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from typing import Any, Dict, List
import json
import pytest


TEST_PAGE_LENGTH = 2


def get_test_activity_streams_generator() -> ActivityStreamsGenerator:
    return ActivityStreamsGenerator(page_length=TEST_PAGE_LENGTH)


def add_works(db: Session) -> None:
    resource_manager = ResourceManager()
    for i in (1, 2, 3, 4):
        data = {"name": f"jon_{i}"}
        resource_manager.create_work(
            work=WorkCreateSchema(
                data=json.dumps(data), uri=f"https://bc_test.org/work/{i}"
            ),
            db=db,
        )


def update_works(db: Session) -> None:
    resource_manager = ResourceManager()
    for i in (1, 2):
        data = {"name": f"jon_update_{i}"}
        resource_manager.update_work(
            work_id=i,
            work=WorkUpdateSchema(data=json.dumps(data)),
            db=db,
        )


def add_instances(db: Session) -> None:
    resource_manager = ResourceManager()
    for i in (1, 2, 3, 4):
        data = {"name": f"jon_work_{i}"}
        work = resource_manager.create_work(
            work=WorkCreateSchema(
                data=json.dumps(data), uri=f"https://bc_test.org/work/{i}"
            ),
            db=db,
        )
        data = {"name": f"jon_instance_{i}"}
        resource_manager.create_instance(
            instance=InstanceCreateSchema(
                work_id=work.id,
                data=json.dumps(data),
                uri=f"https://bc_test.org/instance/{i}",
            ),
            db=db,
        )


def update_instances(db: Session) -> None:
    resource_manager = ResourceManager()
    for i in (1, 2):
        data = {"name": f"jon_instance_update_{i}"}
        resource_manager.update_instance(
            instance_id=i * 2,
            instance=InstanceUpdateSchema(data=json.dumps(data)),
            db=db,
        )


def test_determine_create_update() -> None:
    activity_streams_generator = get_test_activity_streams_generator()

    dates = [
        {
            "label": "Create 1",
            "version_created_at": "2025-04-24 11:10:15.288511",
            "resource_created_at": "2025-04-24 11:10:15.288507",
            "resource_updated_at": "2025-04-24 11:10:55.715032",
            "type": "Create",
        },
        {
            "label": "Create 2",
            "version_created_at": "2025-04-24 11:10:18.206634",
            "resource_created_at": "2025-04-24 11:10:18.206621",
            "resource_updated_at": "2025-04-24 11:10:42.547386",
            "type": "Create",
        },
        {
            "label": "Create 3",
            "version_created_at": "2025-04-24 11:10:21.939639",
            "resource_created_at": "2025-04-24 11:10:21.939627",
            "resource_updated_at": "2025-04-24 11:10:21.939639",
            "type": "Create",
        },
        {
            "label": "Create 4",
            "version_created_at": "2025-04-24 11:10:24.561125",
            "resource_created_at": "2025-04-24 11:10:24.561114",
            "resource_updated_at": "2025-04-24 11:10:24.561125",
            "type": "Create",
        },
        {
            "label": "Update 1",
            "version_created_at": "2025-04-24 11:10:30.38912",
            "resource_created_at": "2025-04-24 11:10:15.288507",
            "resource_updated_at": "2025-04-24 11:10:55.715032",
            "type": "Update",
        },
        {
            "label": "Create 5",
            "version_created_at": "2025-04-24 11:10:37.13989",
            "resource_created_at": "2025-04-24 11:10:37.139877",
            "resource_updated_at": "2025-04-24 11:10:37.13989",
            "type": "Create",
        },
        {
            "label": "Update 2",
            "version_created_at": "2025-04-24 11:10:42.547386",
            "resource_created_at": "2025-04-24 11:10:18.206621",
            "resource_updated_at": "2025-04-24 11:10:42.547386",
            "type": "Update",
        },
        {
            "label": "Update 1 again",
            "version_created_at": "2025-04-24 11:10:55.715032",
            "resource_created_at": "2025-04-24 11:10:15.288507",
            "resource_updated_at": "2025-04-24 11:10:55.715032",
            "type": "Update",
        },
    ]

    for date in dates:
        result = activity_streams_generator.determine_create_update(
            resource_created_at=date["resource_created_at"],
            resource_updated_at=date["resource_updated_at"],
            version_created_at=date["version_created_at"],
        )
        assert result == date["type"], (
            f"Test case {date['label']}: expected {date['type']} but got {result}"
        )


def feed_test(feed: ActivityStreamsEntryPointSchema, expected: Dict[str, Any]) -> None:
    assert feed.id == expected["id"], (
        f"{expected['label']} id: {expected['id']} but got {feed.id}"
    )
    assert feed.type == "OrderedCollection", (
        f"{expected['label']} type: {expected['type']} but got {feed.type}"
    )
    assert feed.first["type"] == "OrderedCollectionPage", (
        f"{expected['label']} first type: {expected['first']['type']} but got {feed.first['type']}"
    )
    assert feed.first["id"] == expected["first"]["id"], (
        f"{expected['label']} first id: {expected['first']['id']} but got {feed.first['id']}"
    )
    assert feed.last["type"] == "OrderedCollectionPage", (
        f"{expected['label']} last type: {expected['last']['type']} but got {feed.last['type']}"
    )
    assert feed.last["id"] == expected["last"]["id"], (
        f"{expected['label']} last id: {expected['last']['id']} but got {feed.last['id']}"
    )
    assert feed.totalItems == expected["totalItems"], (
        f"{expected['label']} totalItems: {expected['totalItems']} but got {feed.totalItems}"
    )


def page_test(page: ActivityStreamsChangeSetSchema, expected: Dict[str, Any]) -> None:
    assert page.type == "OrderedCollectionPage", (
        f"Test page {expected['label']}: expected OrderedCollectionPage but got {page.type}"
    )

    assert page.id == expected["id"], (
        f"Test page {expected['label']}: id: expected {expected['id']} but got {page.id}"
    )
    assert page.partOf == expected["partOf"], (
        f"Test page {expected['label']}: partOf: expected {expected['partOf']} but got {page.partOf}"
    )
    assert page.totalItems == expected["totalItems"], (
        f"Test page {expected['label']}: totalItems: expected {expected['totalItems']} but got {page.totalItems}"
    )
    assert len(page.orderedItems) == len(expected["orderedItems"]), (
        f"Test page {expected['label']}: length of orderedItems: expected {len(expected['orderedItems'])} but got {len(page.orderedItems)}"
    )
    assert page.prev == expected["prev"], (
        f"Test page {expected['label']}: prev: expected {expected['prev']} but got {page.prev}"
    )
    assert page.next == expected["next"], (
        f"Test page {expected['label']}: next: expected {expected['next']} but got {page.next}"
    )
    for ordered_items, expected_ordered_items in zip(
        page.orderedItems, expected["orderedItems"]
    ):
        assert ordered_items.type == expected_ordered_items["type"], (
            f"Test page {expected['label']}: type of ordered item: expected {expected_ordered_items['type']} but got {ordered_items.type}"
        )
        assert ordered_items.object.id == expected_ordered_items["object"]["id"], (
            f"Test page {expected['label']}: id of object: expected {expected_ordered_items['object']['id']} but got {ordered_items.object.id}"
        )
        assert ordered_items.object.type == expected_ordered_items["object"]["type"], (
            f"Test page {expected['label']}: type of object: expected {expected_ordered_items['object']['type']} but got {ordered_items.object.type}"
        )


def test_work_activity_streams_add(client: TestClient, db_session: Session) -> None:
    # Adds 4 works
    add_works(db_session)
    activity_streams_generator = get_test_activity_streams_generator()

    expected_feed_values: Dict[str, Any] = {
        "label": "Initial feed",
        "id": "http://127.0.0.1:3000/change_documents/works/activitystreams/feed",
        "type": "OrderedCollection",
        "first": {
            "type": "OrderedCollectionPage",
            "id": "http://127.0.0.1:3000/change_documents/works/activitystreams/page/1",
        },
        "last": {
            "type": "OrderedCollectionPage",
            "id": "http://127.0.0.1:3000/change_documents/works/activitystreams/page/2",
        },
        "totalItems": 4,
    }

    feed = activity_streams_generator.activity_streams_feed(
        db=db_session, bc_type=BCType.WORKS
    )
    feed_test(
        feed=feed,
        expected=expected_feed_values,
    )

    response = client.get("/change_documents/works/activitystreams/feed")
    assert response.status_code == 200
    # assert response.json() == feed

    expected_page_values: List[Dict[str, Any]] = [
        {
            "label": "Initial page 1",
            "page": 1,
            "id": "http://127.0.0.1:3000/change_documents/works/activitystreams/page/1",
            "partOf": "http://127.0.0.1:3000/change_documents/works/activitystreams/feed",
            "prev": None,
            "next": "http://127.0.0.1:3000/change_documents/works/activitystreams/page/2",
            "totalItems": 2,
            "orderedItems": [
                {
                    "type": "Create",
                    "object": {
                        "id": "https://bc_test.org/work/1",
                        "type": f"bf:{BFType.WORK}",
                    },
                },
                {
                    "type": "Create",
                    "object": {
                        "id": "https://bc_test.org/work/2",
                        "type": f"bf:{BFType.WORK}",
                    },
                },
            ],
        },
        {
            "label": "Initial page 2",
            "page": 2,
            "id": "http://127.0.0.1:3000/change_documents/works/activitystreams/page/2",
            "partOf": "http://127.0.0.1:3000/change_documents/works/activitystreams/feed",
            "prev": "http://127.0.0.1:3000/change_documents/works/activitystreams/page/1",
            "next": None,
            "totalItems": 2,
            "orderedItems": [
                {
                    "type": "Create",
                    "object": {
                        "id": "https://bc_test.org/work/3",
                        "type": f"bf:{BFType.WORK}",
                    },
                },
                {
                    "type": "Create",
                    "object": {
                        "id": "https://bc_test.org/work/4",
                        "type": f"bf:{BFType.WORK}",
                    },
                },
            ],
        },
    ]
    for expected in expected_page_values:
        page = activity_streams_generator.activity_streams_page(
            id=expected["page"],
            db=db_session,
            bc_type=BCType.WORKS,
        )
        page_test(
            page=page,
            expected=expected,
        )

        response = client.get(
            f"/change_documents/works/activitystreams/page/{expected['page']}",
        )
        assert response.status_code == 200
        # assert response.json() == page


def test_work_activity_streams_update(client: TestClient, db_session: Session) -> None:
    # Adds 4 works
    add_works(db_session)
    # Updates 2 works
    update_works(db_session)
    activity_streams_generator = ActivityStreamsGenerator(page_length=TEST_PAGE_LENGTH)

    expected_feed_values: Dict[str, Any] = {
        "label": "Update feed",
        "id": "http://127.0.0.1:3000/change_documents/works/activitystreams/feed",
        "type": "OrderedCollection",
        "first": {
            "type": "OrderedCollectionPage",
            "id": "http://127.0.0.1:3000/change_documents/works/activitystreams/page/1",
        },
        "last": {
            "type": "OrderedCollectionPage",
            "id": "http://127.0.0.1:3000/change_documents/works/activitystreams/page/3",
        },
        "totalItems": 6,
    }

    feed = activity_streams_generator.activity_streams_feed(
        db=db_session, bc_type=BCType.WORKS
    )
    feed_test(
        feed=feed,
        expected=expected_feed_values,
    )

    response = client.get("/change_documents/works/activitystreams/feed")
    assert response.status_code == 200
    # assert response.json() == feed

    expected_page_values: List[Dict[str, Any]] = [
        {
            "label": "Update page 1",
            "page": 1,
            "id": "http://127.0.0.1:3000/change_documents/works/activitystreams/page/1",
            "partOf": "http://127.0.0.1:3000/change_documents/works/activitystreams/feed",
            "prev": None,
            "next": "http://127.0.0.1:3000/change_documents/works/activitystreams/page/2",
            "totalItems": 2,
            "orderedItems": [
                {
                    "type": "Create",
                    "object": {
                        "id": "https://bc_test.org/work/1",
                        "type": f"bf:{BFType.WORK}",
                    },
                },
                {
                    "type": "Create",
                    "object": {
                        "id": "https://bc_test.org/work/2",
                        "type": f"bf:{BFType.WORK}",
                    },
                },
            ],
        },
        {
            "label": "Update page 2",
            "page": 2,
            "id": "http://127.0.0.1:3000/change_documents/works/activitystreams/page/2",
            "partOf": "http://127.0.0.1:3000/change_documents/works/activitystreams/feed",
            "prev": "http://127.0.0.1:3000/change_documents/works/activitystreams/page/1",
            "next": "http://127.0.0.1:3000/change_documents/works/activitystreams/page/3",
            "totalItems": 2,
            "orderedItems": [
                {
                    "type": "Create",
                    "object": {
                        "id": "https://bc_test.org/work/3",
                        "type": f"bf:{BFType.WORK}",
                    },
                },
                {
                    "type": "Create",
                    "object": {
                        "id": "https://bc_test.org/work/4",
                        "type": f"bf:{BFType.WORK}",
                    },
                },
            ],
        },
        {
            "label": "Update page 3",
            "page": 3,
            "id": "http://127.0.0.1:3000/change_documents/works/activitystreams/page/3",
            "partOf": "http://127.0.0.1:3000/change_documents/works/activitystreams/feed",
            "prev": "http://127.0.0.1:3000/change_documents/works/activitystreams/page/2",
            "next": None,
            "totalItems": 2,
            "orderedItems": [
                {
                    "type": "Update",
                    "object": {
                        "id": "https://bc_test.org/work/1",
                        "type": f"bf:{BFType.WORK}",
                    },
                },
                {
                    "type": "Update",
                    "object": {
                        "id": "https://bc_test.org/work/2",
                        "type": f"bf:{BFType.WORK}",
                    },
                },
            ],
        },
    ]
    for expected in expected_page_values:
        page = activity_streams_generator.activity_streams_page(
            id=expected["page"],
            db=db_session,
            bc_type=BCType.WORKS,
        )
        page_test(
            page=page,
            expected=expected,
        )

        response = client.get(
            f"/change_documents/works/activitystreams/page/{expected['page']}",
        )
        assert response.status_code == 200
        # assert response.json() == page


def test_instance_activity_streams_add(client: TestClient, db_session: Session) -> None:
    # Adds 4 instances
    add_instances(db_session)
    activity_streams_generator = get_test_activity_streams_generator()

    expected_feed_values: Dict[str, Any] = {
        "label": "Initial feed",
        "id": "http://127.0.0.1:3000/change_documents/instances/activitystreams/feed",
        "type": "OrderedCollection",
        "first": {
            "type": "OrderedCollectionPage",
            "id": "http://127.0.0.1:3000/change_documents/instances/activitystreams/page/1",
        },
        "last": {
            "type": "OrderedCollectionPage",
            "id": "http://127.0.0.1:3000/change_documents/instances/activitystreams/page/2",
        },
        "totalItems": 4,
    }

    feed = activity_streams_generator.activity_streams_feed(
        db=db_session, bc_type=BCType.INSTANCES
    )
    feed_test(
        feed=feed,
        expected=expected_feed_values,
    )

    response = client.get("/change_documents/instances/activitystreams/feed")
    assert response.status_code == 200
    # assert response.json() == feed

    expected_page_values: List[Dict[str, Any]] = [
        {
            "label": "Initial page 1",
            "page": 1,
            "id": "http://127.0.0.1:3000/change_documents/instances/activitystreams/page/1",
            "partOf": "http://127.0.0.1:3000/change_documents/instances/activitystreams/feed",
            "prev": None,
            "next": "http://127.0.0.1:3000/change_documents/instances/activitystreams/page/2",
            "totalItems": 2,
            "orderedItems": [
                {
                    "type": "Create",
                    "object": {
                        "id": "https://bc_test.org/instance/1",
                        "type": f"bf:{BFType.INSTANCE}",
                    },
                },
                {
                    "type": "Create",
                    "object": {
                        "id": "https://bc_test.org/instance/2",
                        "type": f"bf:{BFType.INSTANCE}",
                    },
                },
            ],
        },
        {
            "label": "Initial page 2",
            "page": 2,
            "id": "http://127.0.0.1:3000/change_documents/instances/activitystreams/page/2",
            "partOf": "http://127.0.0.1:3000/change_documents/instances/activitystreams/feed",
            "prev": "http://127.0.0.1:3000/change_documents/instances/activitystreams/page/1",
            "next": None,
            "totalItems": 2,
            "orderedItems": [
                {
                    "type": "Create",
                    "object": {
                        "id": "https://bc_test.org/instance/3",
                        "type": f"bf:{BFType.INSTANCE}",
                    },
                },
                {
                    "type": "Create",
                    "object": {
                        "id": "https://bc_test.org/instance/4",
                        "type": f"bf:{BFType.INSTANCE}",
                    },
                },
            ],
        },
    ]
    for expected in expected_page_values:
        page = activity_streams_generator.activity_streams_page(
            id=expected["page"],
            db=db_session,
            bc_type=BCType.INSTANCES,
        )
        page_test(
            page=page,
            expected=expected,
        )

        response = client.get(
            f"/change_documents/instances/activitystreams/page/{expected['page']}",
        )
        assert response.status_code == 200
        # assert response.json() == page


def test_instance_activity_streams_update(
    client: TestClient, db_session: Session
) -> None:
    # Adds 4 works
    add_instances(db_session)
    # Updates 2 works
    update_instances(db_session)
    activity_streams_generator = ActivityStreamsGenerator(page_length=TEST_PAGE_LENGTH)

    expected_feed_values: Dict[str, Any] = {
        "label": "Initial feed",
        "id": "http://127.0.0.1:3000/change_documents/instances/activitystreams/feed",
        "type": "OrderedCollection",
        "first": {
            "type": "OrderedCollectionPage",
            "id": "http://127.0.0.1:3000/change_documents/instances/activitystreams/page/1",
        },
        "last": {
            "type": "OrderedCollectionPage",
            "id": "http://127.0.0.1:3000/change_documents/instances/activitystreams/page/3",
        },
        "totalItems": 6,
    }

    feed = activity_streams_generator.activity_streams_feed(
        db=db_session, bc_type=BCType.INSTANCES
    )
    feed_test(
        feed=feed,
        expected=expected_feed_values,
    )

    response = client.get("/change_documents/instances/activitystreams/feed")
    assert response.status_code == 200
    # assert response.json() == feed

    expected_page_values: List[Dict[str, Any]] = [
        {
            "label": "Update page 1",
            "page": 1,
            "id": "http://127.0.0.1:3000/change_documents/instances/activitystreams/page/1",
            "partOf": "http://127.0.0.1:3000/change_documents/instances/activitystreams/feed",
            "prev": None,
            "next": "http://127.0.0.1:3000/change_documents/instances/activitystreams/page/2",
            "totalItems": 2,
            "orderedItems": [
                {
                    "type": "Create",
                    "object": {
                        "id": "https://bc_test.org/instance/1",
                        "type": f"bf:{BFType.INSTANCE}",
                    },
                },
                {
                    "type": "Create",
                    "object": {
                        "id": "https://bc_test.org/instance/2",
                        "type": f"bf:{BFType.INSTANCE}",
                    },
                },
            ],
        },
        {
            "label": "Update page 2",
            "page": 2,
            "id": "http://127.0.0.1:3000/change_documents/instances/activitystreams/page/2",
            "partOf": "http://127.0.0.1:3000/change_documents/instances/activitystreams/feed",
            "prev": "http://127.0.0.1:3000/change_documents/instances/activitystreams/page/1",
            "next": "http://127.0.0.1:3000/change_documents/instances/activitystreams/page/3",
            "totalItems": 2,
            "orderedItems": [
                {
                    "type": "Create",
                    "object": {
                        "id": "https://bc_test.org/instance/3",
                        "type": f"bf:{BFType.INSTANCE}",
                    },
                },
                {
                    "type": "Create",
                    "object": {
                        "id": "https://bc_test.org/instance/4",
                        "type": f"bf:{BFType.INSTANCE}",
                    },
                },
            ],
        },
        {
            "label": "Update page 3",
            "page": 3,
            "id": "http://127.0.0.1:3000/change_documents/instances/activitystreams/page/3",
            "partOf": "http://127.0.0.1:3000/change_documents/instances/activitystreams/feed",
            "prev": "http://127.0.0.1:3000/change_documents/instances/activitystreams/page/2",
            "next": None,
            "totalItems": 2,
            "orderedItems": [
                {
                    "type": "Update",
                    "object": {
                        "id": "https://bc_test.org/instance/1",
                        "type": f"bf:{BFType.INSTANCE}",
                    },
                },
                {
                    "type": "Update",
                    "object": {
                        "id": "https://bc_test.org/instance/2",
                        "type": f"bf:{BFType.INSTANCE}",
                    },
                },
            ],
        },
    ]
    for expected in expected_page_values:
        page = activity_streams_generator.activity_streams_page(
            id=expected["page"],
            db=db_session,
            bc_type=BCType.INSTANCES,
        )
        page_test(
            page=page,
            expected=expected,
        )

        response = client.get(
            f"/change_documents/instances/activitystreams/page/{expected['page']}",
        )
        assert response.status_code == 200
        # assert response.json() == page


if __name__ == "__main__":
    pytest.main()
