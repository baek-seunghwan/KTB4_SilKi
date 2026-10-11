"""Spring-triggered internal menu reindex endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status

from silki_ai.contracts import ReindexRequest, ReindexResponse
from silki_ai.internal_auth import require_internal_api_key

router = APIRouter(prefix="/ai/internal/v1", tags=["internal"])


@router.post(
    "/stores/{store_id}/reindex",
    response_model=ReindexResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_internal_api_key)],
)
async def reindex_store(
    store_id: str,
    body: ReindexRequest,
    request: Request,
) -> ReindexResponse:
    return await request.app.state.container.reindex_service.reindex(store_id, body)
