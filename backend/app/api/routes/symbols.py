from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.code_intelligence import (
    CalleeResponse,
    CallerResponse,
    SymbolDependencyItem,
    SymbolDetailResponse,
    SymbolPathsResponse,
)
from app.services.code_intelligence.graph_service import (
    GraphService,
    graph_service,
)

router = APIRouter(prefix="/symbols", tags=["symbols"])


@router.get(
    "/{symbol_id}",
    response_model=SymbolDetailResponse,
    summary="Get symbol details and definition",
)
def get_symbol(
    symbol_id: int,
    db: Session = Depends(get_db),
    service: GraphService = Depends(lambda: graph_service),
):
    """Retrieve detailed symbol metadata and definition information."""
    return service.get_symbol(db, symbol_id=symbol_id)


@router.get(
    "/{symbol_id}/callers",
    response_model=list[CallerResponse],
    summary="Get symbol callers",
)
def get_symbol_callers(
    symbol_id: int,
    db: Session = Depends(get_db),
    service: GraphService = Depends(lambda: graph_service),
):
    """Retrieve all resolved callers that call this symbol."""
    return service.get_callers(db, symbol_id=symbol_id)


@router.get(
    "/{symbol_id}/callees",
    response_model=list[CalleeResponse],
    summary="Get symbol callees",
)
def get_symbol_callees(
    symbol_id: int,
    db: Session = Depends(get_db),
    service: GraphService = Depends(lambda: graph_service),
):
    """Retrieve all calls made by this symbol (resolved and unresolved)."""
    return service.get_callees(db, symbol_id=symbol_id)


@router.get(
    "/{symbol_id}/dependencies",
    response_model=list[SymbolDependencyItem],
    summary="Get symbol outgoing dependencies",
)
def get_symbol_dependencies(
    symbol_id: int,
    db: Session = Depends(get_db),
    service: GraphService = Depends(lambda: graph_service),
):
    """Retrieve outgoing dependencies originating from this symbol."""
    return service.get_symbol_dependencies(db, symbol_id=symbol_id)


@router.get(
    "/{symbol_id}/paths",
    response_model=SymbolPathsResponse,
    summary="Find directed call paths between two symbols",
)
def get_symbol_paths(
    symbol_id: int,
    target_id: int | None = Query(default=None, description="Target symbol ID to find paths to"),
    target_symbol_id: int | None = Query(default=None, description="Alias for target_id"),
    max_depth: int = Query(default=10, ge=1, le=50, description="Maximum number of call hops/edges"),
    db: Session = Depends(get_db),
    service: GraphService = Depends(lambda: graph_service),
):
    """Find all directed call paths from this symbol to a target symbol."""
    resolved_target = target_id if target_id is not None else target_symbol_id
    if resolved_target is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Query parameter 'target_id' is required",
        )
    return service.find_paths(
        db,
        source_symbol_id=symbol_id,
        target_symbol_id=resolved_target,
        max_depth=max_depth,
    )
