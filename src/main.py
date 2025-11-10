"""
Module: main.py
Description: FastAPI application entry point for Zapier Triggers API.

Initializes the FastAPI application with all routes, middleware,
and error handlers for the Triggers API.
"""

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

from handlers.events import router as events_router
from handlers.inbox import router as inbox_router
from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Zapier Triggers API",
    description="Event ingestion and delivery API for real-time automation",
    version="0.1.0",
    docs_url="/docs",  # Swagger UI
    redoc_url="/redoc"  # ReDoc
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(events_router)
app.include_router(inbox_router)


@app.get("/health")
async def health_check():
    """
    Health check endpoint.

    Returns basic application health information.
    In future versions, this could include database connectivity checks.
    """
    logger.info("Health check requested")

    return {
        "status": "ok",
        "message": "Triggers API is healthy",
        "version": settings.app_version,
        "environment": settings.stage
    }


# Global exception handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """
    Global HTTP exception handler.

    Logs HTTP exceptions and returns structured error responses.
    """
    logger.warning(
        "HTTP exception occurred",
        status_code=exc.status_code,
        detail=exc.detail,
        path=request.url.path,
        method=request.method
    )

    return {
        "error": {
            "code": exc.status_code,
            "message": exc.detail,
            "type": "http_exception"
        }
    }


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """
    Global exception handler for unhandled errors.

    Logs unexpected exceptions and returns generic error responses.
    """
    logger.error(
        "Unhandled exception occurred",
        error=str(exc),
        error_type=type(exc).__name__,
        path=request.url.path,
        method=request.method
    )

    return {
        "error": {
            "code": 500,
            "message": "Internal server error",
            "type": "internal_error"
        }
    }


# Startup event
@app.on_event("startup")
async def startup_event():
    """Application startup event handler."""
    logger.info(
        "Starting Triggers API",
        version=settings.app_version,
        stage=settings.stage,
        region=settings.aws_region
    )


# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown event handler."""
    logger.info("Shutting down Triggers API")


# Lambda handler
handler = Mangum(app, lifespan="off")

