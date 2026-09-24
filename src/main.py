from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from src.api.routes import api_keys, charts, fundamentals, health, instruments, macro, prices, runs
from src.core.config import settings
from src.core.logger import get_logger

logger = get_logger(__name__)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"

API_V1_PREFIX = "/v1"

app = FastAPI(title="Finance Data Platform API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=False,  # must be False when allow_origins can be "*"
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def spa_no_cache(request: Request, call_next):
    """The SPA entry (index.html) must always be revalidated so a fresh deploy's
    new hashed bundle is picked up without a manual hard refresh. Content-hashed
    assets under /app/assets/ stay cacheable (their name changes on each build).
    """
    response = await call_next(request)
    path = request.url.path
    if path in ("/app", "/app/") or path.endswith(".html"):
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catches anything that isn't already an HTTPException/validation error
    (those get FastAPI's own handlers, which run first) -- a raw Postgres/S3
    error no longer leaks a stack trace to the client, just a generic 500.
    The real detail still goes to the logs.
    """
    logger.error("Unhandled exception on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.include_router(health.router)
app.include_router(api_keys.router)
app.include_router(instruments.router, prefix=API_V1_PREFIX)
app.include_router(prices.router, prefix=API_V1_PREFIX)
app.include_router(fundamentals.router, prefix=API_V1_PREFIX)
app.include_router(macro.router, prefix=API_V1_PREFIX)
app.include_router(runs.router, prefix=API_V1_PREFIX)
app.include_router(charts.router, prefix=API_V1_PREFIX)

if FRONTEND_DIR.is_dir():
    app.mount("/app", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
else:
    logger.warning("frontend/dist not found -- run `npm run build` in frontend/ to serve the UI at /app")
