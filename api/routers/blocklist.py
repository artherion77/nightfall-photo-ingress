"""Blocklist endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi import Header, HTTPException, Path, status
import sqlite3
from fastapi.responses import JSONResponse

from api.dependencies import get_registry_connection
from api.auth import verify_api_token
from api.schemas import BlockRule, BlockRuleCreate, BlockRuleDeleteResponse, BlockRuleList, BlockRuleUpdate
from api.services import BlocklistService

router = APIRouter(prefix="/api/v1", tags=["blocklist"])


@router.get("/blocklist", response_model=BlockRuleList)
async def get_blocklist(
    _: str = Depends(verify_api_token),
    conn: sqlite3.Connection = Depends(get_registry_connection),
) -> BlockRuleList:
    """Get all blocklist rules."""
    service = BlocklistService(conn)
    return service.get_blocklist()


@router.post("/blocklist", response_model=BlockRule)
async def create_block_rule(
    payload: BlockRuleCreate,
    _: str = Depends(verify_api_token),
    idempotency_key: str = Header(..., alias="X-Idempotency-Key", min_length=8, max_length=128),
    conn: sqlite3.Connection = Depends(get_registry_connection),
) -> JSONResponse:
    service = BlocklistService(conn)
    try:
        status_code, response = service.create_rule(payload=payload, idempotency_key=idempotency_key)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return JSONResponse(status_code=status_code, content=response.model_dump())


@router.patch("/blocklist/{rule_id}", response_model=BlockRule)
async def update_block_rule(
    rule_id: Annotated[int, Path(ge=1)],
    payload: BlockRuleUpdate,
    _: str = Depends(verify_api_token),
    idempotency_key: str = Header(..., alias="X-Idempotency-Key", min_length=8, max_length=128),
    conn: sqlite3.Connection = Depends(get_registry_connection),
) -> JSONResponse:
    service = BlocklistService(conn)
    try:
        status_code, response = service.update_rule(
            rule_id=rule_id,
            payload=payload,
            idempotency_key=idempotency_key,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return JSONResponse(status_code=status_code, content=response.model_dump())


@router.delete("/blocklist/{rule_id}", response_model=BlockRuleDeleteResponse)
async def delete_block_rule(
    rule_id: Annotated[int, Path(ge=1)],
    _: str = Depends(verify_api_token),
    idempotency_key: str = Header(..., alias="X-Idempotency-Key", min_length=8, max_length=128),
    conn: sqlite3.Connection = Depends(get_registry_connection),
) -> JSONResponse:
    service = BlocklistService(conn)
    try:
        status_code, response = service.delete_rule(rule_id=rule_id, idempotency_key=idempotency_key)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return JSONResponse(status_code=status_code, content=response.model_dump())
