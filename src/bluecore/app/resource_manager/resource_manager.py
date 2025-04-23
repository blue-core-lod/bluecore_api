from bluecore.schemas import (
    InstanceCreateSchema,
    InstanceUpdateSchema,
    WorkCreateSchema,
    WorkUpdateSchema,
)
from bluecore_models.models import Instance, Work
from fastapi import HTTPException
from sqlalchemy.orm import Session


class ResourceManager:
    def create_instance(self, instance: InstanceCreateSchema, db: Session) -> Instance:
        db_instance = Instance(
            data=instance.data, uri=instance.uri, work_id=instance.work_id
        )
        db.add(db_instance)
        db.commit()
        db.refresh(db_instance)

        return db_instance

    def read_instance(self, instance_id: int, db: Session) -> Instance:
        db_instance = db.query(Instance).filter(Instance.id == instance_id).first()

        if db_instance is None:
            raise HTTPException(status_code=404, detail="Instance not found")

        return db_instance

    def update_instance(
        self, instance_id: int, instance: InstanceUpdateSchema, db: Session
    ) -> Instance:
        db_instance = db.query(Instance).filter(Instance.id == instance_id).first()
        if db_instance is None:
            raise HTTPException(
                status_code=404, detail=f"Instance {instance_id} not found"
            )

        # Update fields if they are provided
        if instance.data is not None:
            db_instance.data = instance.data
        if instance.uri is not None:
            db_instance.uri = instance.uri
        if instance.work_id is not None:
            db_instance.work_id = instance.work_id

        db.commit()
        db.refresh(db_instance)

        return db_instance

    def create_work(self, work: WorkCreateSchema, db: Session) -> Work:
        db_work = Work(data=work.data, uri=work.uri)
        db.add(db_work)
        db.commit()
        db.refresh(db_work)

        return db_work

    def read_work(self, work_id: int, db: Session) -> Work:
        db_work = db.query(Work).filter(Work.id == work_id).first()

        if db_work is None:
            raise HTTPException(status_code=404, detail=f"Work {work_id} not found")

        return db_work

    def update_work(self, work_id: int, work: WorkUpdateSchema, db: Session) -> Work:
        db_work = db.query(Work).filter(Work.id == work_id).first()
        if db_work is None:
            raise HTTPException(status_code=404, detail=f"Work {work_id} not found")

        # Update fields if they are provided
        if work.data is not None:
            db_work.data = work.data
        if work.uri is not None:
            db_work.uri = work.uri

        db.commit()
        db.refresh(db_work)

        return db_work
