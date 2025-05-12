from bluecore.constants import BluecoreType
from bluecore_models.models import ResourceBase, Version
from sqlalchemy import func, select
from sqlalchemy.orm import Session


class Counter:
    """
    A class to count the number of items in a database.
    """

    def total_items(self, db: Session, bc_type: BluecoreType) -> int:
        return (
            db.scalar(
                select(func.count(Version.id))
                .select_from(Version)
                .join(ResourceBase)
                .filter(ResourceBase.type == bc_type)
            )
            or 0
        )
