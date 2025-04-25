from bluecore.schemas import (
    ActivityStreamsChangeSetSchema,
    ActivityStreamsEntityChangeActivitiesSchema,
    ActivityStreamsEntryPointSchema,
    ActivityStreamsObjectSchema,
)
from bluecore.utils.constants import ACTIVITY_STREAMS_PAGE_LENGTH, BCType, BFType
from bluecore_models.models import ResourceBase, Version
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import Dict, List, Union
import math
import os

HOST = os.getenv("HOST", "http://127.0.0.1:3000")


class ActivityStreamsGenerator:
    """
    A class to handle change notifications.
    """

    page_length: int = 1

    def __init__(self, page_length: int = ACTIVITY_STREAMS_PAGE_LENGTH):
        """
        Initializes the ActivityStreamsGenerator with a specified page length.
        The page length is set to ACTIVITY_STREAMS_PAGE_LENGTH (100) by default.
        Don't change this value unless running tests.

        Args:
            page_length (int): The number of items per page for the activity streams.
        """
        self.page_length = page_length

    def activity_streams_feed(
        self, db: Session, bc_type: str
    ) -> ActivityStreamsEntryPointSchema:
        """
        Generates an activity streams feed for a given resource type.

        This method constructs an OrderedCollection representation of an
        activity streams feed for the specified resource type. It calculates
        the total number of items, determines the last page, and provides
        metadata about the feed including its context, summary, and pagination
        details.
        The feed is structured according to the Activity Streams 2.0
        specification, and includes a context URL for the EMM specification.

        Args:
            db (Session): database session used to query the resource data
            bf_type (str): type of the resource for which the activity
                  streams feed is being generated

        Returns:
            ActivityStreamsEntryPointSchema: activity streams feed
                  in the OrderedCollection format, including metadata
                  and pagination details
        """
        total = (
            db.query(func.count(Version.id))
            .join(ResourceBase)
            .filter(ResourceBase.type == bc_type)
            .scalar()
        )
        last_page: int = math.ceil(total / self.page_length)
        return ActivityStreamsEntryPointSchema(
            context=[
                "https://www.w3.org/ns/activitystreams",
                "https://emm-spec.org/1.0/context.json",
            ],
            summary="Bluecore",
            type="OrderedCollection",
            id=f"{HOST}/change_documents/{bc_type}/activitystreams/feed",
            totalItems=total,
            first={
                "id": f"{HOST}/change_documents/{bc_type}/activitystreams/page/1",
                "type": "OrderedCollectionPage",
            },
            last={
                "id": f"{HOST}/change_documents/{bc_type}/activitystreams/page/{last_page}",
                "type": "OrderedCollectionPage",
            },
        )

    def activity_streams_page(
        self, id: int, db: Session, bc_type: str
    ) -> ActivityStreamsChangeSetSchema:
        """
        Retrieves a paginated list of activity streams for a given resource type.

        This method constructs an OrderedCollectionPage representation of
        activity streams for the specified resource type. It calculates
        the total number of items, determines the next and previous pages,
        and provides metadata about the page including its context, type,
        and pagination details. The page is structured according to the
        Activity Streams 2.0 specification, and includes a context URL for
        the EMM specification.

        Args:
            id (int): page number to retrieve
            db (Session): database session to use for querying
            bf_type (str): type of resource to filter the activity streams

        Returns:
            ActivityStreamsChangeSetSchema: activity streams in the OrderedCollectionPage format
        """
        total = (
            db.query(func.count(Version.id))
            .join(ResourceBase)
            .filter(ResourceBase.type == bc_type)
            .scalar()
        )

        query = (
            db.query(Version).join(ResourceBase).filter(ResourceBase.type == bc_type)
        )
        paginated_query = (
            query.offset((id - 1) * self.page_length).limit(self.page_length).all()
        )
        return self._generate_page(
            id=id, items=paginated_query, total=total, bc_type=bc_type
        )

    def instances_activity_streams_feed(
        self, db: Session
    ) -> ActivityStreamsEntryPointSchema:
        """
        This function generates an activity streams feed for instances.

        Args:
            db (Session): The database session to use for querying.

        Returns:
            ActivityStreamsEntryPointSchema: activity streams feed in the OrderedCollection format
        """

        return self.activity_streams_feed(db=db, bc_type=BCType.INSTANCES)

    def instances_activity_streams_page(
        self, id: int, db: Session
    ) -> ActivityStreamsChangeSetSchema:
        """
        This function retrieves a paginated list of activity streams for instances.

        Args:
            id (int): page number to retrieve
            db (Session): database session to use for querying

        Returns:
            ActivityStreamsChangeSetSchema: activity streams in the OrderedCollectionPage format
        """

        return self.activity_streams_page(id=id, db=db, bc_type=BCType.INSTANCES)

    def works_activity_streams_feed(
        self, db: Session
    ) -> ActivityStreamsEntryPointSchema:
        """
        This function generates an activity streams feed for works.

        Args:
            db (Session): database session to use for querying

        Returns:
            ActivityStreamsEntryPointSchema: activity streams feed in the OrderedCollection format
        """

        return self.activity_streams_feed(db=db, bc_type=BCType.WORKS)

    def works_activity_streams_page(
        self, id: int, db: Session
    ) -> ActivityStreamsChangeSetSchema:
        """
        This function retrieves a paginated list of activity streams for instances.

        Args:
            id (int): page number to retrieve
            db (Session): database session to use for querying

        Returns:
            ActivityStreamsChangeSetSchema: activity streams in the OrderedCollectionPage format
        """

        return self.activity_streams_page(id=id, db=db, bc_type=BCType.WORKS)

    def determine_prev_next(
        self, id: int, total_pages: int, bc_type: str
    ) -> Dict[str, Union[str, None]]:
        """
        Private method to determine the previous and next page URLs.

        Args:
            id (int): current page number
            total_pages (int): total number of pages available

        Returns:
            Dict[str, str]: dictionary containing the previous and next page URLs
        """
        if id < 0:
            id = 1
        if id > total_pages:
            id = total_pages

        if id < total_pages:
            next = f"{HOST}/change_documents/{bc_type}/activitystreams/page/{id + 1}"
            if id > 1:
                prev = (
                    f"{HOST}/change_documents/{bc_type}/activitystreams/page/{id - 1}"
                )
            else:
                prev = None
        else:
            # id == total_pages
            if total_pages > 1:
                prev = f"{HOST}/change_documents/{bc_type}/activitystreams/page/{total_pages - 1}"
            else:
                prev = None
            next = None

        return {"prev": prev, "next": next}

    def determine_create_update(
        self,
        resource_created_at: str,
        resource_updated_at: str,
        version_created_at: str,
    ) -> str:
        """
        Determines whether the version is a create or an update based on timestamps.
        This method compares the created and updated timestamps of the resource
        and the version to determine if the version represents a new entity
        If resource updated_at and version created_at are the same:
        - If resource created_at and resource updated_at are the same, it is a "Create"
        - If resource created_at and resource updated_at are different, it is an "Update"
        If resource updated_at and version created_at are different:
        - If resource created_at and version created_at are the same, it is a "Create"
        - Otherwise, it is an "Update"

        Args:
            resource_created_at (str): ResourceBase created_at timestamp
            resource_updated_at (str): ResourceBase updated_at timestamp
            version_created_at (str): Version created_at timestamp

        Returns:
            str: Create or Update
        """
        rca = resource_created_at[:23]
        rua = resource_updated_at[:23]
        vca = version_created_at[:23]
        if resource_updated_at == version_created_at:
            if rua == rca:
                return "Create"
            else:
                return "Update"
        elif rca == vca:
            return "Create"
        else:
            return "Update"

    def _generate_page(
        self,
        id: int,
        items: List[Version],
        total: int,
        bc_type: str,
    ) -> ActivityStreamsChangeSetSchema:
        """
          Private method to generate an activity streams page for a given resource type.

        Args:
            id (int): page number to generate
            items (List[Version]): list of versions to include in the page
            total (int): total number of items available
            bc_type (str): type of resource: BCType.Works or BCType.Instances

        Returns:
            ActivityStreamsChangeSetSchema: activity streams for a given page
        """

        total_pages = math.ceil(total / self.page_length)
        prev_next = self.determine_prev_next(
            id=id, total_pages=total_pages, bc_type=bc_type
        )

        return ActivityStreamsChangeSetSchema(
            context=[
                "https://www.w3.org/ns/activitystreams",
                "https://emm-spec.org/1.0/context.json",
                {"bf": "http://id.loc.gov/ontologies/bibframe/"},
            ],
            type="OrderedCollectionPage",
            id=f"{HOST}/change_documents/{bc_type}/activitystreams/page/{id}",
            partOf=f"{HOST}/change_documents/{bc_type}/activitystreams/feed",
            prev=prev_next["prev"],
            next=prev_next["next"],
            orderedItems=self._generate_ordered_items(items),
            totalItems=len(items),
        )

    # When https://github.com/blue-core-lod/bluecore_api/issues/66 is complete,
    # we can add list of urls to the ordered items object
    # def generate_url(self) -> List[str]:
    #     return []

    def _generate_ordered_items(
        self, versions: List[Version]
    ) -> List[ActivityStreamsEntityChangeActivitiesSchema]:
        """
        Private method to generate ordered items for the activity streams page.

        Args:
            versions (List[Version]): list of versions to include in the ordered items

        Returns:
            List[ActivityStreamsEntityChangeActivitiesSchema]: list of ordered items
        """

        ordered_items: List[ActivityStreamsEntityChangeActivitiesSchema] = []
        for version in versions:
            resource = version.resource
            if resource.type == BCType.WORKS:
                resource_type = BFType.WORK
            elif resource.type == BCType.INSTANCES:
                resource_type = BFType.INSTANCE
            else:
                raise ValueError(
                    f"Unknown resource type: {resource.type} for resource {resource.id}"
                )

            ordered_items.append(
                ActivityStreamsEntityChangeActivitiesSchema(
                    summary=f"New entity for bf:{resource_type}",
                    published=str(version.created_at),
                    type=self.determine_create_update(
                        str(resource.created_at),
                        str(resource.updated_at),
                        str(version.created_at),
                    ),
                    object=ActivityStreamsObjectSchema(
                        id=resource.uri,
                        updated=str(version.created_at),
                        type=f"bf:{resource_type}",
                        # url=self.generate_url(),
                    ),
                )
            )

        return ordered_items
