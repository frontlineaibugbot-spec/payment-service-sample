"""
payment-service-sample

Entry point — exposes `app` for:
    uvicorn main:app --reload
"""

from app.main import app  # noqa: F401
