"""Small async wrapper around cachetools TTLCache."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

import orjson
from cachetools import TTLCache

from app.config import settings

logger = logging.getLogger(__name__)
T = TypeVar("T")

class AsyncCache:
    """A cache that uses Redis if REDIS_URL is set, otherwise falls back to local memory."""

    def __init__(self, maxsize: int = 512, ttl: int = settings.cache_ttl_seconds) -> None:
        self._local_cache: TTLCache[str, Any] = TTLCache(maxsize=maxsize, ttl=ttl)
        self._lock = asyncio.Lock()
        self._redis_url = settings.redis_url
        self._redis = None

    async def _get_redis(self):
        if not self._redis_url:
            return None
        if self._redis is None:
            try:
                import redis.asyncio as redis
                self._redis = redis.from_url(self._redis_url, decode_responses=False)
                await self._redis.ping()
                logger.info("Connected to Redis cache")
            except Exception as e:
                logger.warning(f"Failed to connect to Redis: {e}. Falling back to local memory.")
                self._redis = False # Mark as failed
        return self._redis if self._redis is not False else None

    async def get_or_set(self, key: str, factory: Callable[[], Coroutine[Any, Any, T]]) -> T:
        """Return a cached value or compute and store it."""

        # 1. Try Redis first
        redis_client = await self._get_redis()
        if redis_client:
            try:
                cached = await redis_client.get(key)
                if cached:
                    return orjson.loads(cached)
            except Exception as e:
                logger.warning(f"Redis get failed: {e}")

        # 2. Try Local Memory
        async with self._lock:
            if key in self._local_cache:
                return self._local_cache[key]

        # 3. Compute Value
        value = await factory()

        # 4. Save to Local Memory
        async with self._lock:
            self._local_cache[key] = value

        # 5. Save to Redis in background
        if redis_client:
            try:
                await redis_client.set(key, orjson.dumps(value), ex=settings.cache_ttl_seconds)
            except Exception as e:
                logger.warning(f"Redis set failed: {e}")

        return value

    async def clear(self) -> None:
        """Remove all cached entries."""
        async with self._lock:
            self._local_cache.clear()
        redis_client = await self._get_redis()
        if redis_client:
            try:
                await redis_client.flushdb()
            except Exception:
                pass

cache = AsyncCache()

