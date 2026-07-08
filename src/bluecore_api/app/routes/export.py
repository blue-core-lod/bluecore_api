from bluecore_models.models.version import CURRENT_USER_ID
from fastapi import APIRouter, Depends, HTTPException

from bluecore_api import workflow
from bluecore_api.constants import READ_ONLY_ROLES, KeycloakRole
from bluecore_api.middleware.bluecore_check_permissions import (
    BluecoreCheckPermissions as BCP,
)
from bluecore_api.schemas.schemas import ExportResponseSchema, ExportSchema

endpoints = APIRouter()


@endpoints.post(
    "/export/",
    dependencies=[Depends(BCP(KeycloakRole.CREATE, READ_ONLY_ROLES))],
    response_model=ExportResponseSchema,
    operation_id="export",
)
async def export_to_lsp(export: ExportSchema):
    """
    Triggers Workflows DAG for exporting Instance and Work to an insitution's
    Library Services Platform (LSP) like FOLIO or Alma.
    """
    user_uid = CURRENT_USER_ID.get()

    try:
        workflow_id = await workflow.export_instance(
            instance_uri=export.instance_uri, user_uid=user_uid
        )
    except workflow.WorkflowError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return {"instance_uri": export.instance_uri, "workflow_id": workflow_id}
