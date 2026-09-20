"""
Leadyfy OS — FastAPI application entrypoint.

Run locally with:
    uvicorn app.main:app --reload

Swagger UI: http://localhost:8000/docs
"""
import logging

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.config import settings
from app.database import Base, engine
from app.models import *  # noqa: F401,F403  (ensures every model is registered on Base.metadata)
from app.routers import (
    auth,
    clients,
    creators,
    dashboard,
    employees,
    finance,
    notifications,
    orders,
    scripts,
    shoots,
    support,
    tasks,
    videos,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("leadyfy")

app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "Leadyfy OS — Internal Agency Management & Operations SaaS backend. "
        "Covers the full UGC/Digital Marketing agency lifecycle: Lead/Client "
        "onboarding, Package/Order management, Scripting, Creator matching, "
        "Shoot scheduling, Video production pipeline, Client portal review, "
        "and Financials (Payments, Expenses, Creator Payouts)."
    ),
    version="1.0.0",
    contact={"name": "Leadyfy OS Backend"},
)

# --- CORS (spec section: "Configure CORS so the React frontend can communicate") ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Global error handling (never leak internal stack traces) --------------


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "Validation error", "errors": exc.errors()},
    )


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    logger.warning("Integrity error: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": "A database integrity constraint was violated (e.g. duplicate or invalid reference)."},
    )


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError):
    logger.error("Database error: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected database error occurred."},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected internal error occurred."},
    )


# --- DB init (prototype-grade: create_all instead of Alembic migrations) ---


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables ensured via create_all().")


# --- Health check ------------------------------------------------------------


@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "ok", "service": settings.APP_NAME, "environment": settings.ENVIRONMENT}


# --- Routers -------------------------------------------------------------------

app.include_router(auth.router)
app.include_router(employees.router)
app.include_router(clients.router)
app.include_router(orders.router)
app.include_router(scripts.router)
app.include_router(creators.router)
app.include_router(shoots.router)
app.include_router(videos.router)
app.include_router(tasks.router)
app.include_router(finance.router)
app.include_router(notifications.router)
app.include_router(support.router)
app.include_router(dashboard.router)
