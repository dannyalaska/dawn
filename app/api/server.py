from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.excel import router as excel_router
from app.api.rag import router as rag_router
from app.core.config import settings
from app.core.redis_client import redis_async

app = FastAPI(title="DAWN API")

# Dev CORS (tighten in prod)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"ok": True, "service": "api", "env": settings.ENV}


@app.get("/version")
def version():
    return {"name": settings.APP_NAME, "env": settings.ENV}


@app.get("/health/redis")
async def health_redis():
    pong = await redis_async.ping()
    return {"ok": bool(pong)}


app.include_router(excel_router)
app.include_router(rag_router)
