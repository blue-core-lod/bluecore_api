from __future__ import annotations
from bluecore.app.change_notifications.activity_streams import ActivityStreamsGenerator
from bluecore.app.resource_manager.resource_manager import ResourceManager
from bluecore.app.main import app, get_db
from bluecore.schemas import (
    WorkCreateSchema,
    WorkUpdateSchema,
)
from bluecore_models.models import (
    Base,
    BibframeClass,
    Instance,
    ResourceBase,
    ResourceBibframeClass,
    Version,
    Work,
)
from bluecore.utils.constants import BCType
from fastapi.testclient import TestClient
from pytest_mock_resources import create_postgres_fixture
from sqlalchemy.orm import Session
import json
import pytest


db_session: Session = create_postgres_fixture(session=True)


@pytest.fixture
def client(db_session: Session) -> TestClient:
    Base.metadata.create_all(
        bind=db_session.get_bind(),
        tables=[
            ResourceBase.__table__,
            BibframeClass.__table__,
            Instance.__table__,
            ResourceBibframeClass.__table__,
            Version.__table__,
            Work.__table__,
        ],
    )

    def override_get_db():
        db = db_session
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as c:
        yield c

    Base.metadata.drop_all(bind=db_session.get_bind())


def add_works_instances(db: Session) -> None:
    resource_manager = ResourceManager()
    for i in (1, 2, 3, 4):
        data = {"name": f"jon_{i}"}
        resource_manager.create_work(
            work=WorkCreateSchema(
                data=json.dumps(data), uri=f"https://bc_test.org/work/{i}"
            ),
            db=db,
        )


def update_works_instances(db: Session) -> None:
    resource_manager = ResourceManager()
    for i in (1, 2):
        data = {"name": f"jon_update_{i}"}
        resource_manager.update_work(
            work_id=i,
            work=WorkUpdateSchema(data=json.dumps(data)),
            db=db,
        )


TEST_PAGE_LENGTH = 2


@pytest.mark.run(order=1)
def test_determine_create_update() -> None:
    activity_streams_generator = ActivityStreamsGenerator(page_length=TEST_PAGE_LENGTH)

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
        assert (
            result == date["type"]
        ), f"Test case {date['label']}: expected {date['type']} but got {result}"


@pytest.mark.run(order=2)
def test_work_activity_streams_add(client: TestClient, db_session: Session) -> None:
    add_works_instances(db_session)
    activity_streams_generator = ActivityStreamsGenerator(page_length=TEST_PAGE_LENGTH)

    # OrderedCollection
    # first must be 1
    # last must be 2
    feed = activity_streams_generator.activity_streams_feed(
        db=db_session, bc_type=BCType.WORKS
    )
    assert (
        feed["id"]
        == "http://127.0.0.1:3000/change_documents/works/activitystreams/feed"
    )
    assert feed["type"] == "OrderedCollection"
    assert feed["first"]["type"] == "OrderedCollectionPage"
    assert (
        feed["first"]["id"]
        == "http://127.0.0.1:3000/change_documents/works/activitystreams/page/1"
    )
    assert feed["last"]["type"] == "OrderedCollectionPage"
    assert (
        feed["last"]["id"]
        == "http://127.0.0.1:3000/change_documents/works/activitystreams/page/2"
    )
    assert feed["totalItems"] == 4

    response = client.get("/change_documents/works/activitystreams/feed")
    assert response.status_code == 200
    assert response.json() == feed

    # Page 1
    # prev must be None
    # next must be 2
    # all objects must be Create
    page = activity_streams_generator.activity_streams_page(
        id=1,
        db=db_session,
        bc_type=BCType.WORKS,
    )
    assert page["type"] == "OrderedCollectionPage"
    assert (
        page["id"]
        == "http://127.0.0.1:3000/change_documents/works/activitystreams/page/1"
    )
    assert (
        page["partOf"]
        == "http://127.0.0.1:3000/change_documents/works/activitystreams/feed"
    )
    assert page["totalItems"] == 2
    assert len(page["orderedItems"]) == 2
    assert page["prev"] is None
    assert (
        page["next"]
        == "http://127.0.0.1:3000/change_documents/works/activitystreams/page/2"
    )
    # ordered_items = page["orderedItems"]
    # for i in (0, 1):
    #     assert (
    #         ordered_items[i]["type"] == "Create"
    #     ), f"Test type of ordered item {i}: expected Created but got {ordered_items[i]["type"]}"
    #     assert (
    #         ordered_items[i]["object"]["id"] == f"http://127.0.0.1:3000/works/{i+1}"
    #     ), f"Test id of object {i}: expected http://127.0.0.1:3000/works/{i+1} but got {ordered_items[i]["object"]["id"]}"
    #     assert (
    #         ordered_items[i]["object"]["type"] == "bf:{BFType.WORK}"
    #     ), f"Test type of object {i}: expected bf:{BFType.WORK} but got {ordered_items[i]["object"]["type"]}"

    # response = client.get(
    #     "/change_documents/works/activitystreams/page/1",
    # )
    # assert response.status_code == 200
    # assert response.json() == page

    # Page 2
    # prev must be 1, and next must be None
    page = activity_streams_generator.activity_streams_page(
        id=2,
        db=db_session,
        bc_type=BCType.WORKS,
    )
    assert (
        page["id"]
        == "http://127.0.0.1:3000/change_documents/works/activitystreams/page/2"
    )
    assert (
        page["prev"]
        == "http://127.0.0.1:3000/change_documents/works/activitystreams/page/1"
    )
    assert page["next"] is None

    breakpoint()


#     response = client.get(
#         "/change_documents/works/activitystreams/page/2",
#     )
#     assert response.status_code == 200
#     assert response.json() == page


# @pytest.mark.run(order=3)
# def test_work_activity_streams_update(client: TestClient, db_session: Session) -> None:
#     update_works_instances(db_session)
#     activity_streams_generator = ActivityStreamsGenerator(page_length=TEST_PAGE_LENGTH)

#     # OrderedCollection
#     # first must be 1
#     # last must be 3
#     feed = activity_streams_generator.activity_streams_feed(
#         db=db_session, bc_type=BCType.WORKS
#     )
#     assert (
#         feed["id"]
#         == "http://127.0.0.1:3000/change_documents/works/activitystreams/feed"
#     )
#     assert feed["type"] == "OrderedCollection"
#     assert feed["first"]["type"] == "OrderedCollectionPage"
#     assert (
#         feed["first"]["id"]
#         == "http://127.0.0.1:3000/change_documents/works/activitystreams/page/1"
#     )
#     assert feed["last"]["type"] == "OrderedCollectionPage"
#     assert (
#         feed["last"]["id"]
#         == "http://127.0.0.1:3000/change_documents/works/activitystreams/page/3"
#     )
#     assert feed["totalItems"] == 6

#     response = client.get("/change_documents/works/activitystreams/feed")
#     assert response.status_code == 200
#     assert response.json() == feed

#     # Page 3
#     # prev must be 2
#     # next must be None
#     # all objects must be Update
#     page = activity_streams_generator.activity_streams_page(
#         id=3,
#         db=db_session,
#         bc_type=BCType.WORKS,
#     )
#     assert page["type"] == "OrderedCollectionPage"
#     assert (
#         page["id"]
#         == "http://127.0.0.1:3000/change_documents/works/activitystreams/page/3"
#     )
#     assert page["totalItems"] == 2
#     assert len(page["orderedItems"]) == 2
#     assert (
#         page["prev"]
#         == "http://127.0.0.1:3000/change_documents/works/activitystreams/page/2"
#     )
#     assert page["next"] is None
#     ordered_items = page["orderedItems"]

#     for i in (0, 1):
#         assert ordered_items[i]["type"] == "Update"
#         assert ordered_items[i]["object"]["id"] == f"http://127.0.0.1:3000/works/{i+1}"

#     response = client.get(
#         "/change_documents/works/activitystreams/page/3",
#     )
#     assert response.status_code == 200
#     assert response.json() == page
