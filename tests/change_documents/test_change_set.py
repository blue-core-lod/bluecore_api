from __future__ import annotations
from bluecore_models.models import Work, Instance
from bluecore_api.change_documents.change_set import (
    ChangeSet,
)
from bluecore_api.constants import BibframeType, BluecoreType
from bluecore_api.schemas.change_documents.schemas import (
    ChangeSetSchema,
)

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
import pytest


TEST_PAGE_LENGTH = 2
HOST = "http://127.0.0.1:3000"


def add_works(db: Session, start_index: int) -> None:
    for i in (1, 2, 3, 4):
        uri = f"https://bc_test.org/works/{i + start_index}"
        db.add(
            Work(
                id=i + start_index,
                uri=uri,
                data={
                    "@id": uri,
                    "@type": "Work",
                    "title": f"jon_works_{i + start_index}",
                },
            ),
        )
    db.commit()


def update_works(db: Session, start_index: int) -> None:
    for i in (1, 2):
        index = i + start_index
        work = db.query(Work).filter(Work.id == index).first()
        # using the ** splat here preserves the existing @id and @type
        work.data = {**work.data, "title": f"jon_works_{index}_update"}
    db.commit()


def add_instances(db: Session) -> None:
    works = db.query(Work).all()
    instance_id = 1
    for work in works:
        uri = f"https://bc_test.org/instances/{instance_id}"
        db.add(
            Instance(
                uri=uri,
                work_id=work.id,
                data={
                    "@id": uri,
                    "@type": "Instance",
                    "title": f"jon_instances_{work.id}",
                },
            )
        )
        instance_id += 1
    db.commit()


def update_instances(db: Session) -> None:
    instances = db.query(Instance).all()
    for instance in instances:
        # using the ** splat here preserves the existing @id and @type
        instance.data = {
            **instance.data,
            "title": f"jon_instances_{instance.id}_update",
        }

    db.commit()


def test_work_change_set_add(client: TestClient, db_session: Session) -> None:
    # Adds 4 works
    add_works(db_session, start_index=0)

    page_id = 1
    change_set = ChangeSet(
        db=db_session,
        bc_type=BluecoreType.WORKS,
        id=page_id,
        host=HOST,
        page_length=TEST_PAGE_LENGTH,
    )
    assert change_set.totalItems == 2
    assert change_set.prev is None
    assert (
        change_set.next
        == f"http://127.0.0.1:3000/change_documents/works/page/{page_id + 1}"
    )
    assert change_set.orderedItems[0].type == "Create"
    assert change_set.orderedItems[0].object.type == f"bf:{BibframeType.WORK}"

    response = client.get(f"/change_documents/works/page/{page_id}")
    assert response.status_code == 200
    as_schema = ChangeSetSchema.model_validate(change_set)
    assert ChangeSetSchema(**response.json()) == as_schema


def test_work_entry_point_update(client: TestClient, db_session: Session) -> None:
    # Adds 4 works
    add_works(db_session, start_index=20)
    # Updates 2 works
    update_works(db_session, start_index=20)

    page_id = 3
    change_set = ChangeSet(
        db=db_session,
        bc_type=BluecoreType.WORKS,
        id=page_id,
        host=HOST,
        page_length=TEST_PAGE_LENGTH,
    )
    assert change_set.totalItems == 2
    assert (
        change_set.prev
        == f"http://127.0.0.1:3000/change_documents/works/page/{page_id - 1}"
    )
    assert change_set.next is None
    assert change_set.orderedItems[0].type == "Update"
    assert change_set.orderedItems[0].object.type == f"bf:{BibframeType.WORK}"


def test_instance_entry_point_add(client: TestClient, db_session: Session) -> None:
    # Adds 4 works
    add_works(db_session, start_index=40)
    # Adds 4 instances
    add_instances(db_session)

    page_id = 2
    change_set = ChangeSet(
        db=db_session,
        bc_type=BluecoreType.INSTANCES,
        id=page_id,
        host=HOST,
        page_length=TEST_PAGE_LENGTH,
    )
    assert change_set.totalItems == 2
    assert (
        change_set.prev
        == f"http://127.0.0.1:3000/change_documents/instances/page/{page_id - 1}"
    )
    assert change_set.next is None
    assert change_set.orderedItems[0].type == "Create"
    assert change_set.orderedItems[0].object.type == f"bf:{BibframeType.INSTANCE}"


def test_instance_entry_point_update(client: TestClient, db_session: Session) -> None:
    # Adds 4 works
    add_works(db_session, start_index=60)
    # Adds 4 instances
    add_instances(db_session)
    # Updates 4 instances
    update_instances(db_session)

    change_set = ChangeSet(
        db=db_session,
        bc_type=BluecoreType.INSTANCES,
        id=1,
        host=HOST,
        page_length=TEST_PAGE_LENGTH,
    )
    assert change_set.orderedItems[0].type == "Create"
    assert change_set.orderedItems[0].object.type == f"bf:{BibframeType.INSTANCE}"

    page_id = 3
    change_set = ChangeSet(
        db=db_session,
        bc_type=BluecoreType.INSTANCES,
        id=page_id,
        host=HOST,
        page_length=TEST_PAGE_LENGTH,
    )
    assert change_set.totalItems == 2
    assert (
        change_set.prev
        == f"http://127.0.0.1:3000/change_documents/instances/page/{page_id - 1}"
    )
    assert (
        change_set.next
        == f"http://127.0.0.1:3000/change_documents/instances/page/{page_id + 1}"
    )

    assert change_set.orderedItems[0].type == "Update"
    assert change_set.orderedItems[0].object.type == f"bf:{BibframeType.INSTANCE}"

    response = client.get(f"/change_documents/instances/page/{page_id}")
    assert response.status_code == 200
    as_schema = ChangeSetSchema.model_validate(change_set)
    assert ChangeSetSchema(**response.json()) == as_schema


if __name__ == "__main__":
    pytest.main()
