from fastapi import FastAPI
from app.api import api_router
from app.api.routes import health
from app.core.config import settings

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
)

# Root-level health check endpoint (preserved for backward compatibility)
app.include_router(health.router)

# Versioned API routes (/api/v1/...)
app.include_router(api_router, prefix=settings.API_V1_STR)
