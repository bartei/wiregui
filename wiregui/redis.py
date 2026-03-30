import redis.asyncio as redis

from wiregui.config import get_settings

pool = redis.ConnectionPool.from_url(get_settings().redis_url)


def get_redis() -> redis.Redis:
    return redis.Redis(connection_pool=pool)
