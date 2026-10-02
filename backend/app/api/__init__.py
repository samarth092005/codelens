from fastapi import APIRouter
from app.api.routes import files, health, repositories, symbols, users

api_router = APIRouter()

# API v1 routes
api_router.include_router(repositories.router)
api_router.include_router(symbols.router)
api_router.include_router(files.router)
api_router.include_router(users.router)
api_router.include_router(health.router)

__all__ = ["api_router"]
