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
from sqlalchemy.orm import Session
from typing import Dict, List, Union
import math


class EntityChangeObject(EntityChangeObjectSchema):
    def __init__(self, resource_uri: str, updated: str, resource_type: BibframeType):
        super().__init__(
            id=resource_uri,
            updated=updated,
            type=f"bf:{resource_type}",
        )


class EntityChangeActivity(EntityChangeActivitiesSchema):
    def __init__(self, version: Version):
        resource = version.resource
        resource_type = self.determine_bibframe_type(resource=resource)

        super().__init__(
            summary=f"New entity for bf:{resource_type}",
            published=str(version.created_at),
            type=self.determine_create_update(
                str(resource.created_at),
                str(resource.updated_at),
                str(version.created_at),
            ),
            object=EntityChangeObject(
                resource_uri=resource.uri,
                updated=str(version.created_at),
                resource_type=resource_type,
            ),
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

    def determine_create_update(
        self,
        resource_created_at: str,
        resource_updated_at: str,
        version_created_at: str,
    ) -> str:
        # Truncate until the create/update timestamps are aligned
        print("Determine Create/Update")
        print(f"resource_created_at: {resource_created_at}")
        print(f"resource_updated_at: {resource_updated_at}")
        print(f"version_created_at: {version_created_at}")
        rca = resource_created_at
        rua = resource_updated_at
        vca = version_created_at
        if resource_updated_at == version_created_at:
            if rua == rca:
                return "Create"
            else:
                return "Update"
        elif rca == vca:
            return "Create"
        else:
            return "Update"


class ChangeSet(Counter, ChangeSetSchema):
    def __init__(
        self, db: Session, bc_type: BluecoreType, id: int, host: str, page_length: int
    ):
        total = self.total_items(db=db, bc_type=bc_type)

        query = (
            db.query(Version).join(ResourceBase).filter(ResourceBase.type == bc_type)
        )
        paginated_query = query.offset((id - 1) * page_length).limit(page_length).all()

        total_pages = math.ceil(total / page_length)
        prev_next = self.determine_prev_next(
            id=id, total_pages=total_pages, bc_type=bc_type, host=host
        )

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
        if id < 0:
            id = 1
        if id > total_pages:
            id = total_pages

        if id < total_pages:
            next = f"{host}/change_documents/{bc_type}/page/{id + 1}"
            if id > 1:
                prev = f"{host}/change_documents/{bc_type}/page/{id - 1}"
            else:
                prev = None
        else:
            # id == total_pages
            if total_pages > 1:
                prev = f"{host}/change_documents/{bc_type}/page/{total_pages - 1}"
            else:
                prev = None
            next = None

        return {"prev": prev, "next": next}
