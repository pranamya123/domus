"""
Health check endpoints.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    """Basic health check endpoint."""
    return {
        "status": "healthy",
        "service": "domus",
        "version": "0.1.0",
    }


@router.get("/ready")
async def readiness_check():
    """Readiness check for kubernetes/load balancers."""
    return {
        "status": "ready",
    }
