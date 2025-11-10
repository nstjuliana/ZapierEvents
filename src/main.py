"""
Module: main.py
Description: FastAPI application entry point for Zapier Triggers API.
"""

from fastapi import FastAPI
from mangum import Mangum

app = FastAPI(
    title="Zapier Triggers API",
    description="Event ingestion and delivery API",
    version="0.1.0"
)

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "message": "Hello World",
        "version": "0.1.0"
    }

# Lambda handler
handler = Mangum(app, lifespan="off")

