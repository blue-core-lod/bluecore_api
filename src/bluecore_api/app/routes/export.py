from typing import Annotated

from bluecore_models.models.version import CURRENT_USER_ID
from fastapi import APIRouter, Body, Depends, HTTPException

from bluecore_api import workflow
from bluecore_api.constants import READ_ONLY_ROLES, KeycloakRole
from bluecore_api.middleware.bluecore_check_permissions import (
    BluecoreCheckPermissions as BCP,
)
from bluecore_api.schemas.schemas import ExportResponseSchema, ExportSchema

endpoints = APIRouter()

EXPORT_EXAMPLES = {
    "by_instance_uri": {
        "summary": "Export by Bluecore instance URI",
        "description": "instance_uri is required; local_id is optional and may "
        "be omitted entirely.",
        "value": {
            "instance_uri": "https://bcld.info/instances/8836b3c5-9bc6-421b-9591-df25499cd93c"
        },
    },
    "overlay_by_local_id": {
        "summary": "Overlay an existing catalog record by local identifier",
        "description": "instance_uri is still required to identify the source "
        "data; local_id additionally targets an existing catalog record "
        "(e.g. HRID) to overlay.",
        "value": {
            "instance_uri": "https://bcld.info/instances/8836b3c5-9bc6-421b-9591-df25499cd93c",
            "local_id": "a123456",
        },
    },
}


@endpoints.post(
    "/export/",
    dependencies=[Depends(BCP(KeycloakRole.CREATE, READ_ONLY_ROLES))],
    response_model=ExportResponseSchema,
    operation_id="export",
)
async def export_to_lsp(
    export: Annotated[ExportSchema, Body(openapi_examples=EXPORT_EXAMPLES)],
):
    """
    Triggers Workflows DAG for exporting Instance and Work to an insitution's
    Library Services Platform (LSP) like FOLIO or Alma.
    """
    user_uid = CURRENT_USER_ID.get()

    try:
        workflow_id = await workflow.export_instance(
            instance_uri=export.instance_uri,
            local_id=export.local_id,
            user_uid=user_uid,
        )
    except workflow.WorkflowError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return {
        "instance_uri": export.instance_uri,
        "local_id": export.local_id,
        "workflow_id": workflow_id,
    }
