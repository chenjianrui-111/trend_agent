"""
B站热门视频抓取器
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from trend_agent.config.settings import settings
from trend_agent.models.message import TrendItem
from trend_agent.scrapers.base import BaseScraper
from trend_agent.services.dedup import content_hash

logger = logging.getLogger(__name__)


class BilibiliScraper(BaseScraper):
    """B站热门 API 抓取器"""

    name = "bilibili"
    HOT_URL = "https://api.bilibili.com/x/web-interface/popular"
    SEARCH_URL = "https://api.bilibili.com/x/web-interface/search/type"

    async def scrape(
        self,
        query: Optional[str] = None,
        limit: int = 50,
        capture_mode: str = "hybrid",
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        sort_strategy: str = "hybrid",
    ) -> List[TrendItem]:
        session = await self._get_session()
        items: List[TrendItem] = []
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Referer": "https://www.bilibili.com",
        }
        if settings.scraper.bilibili_sessdata:
            headers["Cookie"] = f"SESSDATA={settings.scraper.bilibili_sessdata}"

        try:
            if query:
                params = {
                    "search_type": "video",
                    "keyword": query,
                    "page": 1,
                    "page_size": min(limit, 50),
                    "order": "totalrank",
                }
                url = self.SEARCH_URL
                source_channel = "bilibili_search"
            else:
                params = {"ps": min(limit, 50), "pn": 1}
                url = self.HOT_URL
                source_channel = "bilibili_popular"

            async with session.get(url, headers=headers, params=params) as resp:
                if resp.status != 200:
                    logger.error("Bilibili API failed: %d", resp.status)
                    return []
                data = await resp.json()

            video_list = data.get("data", {}).get("list", data.get("data", {}).get("result", []))
            if not video_list and isinstance(data.get("data"), dict):
                video_list = data["data"].get("list", [])

            for video in video_list[:limit]:
                stat = video.get("stat", video.get("play", {}))
                if isinstance(stat, dict):
                    views = stat.get("view", 0)
                    likes = stat.get("like", 0)
                    comments = stat.get("reply", stat.get("danmaku", 0))
                else:
                    views = int(stat) if stat else 0
                    likes = 0
                    comments = 0

                engagement = views / 100 + likes + comments * 2
                title = video.get("title", "")
                desc = video.get("desc", video.get("description", ""))
                bvid = video.get("bvid", "")
                pub_epoch = video.get("pubdate")
                published_at = ""
                if isinstance(pub_epoch, (int, float)) and pub_epoch > 0:
                    published_at = datetime.fromtimestamp(pub_epoch, tz=timezone.utc).isoformat()
                pic = video.get("pic", "")
                media_urls = [pic] if pic else []

                items.append(TrendItem(
                    source_platform="bilibili",
                    source_channel=source_channel,
                    source_type="video",
                    source_id=bvid or str(video.get("aid", "")),
                    source_url=f"https://www.bilibili.com/video/{bvid}" if bvid else "",
                    title=title,
                    description=desc[:500],
                    author=video.get("owner", {}).get("name", video.get("author", "")),
                    author_id=str(video.get("owner", {}).get("mid", video.get("mid", ""))),
                    language="zh",
                    engagement_score=float(engagement),
                    media_urls=media_urls,
                    published_at=published_at,
                    platform_metrics={
                        "view_count": views,
                        "like_count": likes,
                        "comment_count": comments,
                    },
                    scraped_at=datetime.now(timezone.utc).isoformat(),
                    raw_data=video,
                    content_hash=content_hash(title + desc),
                ))

        except Exception as e:
            logger.error("Bilibili scraping failed: %s", e, exc_info=True)

        logger.info("Bilibili scraped %d items", len(items))
        return items

    async def health_check(self) -> Dict:
        try:
            session = await self._get_session()
            async with session.get(self.HOT_URL, params={"ps": 1, "pn": 1}) as resp:
                return {
                    "status": "healthy" if resp.status == 200 else "unhealthy",
                    "source": "bilibili",
                }
        except Exception as e:
            return {"status": "unhealthy", "source": "bilibili", "error": str(e)}
