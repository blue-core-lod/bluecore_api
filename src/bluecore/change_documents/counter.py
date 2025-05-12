from bluecore.constants import BluecoreType
from bluecore_models.models import ResourceBase, Version
from sqlalchemy import func, select
from sqlalchemy.orm import Session


class Counter:
    """
    A class to count the number of items in a database.
    """

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
