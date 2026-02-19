"""
YouTube 数据抓取器 - 使用 YouTube Data API v3
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from trend_agent.config.settings import settings
from trend_agent.models.message import TrendItem
from trend_agent.scrapers.base import BaseScraper
from trend_agent.services.dedup import content_hash

logger = logging.getLogger(__name__)


class YouTubeScraper(BaseScraper):
    """YouTube Data API v3 抓取器"""

    name = "youtube"
    BASE_URL = "https://www.googleapis.com/youtube/v3"

    async def scrape(self, query: Optional[str] = None, limit: int = 50) -> List[TrendItem]:
        if not settings.scraper.youtube_api_key:
            logger.warning("YouTube API key not configured, skipping")
            return []

        session = await self._get_session()
        items: List[TrendItem] = []

        try:
            if query:
                # Search videos by query
                video_ids = await self._search_videos(session, query, limit)
            else:
                # Get trending/popular videos
                video_ids = await self._get_popular_videos(session, limit)

            if not video_ids:
                return []

            # Get video details with statistics
            details = await self._get_video_details(session, video_ids)
            for video in details:
                snippet = video.get("snippet", {})
                stats = video.get("statistics", {})
                engagement = (
                    int(stats.get("viewCount", 0)) / 100
                    + int(stats.get("likeCount", 0))
                    + int(stats.get("commentCount", 0)) * 2
                )
                title = snippet.get("title", "")
                desc = snippet.get("description", "")

                items.append(TrendItem(
                    source_platform="youtube",
                    source_id=video["id"],
                    source_url=f"https://www.youtube.com/watch?v={video['id']}",
                    title=title,
                    description=desc[:500],
                    author=snippet.get("channelTitle", ""),
                    author_id=snippet.get("channelId", ""),
                    language=snippet.get("defaultAudioLanguage", snippet.get("defaultLanguage", "en")),
                    engagement_score=float(engagement),
                    media_urls=[snippet.get("thumbnails", {}).get("high", {}).get("url", "")],
                    scraped_at=datetime.now(timezone.utc).isoformat(),
                    raw_data=video,
                    content_hash=content_hash(title + desc),
                ))

        except Exception as e:
            logger.error("YouTube scraping failed: %s", e, exc_info=True)

        logger.info("YouTube scraped %d items", len(items))
        return items

    async def _search_videos(self, session, query: str, limit: int) -> List[str]:
        params = {
            "key": settings.scraper.youtube_api_key,
            "part": "id",
            "q": query,
            "type": "video",
            "order": "viewCount",
            "maxResults": min(limit, 50),
            "regionCode": settings.scraper.youtube_region_code,
        }
        async with session.get(f"{self.BASE_URL}/search", params=params) as resp:
            if resp.status != 200:
                logger.error("YouTube search failed: %d", resp.status)
                return []
            data = await resp.json()
            return [item["id"]["videoId"] for item in data.get("items", []) if "videoId" in item.get("id", {})]

    async def _get_popular_videos(self, session, limit: int) -> List[str]:
        params = {
            "key": settings.scraper.youtube_api_key,
            "part": "id",
            "chart": "mostPopular",
            "maxResults": min(limit, 50),
            "regionCode": settings.scraper.youtube_region_code,
        }
        async with session.get(f"{self.BASE_URL}/videos", params=params) as resp:
            if resp.status != 200:
                logger.error("YouTube popular failed: %d", resp.status)
                return []
            data = await resp.json()
            return [item["id"] for item in data.get("items", [])]

    async def _get_video_details(self, session, video_ids: List[str]) -> List[Dict]:
        params = {
            "key": settings.scraper.youtube_api_key,
            "part": "snippet,statistics",
            "id": ",".join(video_ids[:50]),
        }
        async with session.get(f"{self.BASE_URL}/videos", params=params) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            return data.get("items", [])

    async def health_check(self) -> Dict:
        if not settings.scraper.youtube_api_key:
            return {"status": "unconfigured", "source": "youtube"}
        try:
            session = await self._get_session()
            params = {
                "key": settings.scraper.youtube_api_key,
                "part": "id",
                "chart": "mostPopular",
                "maxResults": 1,
            }
            async with session.get(f"{self.BASE_URL}/videos", params=params) as resp:
                return {
                    "status": "healthy" if resp.status == 200 else "unhealthy",
                    "source": "youtube",
                    "http_status": resp.status,
                }
        except Exception as e:
            return {"status": "unhealthy", "source": "youtube", "error": str(e)}
