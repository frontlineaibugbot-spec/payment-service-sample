from fastapi import APIRouter

from app.config import SERVICE
from app.logger import push_log

router = APIRouter()


@router.get("/health")
def health():
    push_log("info", "Health check OK")
    return {"status": "ok", "service": SERVICE}
