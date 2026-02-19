"""
ScraperAgent - 多源数据抓取协调 Agent
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional

from trend_agent.agents.base import BaseAgent
from trend_agent.config.settings import settings
from trend_agent.models.message import AgentMessage, TrendItem
from trend_agent.observability import metrics as obs
from trend_agent.scrapers.base import BaseScraper
from trend_agent.scrapers.twitter_scraper import TwitterScraper
from trend_agent.scrapers.youtube_scraper import YouTubeScraper
from trend_agent.scrapers.weibo_scraper import WeiboScraper
from trend_agent.scrapers.bilibili_scraper import BilibiliScraper
from trend_agent.scrapers.zhihu_scraper import ZhihuScraper
from trend_agent.services.dedup import DedupService

logger = logging.getLogger(__name__)

# Source name -> Scraper class
SCRAPER_REGISTRY: Dict[str, type] = {
    "twitter": TwitterScraper,
    "youtube": YouTubeScraper,
    "weibo": WeiboScraper,
    "bilibili": BilibiliScraper,
    "zhihu": ZhihuScraper,
}


class ScraperAgent(BaseAgent):
    """多源数据抓取协调 Agent"""

    def __init__(self):
        super().__init__("scraper")
        self._scrapers: Dict[str, BaseScraper] = {}
        self._dedup = DedupService()

    async def startup(self):
        await super().startup()
        for name in settings.scraper.enabled_sources:
            cls = SCRAPER_REGISTRY.get(name)
            if cls:
                self._scrapers[name] = cls()
            else:
                self.logger.warning("Unknown scraper source: %s", name)

    async def shutdown(self):
        for scraper in self._scrapers.values():
            await scraper.close()
        await super().shutdown()

    async def process(self, message: AgentMessage) -> AgentMessage:
        """
        payload 输入: {"sources": ["twitter", "youtube"], "query": "AI", "limit": 50}
        payload 输出: {"items": List[TrendItem_dict]}
        """
        sources = message.payload.get("sources", list(self._scrapers.keys()))
        query = message.payload.get("query")
        limit = message.payload.get("limit", 50)

        # Filter to only initialized scrapers
        active_scrapers = {
            name: scraper for name, scraper in self._scrapers.items()
            if name in sources
        }

        if not active_scrapers:
            return message.create_reply("scraper", {"items": [], "error": "No active scrapers"})

        # Run scrapers concurrently
        all_items: List[TrendItem] = []
        tasks = {}
        for name, scraper in active_scrapers.items():
            tasks[name] = asyncio.create_task(
                self._scrape_with_metrics(scraper, query, limit)
            )

        results = await asyncio.gather(*tasks.values(), return_exceptions=True)

        for name, result in zip(tasks.keys(), results):
            if isinstance(result, Exception):
                self.logger.error("Scraper %s failed: %s", name, result)
                obs.record_scrape(name, "error")
            else:
                all_items.extend(result)

        # Deduplicate
        self._dedup.clear()
        unique_items = []
        for item in all_items:
            text = item.title + item.description
            if not self._dedup.check_and_add(text):
                unique_items.append(item)

        # Sort by engagement score descending
        unique_items.sort(key=lambda x: x.engagement_score, reverse=True)

        # Convert to dicts for serialization
        items_data = []
        for item in unique_items[:limit]:
            items_data.append(item.__dict__)

        self.logger.info(
            "Scraping complete: %d raw -> %d unique items from %d sources",
            len(all_items), len(unique_items), len(active_scrapers),
        )

        return message.create_reply("scraper", {"items": items_data})

    async def _scrape_with_metrics(
        self, scraper: BaseScraper, query: Optional[str], limit: int,
    ) -> List[TrendItem]:
        start = time.perf_counter()
        try:
            items = await scraper.scrape(query=query, limit=limit)
            latency = time.perf_counter() - start
            obs.record_scrape(scraper.name, "success", latency)
            return items
        except Exception:
            latency = time.perf_counter() - start
            obs.record_scrape(scraper.name, "error", latency)
            raise

    async def get_scraper_health(self) -> Dict:
        results = {}
        for name, scraper in self._scrapers.items():
            results[name] = await scraper.health_check()
        return results
