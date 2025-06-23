from __future__ import annotations
from bluecore_models.models import Work, Instance
from bluecore_api.change_documents.entry_point import (
    EntryPoint,
)
from bluecore_api.constants import BluecoreType
from bluecore_api.schemas.change_documents.schemas import (
    EntryPointSchema,
)

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
import json
import pytest


TEST_PAGE_LENGTH = 2
HOST = "http://127.0.0.1:3000"


def add_works(db: Session, start_index: int) -> None:
    for i in (1, 2, 3, 4):
        data = {"name": f"jon_works_{i + start_index}"}
        db.add(
            Work(
                id=i + start_index,
                uri=f"https://bc_test.org/works/{i + start_index}",
                data=json.dumps(data),
            ),
        )
    db.commit()


def update_works(db: Session, start_index: int) -> None:
    for i in (1, 2):
        index = i + start_index
        work = db.query(Work).filter(Work.id == index).first()
        work.data = json.dumps({"name": f"jon_works_{index}_update"})
    db.commit()


def add_instances(db: Session) -> None:
    works = db.query(Work).all()
    instance_id = 1
    for work in works:
        data = {"name": f"jon_instances_{work.id}"}
        db.add(
            Instance(
                work_id=work.id,
                data=json.dumps(data),
                uri=f"https://bc_test.org/instances/{instance_id}",
            )
        )
        instance_id += 1
    db.commit()


def update_instances(db: Session) -> None:
    instances = db.query(Instance).all()
    for instance in instances:
        instance.data = json.dumps({"name": f"jon_instances_{instance.id}_update"})
    db.commit()


def test_work_entry_point_add(client: TestClient, db_session: Session) -> None:
    # Adds 4 works
    add_works(db_session, start_index=0)

    entry_point = EntryPoint(
        db=db_session,
        bc_type=BluecoreType.WORKS,
        host=HOST,
        page_length=TEST_PAGE_LENGTH,
    )
    assert entry_point.totalItems == 4
    assert (
        entry_point.last["id"] == "http://127.0.0.1:3000/change_documents/works/page/2"
    )

    response = client.get("/change_documents/works/feed")
    assert response.status_code == 200
    as_schema = EntryPointSchema.model_validate(entry_point)
    assert EntryPointSchema(**response.json()) == as_schema


def test_work_entry_point_update(client: TestClient, db_session: Session) -> None:
    # Adds 4 works
    add_works(db_session, start_index=20)
    # Updates 2 works
    update_works(db_session, start_index=20)

    entry_point = EntryPoint(
        db=db_session,
        bc_type=BluecoreType.WORKS,
        host=HOST,
        page_length=TEST_PAGE_LENGTH,
    )
    assert entry_point.totalItems == 6
    assert (
        entry_point.last["id"] == "http://127.0.0.1:3000/change_documents/works/page/3"
    )


def test_instance_entry_point_add(client: TestClient, db_session: Session) -> None:
    # Adds 4 works
    add_works(db_session, start_index=40)
    # Adds 4 instances
    add_instances(db_session)

    entry_point = entry_point = EntryPoint(
        db=db_session,
        bc_type=BluecoreType.INSTANCES,
        host=HOST,
        page_length=TEST_PAGE_LENGTH,
    )
    assert entry_point.totalItems == 4
    assert (
        entry_point.last["id"]
        == "http://127.0.0.1:3000/change_documents/instances/page/2"
    )


def test_instance_entry_point_update(client: TestClient, db_session: Session) -> None:
    # Adds 4 works
    add_works(db_session, start_index=60)
    # Adds 4 instances
    add_instances(db_session)
    # Updates 2 works
    update_instances(db_session)

    entry_point = entry_point = EntryPoint(
        db=db_session,
        bc_type=BluecoreType.INSTANCES,
        host=HOST,
        page_length=TEST_PAGE_LENGTH,
    )
    assert entry_point.totalItems == 8
    assert (
        entry_point.last["id"]
        == "http://127.0.0.1:3000/change_documents/instances/page/4"
    )

    response = client.get("/change_documents/instances/feed")
    assert response.status_code == 200
    as_schema = EntryPointSchema.model_validate(entry_point)
    assert EntryPointSchema(**response.json()) == as_schema


if __name__ == "__main__":
    pytest.main()
