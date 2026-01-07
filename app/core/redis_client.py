import redis as r_sync
from redis.asyncio import from_url as aio_from_url

from .config import settings

redis_async = aio_from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
redis_sync = r_sync.from_url(settings.REDIS_URL, decode_responses=True)
redis_binary = r_sync.from_url(settings.REDIS_URL, decode_responses=False)
