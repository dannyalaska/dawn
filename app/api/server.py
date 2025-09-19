from fastapi import FastAPI

from app.core.config import settings
from app.core.redis_client import redis_async

app = FastAPI(title="DAWN API")


@app.get("/health")
def health():
    return {"ok": True, "service": "api", "env": settings.ENV}


@app.get("/health/redis")
async def health_redis():
    pong = await redis_async.ping()
    return {"ok": bool(pong)}
