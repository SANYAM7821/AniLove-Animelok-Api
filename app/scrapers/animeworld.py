"""AnimeWorld India scraper implementation."""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import quote, urljoin

from selectolax.parser import HTMLParser

from app.cache.memory import cache
from app.config import settings
from app.utils.exceptions import NotFoundError, StreamExtractionError
from app.utils.http import http_client

logger = logging.getLogger(__name__)


class AnimeworldScraper:
    """Scraper for AnimeWorld India (watchanimeworlds.com)."""

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or settings.normalized_base_url).rstrip("/")

    def url(self, path: str) -> str:
        """Build an absolute URL for the configured site."""
        return urljoin(f"{self.base_url}/", path.lstrip("/"))

    async def home(self) -> dict[str, Any]:
        """Scrape the home page sections."""

        async def factory() -> dict[str, Any]:
            html = await http_client.get_text(self.url("/"))
            return {
                "spotlight_anime": self._parse_grid(html, "Trending")[:5],
                "trending_anime": self._parse_grid(html, "Trending")[:10],
                "latest_episodes": self._parse_grid(html, "New Releases")[:20],
                "top_airing": self._parse_grid(html, "Popular")[:15],
                "most_popular": self._parse_grid(html, "Popular")[:20],
                "genres": self._parse_genres(html),
            }

        return await cache.get_or_set("home", factory)

    async def search(self, query: str) -> list[dict[str, Any]]:
        """Search anime by keyword."""

        key = f"search:{query.lower().strip()}"

        async def factory() -> list[dict[str, Any]]:
            html = await http_client.get_text(self.url(f"/?s={quote(query)}"))
            return self._parse_grid(html)

        return await cache.get_or_set(key, factory)

    async def category(self, category: str, page: int = 1) -> dict[str, Any]:
        """Scrape a category/listing page."""

        normalized = category.strip("/")
        key = f"category:{normalized}:{page}"

        async def factory() -> dict[str, Any]:
            separator = "&" if "?" in normalized else "?"
            path = f"/{normalized}{separator}page={page}" if page > 1 else f"/{normalized}"
            html = await http_client.get_text(self.url(path))
            return {"totalPages": self._parse_total_pages(html), "data": self._parse_grid(html)}

        return await cache.get_or_set(key, factory)

    async def info(self, anime_id: str) -> dict[str, Any]:
        """Return anime details."""

        key = f"info:{anime_id}"

        async def factory() -> dict[str, Any]:
            # AnimeWorld IDs are usually slugs.
            # We try series first, then movies.
            try:
                html = await http_client.get_text(self.url(f"/series/{anime_id}"))
            except Exception:
                try:
                    html = await http_client.get_text(self.url(f"/movies/{anime_id}"))
                except Exception:
                    raise NotFoundError(f"Anime not found: {anime_id}")

            return self._parse_detail(anime_id, html)

        return await cache.get_or_set(key, factory)

    async def episodes(self, anime_id: str) -> list[dict[str, Any]]:
        """Return episode list."""
        detail = await self.info(anime_id)
        return detail.get("episodes_list", [])

    @staticmethod
    def make_episode_id(anime_id: str, episode_number: int) -> str:
        """Encode an anime ID and episode number into one path-safe ID."""
        return f"{anime_id}__ep__{episode_number}"

    @staticmethod
    def split_episode_id(episode_id: str) -> tuple[str, int]:
        """Decode an episode ID from this API."""
        if "__ep__" in episode_id:
            anime_id, number = episode_id.rsplit("__ep__", 1)
            return anime_id, int(number)
        raise NotFoundError("episode_id must look like '<anime_id>__ep__<number>'")

    async def servers(self, episode_id: str) -> list[dict[str, Any]]:
        """Return available servers for an episode."""
        # For now, we only extract the main stream.
        # We can expand this if we find how the site lists backup players.
        return [
            {
                "server": "multi",
                "server_name": "Multi",
                "type": "sub", # Default to sub
                "server_id": 1
            }
        ]

    async def stream(self, episode_id: str, server: str = "multi") -> dict[str, Any]:
        """Resolve a stream URL."""
        provider_id, episode_number = self.split_episode_id(episode_id)

        # Try both /watch/ and /episode/ patterns
        watch_slug = f"{provider_id}-episode-{episode_number}"
        try:
            html = await http_client.get_text(self.url(f"/watch/{watch_slug}"))
        except Exception:
            try:
                html = await http_client.get_text(self.url(f"/episode/{watch_slug}"))
            except Exception:
                raise StreamExtractionError(f"Unable to load watch page for {watch_slug}")

        tree = HTMLParser(html)

        # Look for the iframe in common WordPress video players
        iframe = tree.css_first("iframe[src]")
        if not iframe:
             iframe = tree.css_first(".video-embed iframe, #video-player iframe, .player-embed iframe")

        stream_url = iframe.attributes.get("src") if iframe else None

        # Fallback: look for data-src or other common attributes
        if not stream_url and iframe:
            stream_url = iframe.attributes.get("data-src") or iframe.attributes.get("data-lazy-src")

        if not stream_url:
            # Check for direct video tags
            video = tree.css_first("video source")
            stream_url = video.attributes.get("src") if video else None

        if not stream_url:
            raise StreamExtractionError(f"No stream found for {watch_slug}")

        # Resolve relative URLs
        if stream_url.startswith("//"):
            stream_url = f"https:{stream_url}"
        elif stream_url.startswith("/"):
            stream_url = self.url(stream_url)

        return {
            "stream_url": stream_url,
            "subtitles": [],
            "audio_tracks": [],
            "intro": {},
            "outro": {},
            "qualities": [],
            "server": server,
            "headers": {"Referer": self.url(f"/watch/{watch_slug}")}
        }

    def _parse_grid(self, html: str, section: str | None = None) -> list[dict[str, Any]]:
        """Parse the WordPress-style grid with aggressive detection."""
        tree = HTMLParser(html)
        results = []

        # Target common WordPress anime theme containers
        # .post-card, article, .item, .result-item, etc.
        items = tree.css("article, .post-card, .item, .result-item, li.status-publish, .post-lst li")

        # If no containers, just find all anime links
        if not items:
            items = tree.css("a[href*='/series/'], a[href*='/movies/'], a[href*='/anime/']")

        for item in items:
            if item.tag == "a":
                link_node = item
            else:
                link_node = item.css_first("a[href*='/series/'], a[href*='/movies/'], a[href*='/anime/'], a.lnk-blk")

            if not link_node:
                continue

            href = link_node.attributes.get("href", "")
            if not href or any(x in href for x in ["/genre/", "/category/", "/tag/", "/author/"]):
                continue

            anime_id = href.rstrip("/").split("/")[-1]
            if not anime_id:
                continue

            # Aggressive Title Finding
            title = ""
            title_node = item.css_first(".entry-title, h2, h3, h4, .title")
            if title_node:
                title = title_node.text().strip()

            if not title:
                img_node = item.css_first("img")
                title = img_node.attributes.get("alt", "").strip() if img_node else ""

            if not title and item.tag == "a":
                title = item.text().strip()

            img_node = item.css_first("img")
            poster = None
            if img_node:
                poster = img_node.attributes.get("src") or img_node.attributes.get("data-src") or img_node.attributes.get("data-lazy-src")

            results.append({
                "anime_id": anime_id,
                "title": title or anime_id,
                "poster": poster,
                "type": "movie" if "/movie" in href else "series"
            })

        return results

    def _parse_detail(self, anime_id: str, html: str) -> dict[str, Any]:
        """Parse the anime detail page with safety fallbacks."""
        tree = HTMLParser(html)

        title_node = tree.css_first(".entry-title, h1, .title")
        title = title_node.text().strip() if title_node else anime_id

        img_node = tree.css_first(".post-thumbnail img, .poster img, .anime-poster img")
        poster = None
        if img_node:
            poster = img_node.attributes.get("src") or img_node.attributes.get("data-src")

        desc_node = tree.css_first(".description, .entry-content p, .synopsis")
        description = desc_node.text().strip() if desc_node else ""

        anilist_id = None
        match = re.search(r"anilist\.co/anime/(\d+)", html)
        if match:
            anilist_id = int(match.group(1))

        episodes = []
        # Find all watch/episode links
        for ep_node in tree.css("a[href*='/episode/'], a[href*='/watch/'], .episode-link"):
            ep_href = ep_node.attributes.get("href", "")
            if not ep_href or "/series/" in ep_href:
                continue

            ep_id = ep_href.rstrip("/").split("/")[-1]
            # Try to extract episode number
            num_match = re.search(r"episode-(\d+)", ep_id)
            ep_num = int(num_match.group(1)) if num_match else 1

            episodes.append({
                "episode_id": ep_id,
                "number": ep_num,
                "title": ep_node.text().strip() or f"Episode {ep_num}"
            })

        return {
            "anime_id": anime_id,
            "title": title,
            "poster": poster,
            "synopsis": description,
            "anilist_id": anilist_id,
            "episodes_list": sorted(episodes, key=lambda x: x["number"])
        }

    def _parse_genres(self, html: str) -> list[str]:
        tree = HTMLParser(html)
        genres = []
        for a in tree.css("a[href*='/genre/']"):
            g = a.text().strip()
            if g and g not in genres:
                genres.append(g)
        return genres or ["Action", "Adventure", "Comedy"]

    def _parse_total_pages(self, html: str) -> int:
        tree = HTMLParser(html)
        pages = [int(a.text()) for a in tree.css(".pagination a, .page-numbers") if a.text().isdigit()]
        return max(pages) if pages else 1
