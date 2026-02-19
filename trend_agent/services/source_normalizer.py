"""
Source normalization utilities.
"""

import html
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from trend_agent.models.message import TrendItem

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")
_URL_RE = re.compile(r"https?://[^\s]+")
_HASHTAG_RE = re.compile(r"#([^#\s]{1,80})#?")
_MENTION_RE = re.compile(r"@([A-Za-z0-9_\-\u4e00-\u9fff]{1,64})")


def _to_iso8601(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, (int, float)):
        if value <= 0:
            return ""
        return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return ""
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat()
        except ValueError:
            return ""
    return ""


def _clean_text(text: str) -> str:
    if not text:
        return ""
    cleaned = html.unescape(text)
    cleaned = _HTML_TAG_RE.sub(" ", cleaned)
    cleaned = _SPACE_RE.sub(" ", cleaned).strip()
    return cleaned


def _detect_media_type(url: str) -> str:
    lower = (url or "").lower()
    path = urlparse(lower).path
    if path.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp")):
        return "image"
    if path.endswith((".mp4", ".mov", ".webm", ".mkv", ".avi")):
        return "video"
    if "youtube.com" in lower or "youtu.be" in lower or "bilibili.com/video" in lower:
        return "video"
    return "unknown"


class SourceNormalizer:
    """Normalize platform payload into a unified text/media representation."""

    def normalize(self, item: TrendItem) -> TrendItem:
        title = _clean_text(item.title)
        description = _clean_text(item.description)
        merged = _clean_text(f"{title}\n{description}")

        raw_text = f"{title}\n{description}"
        urls = sorted(set(_URL_RE.findall(raw_text)))
        hashtags = sorted(
            set(item.hashtags + [f"#{tag}#" for tag in _HASHTAG_RE.findall(raw_text)])
        )
        mentions = sorted(set(item.mentions + [f"@{name}" for name in _MENTION_RE.findall(raw_text)]))

        media_assets: List[Dict[str, Any]] = []
        media_urls = [u for u in item.media_urls if u]
        for idx, url in enumerate(media_urls):
            media_assets.append(
                {
                    "id": f"{item.source_platform}:{item.source_id}:{idx}",
                    "url": url,
                    "media_type": _detect_media_type(url),
                    "origin": item.source_platform,
                }
            )

        published_at = item.published_at or self._infer_published_at(item)

        item.title = title
        item.description = description
        item.normalized_text = merged
        item.external_urls = sorted(set(item.external_urls + urls))
        item.hashtags = hashtags
        item.mentions = mentions
        item.media_assets = media_assets
        item.published_at = published_at
        item.scraped_at = item.scraped_at or datetime.now(timezone.utc).isoformat()
        return item

    def _infer_published_at(self, item: TrendItem) -> str:
        raw = item.raw_data or {}
        candidates = [
            raw.get("created_at"),
            raw.get("publishedAt"),
            raw.get("publish_time"),
            raw.get("pubdate"),
            raw.get("created"),
            raw.get("created_time"),
        ]
        if isinstance(raw.get("snippet"), dict):
            candidates.append(raw["snippet"].get("publishedAt"))
        if isinstance(raw.get("target"), dict):
            candidates.append(raw["target"].get("created"))

        for value in candidates:
            iso = _to_iso8601(value)
            if iso:
                return iso
        return item.scraped_at

