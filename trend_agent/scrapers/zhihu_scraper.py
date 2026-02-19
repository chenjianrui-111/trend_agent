"""
知乎热榜抓取器
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from trend_agent.models.message import TrendItem
from trend_agent.scrapers.base import BaseScraper
from trend_agent.services.dedup import content_hash

logger = logging.getLogger(__name__)


class ZhihuScraper(BaseScraper):
    """知乎热榜抓取器"""

    name = "zhihu"
    HOT_URL = "https://www.zhihu.com/api/v3/feed/topstory/hot-lists/total"

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
            "Accept": "application/json",
        }

        try:
            params = {"limit": min(limit, 50)}
            async with session.get(self.HOT_URL, headers=headers, params=params) as resp:
                if resp.status != 200:
                    logger.error("Zhihu API failed: %d", resp.status)
                    return []
                data = await resp.json()

            for item in data.get("data", [])[:limit]:
                target = item.get("target", {})
                title = target.get("title", "")
                excerpt = target.get("excerpt", "")
                hot_score = item.get("detail_text", "0")
                # Parse "1234 万热度" format
                try:
                    score = float(hot_score.replace("万热度", "").replace("热度", "").strip()) * 10000
                except (ValueError, AttributeError):
                    score = 0.0

                question_id = str(target.get("id", ""))
                created_epoch = target.get("created")
                published_at = ""
                if isinstance(created_epoch, (int, float)) and created_epoch > 0:
                    published_at = datetime.fromtimestamp(created_epoch, tz=timezone.utc).isoformat()

                items.append(TrendItem(
                    source_platform="zhihu",
                    source_channel="zhihu_hot_list",
                    source_type="question",
                    source_id=question_id,
                    source_url=f"https://www.zhihu.com/question/{question_id}",
                    title=title,
                    description=excerpt[:500],
                    author=target.get("author", {}).get("name", "知乎"),
                    language="zh",
                    engagement_score=score,
                    published_at=published_at,
                    platform_metrics={"hot_score_raw": hot_score},
                    scraped_at=datetime.now(timezone.utc).isoformat(),
                    raw_data=item,
                    content_hash=content_hash(title + excerpt),
                ))

        except Exception as e:
            logger.error("Zhihu scraping failed: %s", e, exc_info=True)

        logger.info("Zhihu scraped %d items", len(items))
        return items

    async def health_check(self) -> Dict:
        try:
            session = await self._get_session()
            async with session.get(self.HOT_URL, params={"limit": 1}) as resp:
                return {
                    "status": "healthy" if resp.status == 200 else "unhealthy",
                    "source": "zhihu",
                }
        except Exception as e:
            return {"status": "unhealthy", "source": "zhihu", "error": str(e)}
