"""FastAPI application entrypoint for Automated Code Vulnerability Reviewer."""

import logging
from pathlib import Path
import sys

# Ensure workspace root is in sys.path when running `python src/main.py` directly
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from src.core.config import get_settings
from src.core.models import HealthResponse
from src.api.routes.ingest import router as ingest_router
from src.api.routes.context import router as context_router
from src.api.routes.review import router as review_router
from src.api.routes.history import router as history_router
from src.api.routes.reports import router as reports_router
from src.dashboard.router import router as dashboard_router

logger = logging.getLogger("reviewer")
settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="Automated Code Vulnerability Reviewer with AST-guided context extraction and LLM analysis.",
    version="1.0.0",
)

# Register route modules
app.include_router(ingest_router)
app.include_router(context_router)
app.include_router(review_router)
app.include_router(history_router)
app.include_router(reports_router)
app.include_router(dashboard_router)

# Mount static assets for web dashboard
dashboard_static_dir = Path(__file__).parent / "dashboard" / "static"
if dashboard_static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(dashboard_static_dir)), name="static")
    app.mount("/dashboard/static", StaticFiles(directory=str(dashboard_static_dir)), name="dashboard_static")
    assets_dir = dashboard_static_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets/aistudio", StaticFiles(directory=str(assets_dir)), name="aistudio_assets")
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")


@app.get("/style.css", include_in_schema=False)
async def get_root_style():
    """Fallback route for style.css."""
    return FileResponse(str(dashboard_static_dir / "style.css"), media_type="text/css")


@app.get("/app.js", include_in_schema=False)
async def get_root_app_js():
    """Fallback route for app.js."""
    return FileResponse(str(dashboard_static_dir / "app.js"), media_type="application/javascript")

# Provide compatibility property for Starlette _IncludedRouter
for _r in app.routes:
    if type(_r).__name__ == "_IncludedRouter" and not hasattr(type(_r), "path"):
        setattr(type(_r), "path", property(lambda self: getattr(self.original_router, "prefix", "")))
        break

# Enable CORS for local dashboards and frontends
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def global_exception_handling_middleware(request: Request, call_next):
    """Catch unhandled exceptions and return formatted JSON error response."""
    try:
        return await call_next(request)
    except Exception as exc:
        logger.exception("Unhandled server error: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"error": str(exc), "status_code": 500},
        )


@app.get("/", include_in_schema=False)
async def root_redirect():
    """Redirect root path to Web Dashboard."""
    return RedirectResponse(url="/dashboard")


@app.get("/health", response_model=HealthResponse, tags=["Health"])
@app.get("/api/v1/health", response_model=HealthResponse, tags=["Health"])
async def health_check() -> HealthResponse:
    """Service health and readiness check endpoint."""
    return HealthResponse(
        status="ok",
        version="1.0.0",
        app_name=settings.app_name,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        reload=True if settings.app_env == "development" else False,
    )

