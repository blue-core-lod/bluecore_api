from bluecore.constants import (
    DEFAULT_ACTIVITY_STREAMS_PAGE_LENGTH,
    # BibframeType,
    BluecoreType,
)
from bluecore.schemas.change_documents.schemas import (
    ChangeSetSchema,
    # EntityChangeActivitiesSchema,
    # EntityChangeObjectSchema,
    EntryPointSchema,
)
from bluecore_models.models import ResourceBase, Version
from sqlalchemy import func, select
from sqlalchemy.orm import Session

# from typing import Dict, List, Union
import math
import os


class ActivityStreamsGenerator:
    """
    A class to handle change notifications.
    """

    page_length: int
    host: str

    def __init__(
        self,
        page_length: int,
        host: str,
    ):
        """
        Initializes the ActivityStreamsGenerator with a specified page length.

        Args:
            page_length (int): The number of items per page for the activity streams.
            host (str): The host URL for the activity streams.
        """
        self.page_length = page_length
        self.host = host

    def total_items(self, db: Session, bc_type: BluecoreType) -> int:
        """
        Returns the total number of items in the activity streams.
        This method is a placeholder and should be implemented to return
        the actual total number of items.

        Returns:
            int: The total number of items in the activity streams.
        """
        return (
            db.scalar(
                select(func.count(Version.id))
                .select_from(Version)
                .join(ResourceBase)
                .filter(ResourceBase.type == bc_type)
            )
            or 0
        )

    def entry_point(self, db: Session, bc_type: BluecoreType) -> EntryPointSchema:
        """
        Generates an entry point for a given resource type.

        This method constructs an OrderedCollection representation of an
        activity streams feed for the specified resource type. It calculates
        the total number of items, determines the last page, and provides
        metadata about the feed including its context, summary, and pagination
        details.
        The feed is structured according to the Activity Streams 2.0
        specification, and includes a context URL for the EMM specification.

        Args:
            db (Session): database session used to query the resource data
            bc_type (BluecoreType): type of the resource for which the activity
                  streams feed is being generated

        Returns:
            EntryPointSchema: activity streams feed
                  in the OrderedCollection format, including metadata
                  and pagination details
        """
        total = self.total_items(db=db, bc_type=bc_type)
        last_page: int = math.ceil(total / self.page_length)
        return EntryPointSchema(
            summary="Bluecore",
            id=f"{self.host}/change_documents/{bc_type}/feed",
            totalItems=total,
            first={
                "id": f"{self.host}/change_documents/{bc_type}/page/1",
                "type": "OrderedCollectionPage",
            },
            last={
                "id": f"{self.host}/change_documents/{bc_type}/page/{last_page}",
                "type": "OrderedCollectionPage",
            },
        )

    def change_set(
        self, id: int, db: Session, bc_type: BluecoreType
    ) -> ChangeSetSchema:
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
            bc_type (BluecoreType): type of resource to filter the activity streams

        Returns:
            ChangeSetSchema: activity streams in the OrderedCollectionPage format
        """
        return ChangeSetSchema(
            id="TBD",
            partOf="TBD",
            orderedItems=[],
        )

    def instances_entry_point(self, db: Session) -> EntryPointSchema:
        """
        This function generates an activity streams feed for instances.

        Args:
            db (Session): The database session to use for querying.

        Returns:
            ActivityStreamsEntryPointSchema: activity streams feed in the OrderedCollection format
        """

        return self.entry_point(db=db, bc_type=BluecoreType.INSTANCES)

    def instances_change_set(self, id: int, db: Session) -> ChangeSetSchema:
        """
        This function retrieves a paginated list of activity streams for instances.

        Args:
            id (int): page number to retrieve
            db (Session): database session to use for querying

        Returns:
            ChangeSetSchema: activity streams in the OrderedCollectionPage format
        """

        return self.change_set(id=id, db=db, bc_type=BluecoreType.INSTANCES)

    def works_entry_point(self, db: Session) -> EntryPointSchema:
        """
        This function generates an activity streams feed for works.

        Args:
            db (Session): database session to use for querying

        Returns:
            EntryPointSchema: activity streams feed in the OrderedCollection format
        """

        return self.entry_point(db=db, bc_type=BluecoreType.WORKS)

    def works_change_set(self, id: int, db: Session) -> ChangeSetSchema:
        """
        This function retrieves a paginated list of activity streams for instances.

        Args:
            id (int): page number to retrieve
            db (Session): database session to use for querying

        Returns:
            ChangeSetSchema: activity streams in the OrderedCollectionPage format
        """

        return self.change_set(id=id, db=db, bc_type=BluecoreType.WORKS)


def get_activity_streams_generator() -> ActivityStreamsGenerator:
    """
    Dependency function to provide an instance of ActivityStreamsGenerator.
    It uses fixed page length of 100 and host of "http://127.0.0.1:3000"
    unless specified with env variable ACTIVITY_STREAMS_PAGE_LENGTH and
    ACTIVITY_STREAMS_HOST respectively.

    Returns:
        ActivityStreamsGenerator: An instance of the ActivityStreamsGenerator class.
    """
    return ActivityStreamsGenerator(
        page_length=int(
            os.getenv(
                "ACTIVITY_STREAMS_PAGE_LENGTH", DEFAULT_ACTIVITY_STREAMS_PAGE_LENGTH
            )
        ),
        host=os.getenv("ACTIVITY_STREAMS_HOST", "http://127.0.0.1:3000"),
    )
