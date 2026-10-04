from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.code_intelligence import (
    CalleeResponse,
    CallerResponse,
    ImpactAnalysisResponse,
    SymbolDependencyItem,
    SymbolDetailResponse,
    SymbolHistoryResponse,
    SymbolPathsResponse,
)
from app.services.code_intelligence.evolution_service import (
    GitEvolutionService,
    git_evolution_service,
)
from app.services.code_intelligence.graph_service import (
    GraphService,
    graph_service,
)
from app.services.code_intelligence.impact_service import (
    ImpactAnalysisService,
    impact_analysis_service,
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


@router.get(
    "/{symbol_id}/impact",
    response_model=ImpactAnalysisResponse,
    summary="Analyze change impact for a symbol",
)
def get_symbol_impact(
    symbol_id: int,
    max_depth: int = Query(default=10, ge=1, le=50, description="Maximum number of call hops/edges"),
    db: Session = Depends(get_db),
    impact_svc: ImpactAnalysisService = Depends(lambda: impact_analysis_service),
):
    """Deterministically analyze what code (symbols, files, tests, APIs, databases) may be affected if this symbol changes."""
    return impact_svc.analyze_symbol_impact(
        db,
        symbol_id=symbol_id,
        max_depth=max_depth,
    )


@router.get(
    "/{symbol_id}/history",
    response_model=SymbolHistoryResponse,
    summary="Get symbol evolution history",
)
def get_symbol_history(
    symbol_id: int,
    db: Session = Depends(get_db),
    evolution_svc: GitEvolutionService = Depends(lambda: git_evolution_service),
):
    """Retrieve commit evolution history and change timeline for a symbol."""
    return evolution_svc.get_symbol_history(db, symbol_id=symbol_id)

