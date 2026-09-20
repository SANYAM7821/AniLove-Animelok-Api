"""General HTML and payload parsers for anime sites."""

from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import unquote, urljoin

from bs4 import BeautifulSoup
from selectolax.parser import HTMLParser

from app.config import settings


def text(value: str | None) -> str:
    """Normalize visible text."""
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def absolutize(url: str | None) -> str | None:
    """Resolve relative URLs."""
    if not url:
        return None
    cleaned = html.unescape(url)
    if cleaned.startswith("//"):
        return f"https:{cleaned}"
    return urljoin(settings.normalized_base_url, cleaned)


def parse_genres(page_html: str) -> list[str]:
    """Extract genre names from visible navigation/footer links."""
    tree = HTMLParser(page_html)
    genres: list[str] = []
    for anchor in tree.css('a[href*="/genre/"]'):
        name = text(anchor.text())
        if name and name not in genres:
            genres.append(name)

    if not genres:
        # Fallback to standard list if scraping fails
        return [
            "Action", "Adventure", "Comedy", "Drama", "Fantasy",
            "Horror", "Mystery", "Romance", "Sci-Fi", "Supernatural"
        ]
    return genres


def extract_metadata_from_meta(page_html: str) -> dict[str, Any]:
    """Extract common SEO metadata from head tags."""
    soup = BeautifulSoup(page_html, "lxml")
    meta = {}

    og_title = soup.find("meta", property="og:title")
    if og_title:
        meta["title"] = text(og_title.get("content"))

    og_desc = soup.find("meta", property="og:description")
    if og_desc:
        meta["description"] = text(og_desc.get("content"))

    og_image = soup.find("meta", property="og:image")
    if og_image:
        meta["poster"] = absolutize(og_image.get("content"))

    return meta
