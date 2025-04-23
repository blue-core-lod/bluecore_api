from bluecore_models.models import ResourceBase, Version
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import Any, Dict, List, Union
import math
import os

from bluecore.utils.constants import ACTIVITY_STREAMS_PAGE_LENGTH, BFType

HOST = os.getenv("HOST", "http://127.0.0.1:3000")


class ActivityStreamsGenerator:
    """
    A class to handle change notifications.
    """

    def activity_streams_feed(self, db: Session, bf_type: str) -> Dict[str, Any]:
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
            db (Session): The database session used to query the resource data.
            bf_type (str): The type of the resource for which the activity
                  streams feed is being generated.

        Returns:
            Dict[str, Any]: A dictionary representing the activity streams feed
                  in the OrderedCollection format, including metadata
                  and pagination details.
        """
        total = (
            db.query(func.count(Version.id))
            .join(ResourceBase)
            .filter(ResourceBase.type == bf_type)
            .scalar()
        )
        last_page: int = math.ceil(total / ACTIVITY_STREAMS_PAGE_LENGTH)
        return {
            "@context": [
                "https://www.w3.org/ns/activitystreams",
                "https://emm-spec.org/1.0/context.json",
            ],
            "summary": "Bluecore",
            "type": "OrderedCollection",
            "id": f"{HOST}/change_documents/{bf_type}/activitystreams/feed",
            "totalItems": total,
            "first": {
                "id": f"{HOST}/change_documents/{bf_type}/activitystreams/page/1",
                "type": "OrderedCollectionPage",
            },
            "last": {
                "id": f"{HOST}/change_documents/{bf_type}/activitystreams/page/{last_page}",
                "type": "OrderedCollectionPage",
            },
        }

    def activity_streams_page(
        self, id: int, db: Session, bf_type: str
    ) -> Dict[str, Any]:
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
            Dict[str, Any]: activity streams in the OrderedCollectionPage format
        """
        total = (
            db.query(func.count(Version.id))
            .join(ResourceBase)
            .filter(ResourceBase.type == bf_type)
            .scalar()
        )

        query = (
            db.query(Version).join(ResourceBase).filter(ResourceBase.type == bf_type)
        )
        paginated_query = (
            query.offset((id - 1) * ACTIVITY_STREAMS_PAGE_LENGTH)
            .limit(ACTIVITY_STREAMS_PAGE_LENGTH)
            .all()
        )
        return self._generate_page(
            id=id, items=paginated_query, total=total, bf_type=bf_type
        )

    def instances_activity_streams_feed(self, db: Session) -> Dict[str, Any]:
        """
        This function generates an activity streams feed for instances.

        Args:
            db (Session): The database session to use for querying.

        Returns:
            Dict[str, Any]: activity streams feed in the OrderedCollection format
        """

        return self.activity_streams_feed(db=db, bf_type=BFType.INSTANCES)

    def instances_activity_streams_page(self, id: int, db: Session) -> Dict[str, Any]:
        """
        This function retrieves a paginated list of activity streams for instances.

        Args:
            id (int): page number to retrieve
            db (Session): database session to use for querying

        Returns:
            Dict[str, Any]: activity streams in the OrderedCollectionPage format
        """

        return self.activity_streams_page(id=id, db=db, bf_type=BFType.INSTANCES)

    def works_activity_streams_feed(self, db: Session) -> Dict[str, Any]:
        """
        This function generates an activity streams feed for works.

        Args:
            db (Session): database session to use for querying

        Returns:
            Dict[str, Any]: activity streams feed in the OrderedCollection format
        """

        return self.activity_streams_feed(db=db, bf_type=BFType.WORKS)

    def works_activity_streams_page(self, id: int, db: Session) -> Dict[str, Any]:
        """
        This function retrieves a paginated list of activity streams for instances.

        Args:
            id (int): page number to retrieve
            db (Session): database session to use for querying

        Returns:
            Dict[str, Any]: activity streams in the OrderedCollectionPage format
        """

        return self.activity_streams_page(id=id, db=db, bf_type=BFType.WORKS)

    def _determine_prev_next(
        self, id: int, total_pages: int, bf_type: str
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
            next = f"{HOST}/change_documents/{bf_type}/activitystreams/page/{id + 1}"
            if id > 1:
                prev = (
                    f"{HOST}/change_documents/{bf_type}/activitystreams/page/{id - 1}"
                )
            else:
                prev = None
        else:
            # id == total_pages
            if total_pages > 1:
                prev = f"{HOST}/change_documents/{bf_type}/activitystreams/page/{total_pages - 1}"
            else:
                prev = None
            next = None

        return {"prev": prev, "next": next}

    def _generate_page(
        self,
        id: int,
        items: List[Version],
        total: int,
        bf_type: str,
    ) -> Dict[str, Any]:
        """
          Private method to generate an activity streams page for a given resource type.

        Args:
            id (int): The page number to retrieve.
            items (List[Version]): The list of versions to include in the page.
            total (int): The total number of items available.
            bf_type (str): The type of resource for which the activity streams page is being generated.

        Returns:
            Dict[str, Any]: A dictionary representing the activity streams page
        """

        total_pages = math.ceil(total / ACTIVITY_STREAMS_PAGE_LENGTH)
        prev_next = self._determine_prev_next(
            id=id, total_pages=total_pages, bf_type=bf_type
        )

        return {
            "@context": [
                "https://www.w3.org/ns/activitystreams",
                "https://emm-spec.org/1.0/context.json",
                {"bf": "http://id.loc.gov/ontologies/bibframe/"},
            ],
            "type": "OrderedCollectionPage",
            "id": f"{HOST}/change_documents/{bf_type}/activitystreams/page/{id}",
            "partOf": f"{HOST}/change_documents/{bf_type}/activitystreams/feed",
            "prev": prev_next["prev"],
            "next": prev_next["next"],
            "orderedItems": self._generate_ordered_items(items),
            "totalItems": len(items),
        }

    def _generate_ordered_items(self, versions: List[Version]) -> List[Dict[str, Any]]:
        """
        Private method to generate ordered items for the activity streams page.

        Args:
            versions (List[Version]): The list of versions to include in the ordered items.

        Returns:
            List[Dict[str, Any]]: A list of dictionaries representing the ordered items
        """

        ordered_items: List[Dict[str, Any]] = []
        for version in versions:
            resource = version.resource
            # truncate the created_at timestamp for comparison
            r_created_at = str(resource.created_at)[:-4]
            v_created_at = str(version.created_at)[:-4]
            if r_created_at == v_created_at:
                my_type = "Create"
            else:
                my_type = "Update"
            ordered_items.append(
                {
                    "summary": f"New entity for {resource.uri}",
                    "published": str(version.created_at),
                    "type": my_type,
                    "object": {
                        "id": f"{HOST}/{resource.type}/{resource.id}",
                        "updated": str(version.created_at),
                        "type": f"bf:{resource.type.capitalize()}",
                    },
                }
            )

        return ordered_items
