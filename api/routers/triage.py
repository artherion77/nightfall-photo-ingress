"""Triage write endpoints (accept/reject/defer)."""

from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, status
from fastapi.responses import JSONResponse

from api.auth import verify_api_token
from api.dependencies import get_registry_connection
from api.schemas import TriageRequest, TriageResponse
from api.services import TriageService

router = APIRouter(prefix="/api/v1", tags=["triage"])


def _run_triage_action(
    *,
    action: str,
    item_id: str,
    payload: TriageRequest,
    idempotency_key: str,
    conn: sqlite3.Connection,
) -> JSONResponse:
    service = TriageService(conn)
    try:
        status_code, response = service.execute(
            action=action,
            item_id=item_id,
            idempotency_key=idempotency_key,
            reason=payload.reason,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Triage action failed") from exc

    return JSONResponse(status_code=status_code, content=response.model_dump())


@router.post("/triage/{item_id}/accept", response_model=TriageResponse)
async def triage_accept(
    item_id: Annotated[str, Path(min_length=1, max_length=128)],
    payload: TriageRequest,
    _: str = Depends(verify_api_token),
    idempotency_key: str = Header(..., alias="X-Idempotency-Key", min_length=8, max_length=128),
    conn: sqlite3.Connection = Depends(get_registry_connection),
) -> JSONResponse:
    return _run_triage_action(
        action="accept",
        item_id=item_id,
        payload=payload,
        idempotency_key=idempotency_key,
        conn=conn,
    )


@router.post("/triage/{item_id}/reject", response_model=TriageResponse)
async def triage_reject(
    item_id: Annotated[str, Path(min_length=1, max_length=128)],
    payload: TriageRequest,
    _: str = Depends(verify_api_token),
    idempotency_key: str = Header(..., alias="X-Idempotency-Key", min_length=8, max_length=128),
    conn: sqlite3.Connection = Depends(get_registry_connection),
) -> JSONResponse:
    return _run_triage_action(
        action="reject",
        item_id=item_id,
        payload=payload,
        idempotency_key=idempotency_key,
        conn=conn,
    )


@router.post("/triage/{item_id}/defer", response_model=TriageResponse)
async def triage_defer(
    item_id: Annotated[str, Path(min_length=1, max_length=128)],
    payload: TriageRequest,
    _: str = Depends(verify_api_token),
    idempotency_key: str = Header(..., alias="X-Idempotency-Key", min_length=8, max_length=128),
    conn: sqlite3.Connection = Depends(get_registry_connection),
) -> JSONResponse:
    return _run_triage_action(
        action="defer",
        item_id=item_id,
        payload=payload,
        idempotency_key=idempotency_key,
        conn=conn,
    )
