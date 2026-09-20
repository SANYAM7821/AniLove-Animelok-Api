"""HTTP client utilities."""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Mapping
from typing import Any

import httpx
from fake_useragent import UserAgent

from app.config import settings
from app.utils.exceptions import ScraperError

logger = logging.getLogger(__name__)


class HttpClient:
    """Shared async HTTP client with rotating headers and proxy support."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._ua = UserAgent()

    def _get_proxy(self) -> str | None:
        """Pick a random proxy from the configured list."""
        if not settings.use_proxy or not settings.proxy_list:
            return None

        proxies = [p.strip() for p in settings.proxy_list.split(",") if p.strip()]
        return random.choice(proxies) if proxies else None

    async def start(self) -> None:
        """Create the underlying AsyncClient with optional proxy."""

        if self._client is not None:
            return

        proxy = self._get_proxy()
        if proxy:
            logger.info(f"Starting HTTP client with proxy: {proxy[:15]}...")

        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.request_timeout),
            follow_redirects=True,
            proxy=proxy,
        )

    async def close(self) -> None:
        """Close the underlying AsyncClient."""

        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def get_fresh_headers(self, referer: str | None = None) -> dict[str, str]:
        """Generate a fresh set of browser headers with a new User-Agent."""

        try:
            user_agent = self._ua.random
        except Exception:
            user_agent = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )

        headers = {
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }
        if referer:
            headers["Referer"] = referer
        return headers

    async def get_text(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> str:
        """GET a URL and return text."""

        response = await self.get(url, headers=headers, params=params)
        return response.text

    async def get_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        """GET a URL and return parsed JSON."""

        response = await self.get(url, headers=headers, params=params)
        return response.json()

    async def post_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        data: Mapping[str, Any] | None = None,
        json: Mapping[str, Any] | None = None,
    ) -> Any:
        """POST form data and return parsed JSON."""

        response = await self.post(url, headers=headers, data=data, json=json)
        return response.json()

    async def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> httpx.Response:
        """GET with rotating headers, retries and useful errors."""

        await self.start()
        assert self._client is not None

        # Merge default fresh headers with request-specific headers
        request_headers = self.get_fresh_headers()
        if headers:
            request_headers.update(headers)

        last_error: Exception | None = None
        for attempt in range(1, settings.request_retries + 1):
            try:
                response = await self._client.get(url, headers=request_headers, params=params)
                response.raise_for_status()
                return response
            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                last_error = exc
                logger.warning("GET failed", extra={"url": url, "attempt": attempt, "error": str(exc)})

                # If we get a 403 or 429, the proxy might be burnt.
                # Re-starting the client picks a new one from the list.
                if attempt < settings.request_retries:
                    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in {403, 429}:
                        await self.close()
                        await self.start()
                    await asyncio.sleep(0.5 * attempt)

        raise ScraperError(f"Failed to fetch {url}: {last_error}") from last_error

    async def post(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        data: Mapping[str, Any] | None = None,
        json: Mapping[str, Any] | None = None,
    ) -> httpx.Response:
        """POST with rotating headers, retries and useful errors."""

        await self.start()
        assert self._client is not None

        request_headers = self.get_fresh_headers()
        if headers:
            request_headers.update(headers)

        last_error: Exception | None = None
        for attempt in range(1, settings.request_retries + 1):
            try:
                response = await self._client.post(url, headers=request_headers, data=data, json=json)
                response.raise_for_status()
                return response
            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                last_error = exc
                logger.warning("POST failed", extra={"url": url, "attempt": attempt, "error": str(exc)})
                if attempt < settings.request_retries:
                    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in {403, 429}:
                        await self.close()
                        await self.start()
                    await asyncio.sleep(0.5 * attempt)
        raise ScraperError(f"Failed to post {url}: {last_error}") from last_error


http_client = HttpClient()
