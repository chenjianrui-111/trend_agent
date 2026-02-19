"""
微博热搜抓取器
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from trend_agent.config.settings import settings
from trend_agent.models.message import TrendItem
from trend_agent.scrapers.base import BaseScraper
from trend_agent.services.dedup import content_hash

logger = logging.getLogger(__name__)


class WeiboScraper(BaseScraper):
    """微博热搜 API 抓取器"""

    name = "weibo"
    HOT_SEARCH_URL = "https://weibo.com/ajax/side/hotSearch"

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

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "application/json",
            }
            if settings.scraper.weibo_access_token:
                headers["Authorization"] = f"Bearer {settings.scraper.weibo_access_token}"

            async with session.get(self.HOT_SEARCH_URL, headers=headers) as resp:
                if resp.status != 200:
                    logger.error("Weibo hot search failed: %d", resp.status)
                    return []
                data = await resp.json()

            realtime = data.get("data", {}).get("realtime", [])
            for i, item in enumerate(realtime[:limit]):
                word = item.get("word", "")
                note = item.get("note", word)
                raw_hot = item.get("raw_hot", item.get("num", 0))

                items.append(TrendItem(
                    source_platform="weibo",
                    source_channel="weibo_hot_search",
                    source_type="topic",
                    source_id=str(item.get("mid", f"weibo_{i}")),
                    source_url=f"https://s.weibo.com/weibo?q=%23{word}%23",
                    title=note,
                    description=f"微博热搜: {note}",
                    author="微博热搜",
                    language="zh",
                    engagement_score=float(raw_hot),
                    tags=[f"#{word}#"],
                    hashtags=[f"#{word}#"],
                    platform_metrics={"raw_hot": raw_hot},
                    scraped_at=datetime.now(timezone.utc).isoformat(),
                    raw_data=item,
                    content_hash=content_hash(word),
                ))

        except Exception as e:
            logger.error("Weibo scraping failed: %s", e, exc_info=True)

        logger.info("Weibo scraped %d items", len(items))
        return items

    async def health_check(self) -> Dict:
        try:
            session = await self._get_session()
            async with session.get(self.HOT_SEARCH_URL) as resp:
                return {
                    "status": "healthy" if resp.status == 200 else "unhealthy",
                    "source": "weibo",
                    "http_status": resp.status,
                }
        except Exception as e:
            return {"status": "unhealthy", "source": "weibo", "error": str(e)}
