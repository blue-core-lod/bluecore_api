from bluecore.change_documents.counter import Counter
from bluecore.constants import (
    BluecoreType,
)
from bluecore.schemas.change_documents.schemas import (
    EntryPointSchema,
)
from sqlalchemy.orm import Session
import math


class EntryPoint(Counter, EntryPointSchema):
    def __init__(self, db: Session, bc_type: BluecoreType, host: str, page_length: int):
        total = self.total_items(db=db, bc_type=bc_type)
        last_page: int = math.ceil(total / page_length)
        super().__init__(
            summary="Bluecore",
            id=f"{host}/change_documents/{bc_type}/feed",
            totalItems=total,
            first={
                "id": f"{host}/change_documents/{bc_type}/page/1",
                "type": "OrderedCollectionPage",
            },
            last={
                "id": f"{host}/change_documents/{bc_type}/page/{last_page}",
                "type": "OrderedCollectionPage",
            },
        )
