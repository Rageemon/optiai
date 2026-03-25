"""
FastAPI Application Entry Point — Step 5b
Bootstraps the ASGI application, attaches middleware, mounts the router,
and configures structured logging.

Run locally:
    uvicorn main:app --reload --port 8000

The interactive API docs are then available at:
    http://localhost:8000/docs      (Swagger UI)
    http://localhost:8000/redoc     (ReDoc)
"""

import logging
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    """Construct and configure the FastAPI application instance."""

    app = FastAPI(
        title="Neuro-Symbolic Multi-Domain Optimization Engine",
        description=(
            "An enterprise-grade backend that combines the probabilistic "
            "natural-language parsing of **Gemini LLMs** with the "
            "deterministic mathematical solving power of **Google OR-Tools**.\n\n"
            "## Supported domains\n"
            "| Domain | Status |\n"
            "|--------|--------|\n"
            "| SCHEDULING | ✅ Implemented (CP-SAT) |\n"
            "| ROUTING | 🔜 Planned |\n"
            "| ASSIGNMENT | 🔜 Planned |"
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # ---- CORS ---------------------------------------------------------------
    # Allow all origins for the MVP / local development.
    # Tighten ``allow_origins`` to specific domains before production deploy.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],       # Replace with ["https://your-frontend.com"] in prod
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---- Router -------------------------------------------------------------
    app.include_router(router)

    # ---- Startup / Shutdown hooks ------------------------------------------
    @app.on_event("startup")
    async def on_startup():
        logger.info("=" * 60)
        logger.info("  Neuro-Symbolic Optimization Engine  —  v1.0.0")
        logger.info("  Docs : http://localhost:8000/docs")
        logger.info("=" * 60)

    @app.on_event("shutdown")
    async def on_shutdown():
        logger.info("Application shutting down.")

    return app


# ---------------------------------------------------------------------------
# ASGI application instance (used by uvicorn)
# ---------------------------------------------------------------------------

app = create_app()


# ---------------------------------------------------------------------------
# Root redirect
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
async def root():
    return {
        "message": "Neuro-Symbolic Optimization Engine is running.",
        "docs":    "http://localhost:8000/docs",
        "health":  "http://localhost:8000/api/health",
    }
