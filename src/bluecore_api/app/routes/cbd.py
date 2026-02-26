#################################################################################################################################
## Deprecated: The instances endpoint now supports content negotiation and can return CBD JSON-LD or XML based on the request. ##
## The separate CBD endpoint is no longer needed and will be removed in a future release.                                      ##
#################################################################################################################################

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from bluecore_api.app.utils.serializer.cbd import (
    generate_cbd_jsonld_response,
    generate_cbd_xml_response,
)
from bluecore_api.database import get_db
from bluecore_models.models import Instance


endpoints = APIRouter()


@endpoints.get("/cbd/{instance_uuid}", operation_id="get_cbd")
async def cbd(instance_uuid: str, db: Session = Depends(get_db)) -> Response:
    # Marva editor expects the request url to end with .rdf
    effective_uuid = instance_uuid.strip().replace(".rdf", "").replace(".jsonld", "")
    db_instance = db.query(Instance).filter(Instance.uuid == effective_uuid).first()

    if db_instance is None:
        raise HTTPException(status_code=404, detail="Instance not found")

    if instance_uuid.endswith(".jsonld"):
        return generate_cbd_jsonld_response(db_instance)

    return generate_cbd_xml_response(db_instance)
