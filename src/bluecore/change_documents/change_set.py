from bluecore.change_documents.counter import Counter
from bluecore.constants import (
    BibframeType,
    BluecoreType,
)
from bluecore_models.models import ResourceBase, Version
from bluecore.schemas.change_documents.schemas import (
    ChangeSetSchema,
    EntityChangeActivitiesSchema,
    EntityChangeObjectSchema,
)
from sqlalchemy import select
from sqlalchemy.orm import Session
from typing import Dict, List, Union
import math


class EntityChangeObject(EntityChangeObjectSchema):
    def __init__(self, resource: ResourceBase, version: Version):
        resource_type = self.determine_bibframe_type(resource=resource)
        super().__init__(
            id=resource.uri,
            updated=str(version.created_at),
            type=f"bf:{resource_type}",
        )

    def determine_bibframe_type(self, resource: ResourceBase) -> BibframeType:
        match resource.type:
            case BluecoreType.WORKS:
                return BibframeType.WORK
            case BluecoreType.INSTANCES:
                return BibframeType.INSTANCE
            case _:
                raise ValueError(
                    f"Unknown resource type: {resource.type} for resource {resource.id}"
                )


class EntityChangeActivity(EntityChangeActivitiesSchema):
    def __init__(self, version: Version):
        resource = version.resource
        create_update = self.determine_create_update(
            str(resource.created_at),
            str(resource.updated_at),
            str(version.created_at),
        )
        if create_update == "Create":
            summary = f"New entity for {resource.type}"
        else:
            summary = f"Updated entity for {resource.type}"

        super().__init__(
            summary=summary,
            published=str(version.created_at),
            type=create_update,
            object=EntityChangeObject(
                resource=resource,
                version=version,
            ),
        )

    def determine_create_update(
        self,
        resource_created_at: str,
        resource_updated_at: str,
        version_created_at: str,
    ) -> str:
        if resource_updated_at == version_created_at:
            # This is the most recent version of the resource
            if resource_updated_at == resource_created_at:
                # This is the first version of the resource
                return "Create"
            else:
                # This is an update to the resource
                return "Update"
        elif resource_created_at == version_created_at:
            return "Create"
        else:
            return "Update"


class ChangeSet(Counter, ChangeSetSchema):
    def __init__(
        self, db: Session, bc_type: BluecoreType, id: int, host: str, page_length: int
    ):
        total = self.total_items(db=db, bc_type=bc_type)
        total_pages = math.ceil(total / page_length)
        prev_next = self.determine_prev_next(
            id=id, total_pages=total_pages, bc_type=bc_type, host=host
        )

        stmt = (
            select(Version)
            .join(ResourceBase)
            .filter(ResourceBase.type == bc_type)
            .order_by(Version.id)
            .offset((id - 1) * page_length)
            .limit(page_length)
        )
        paginated_query = db.execute(stmt).scalars().all()
        ordered_items: List[EntityChangeActivitiesSchema] = []
        for version in paginated_query:
            ordered_items.append(EntityChangeActivity(version=version))

        super().__init__(
            id=f"{host}/change_documents/{bc_type}/page/{id}",
            partOf=f"{host}/change_documents/{bc_type}/feed",
            prev=prev_next["prev"],
            next=prev_next["next"],
            orderedItems=ordered_items,
            totalItems=len(ordered_items),
        )

    def determine_prev_next(
        self,
        id: int,
        total_pages: int,
        bc_type: BluecoreType,
        host: str,
    ) -> Dict[str, Union[str, None]]:
        """
        Out of bounds conditions are not handled here.
        """

        prev_id = id - 1
        if prev_id < 1:
            prev = None
        else:
            prev = f"{host}/change_documents/{bc_type}/page/{prev_id}"

        next_id = id + 1
        if next_id > total_pages:
            next = None
        else:
            next = f"{host}/change_documents/{bc_type}/page/{next_id}"

        return {"prev": prev, "next": next}
