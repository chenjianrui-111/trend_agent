"""
Twitter/X 数据抓取器 - 使用 X API v2
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from trend_agent.config.settings import settings
from trend_agent.models.message import TrendItem
from trend_agent.scrapers.base import BaseScraper
from trend_agent.services.dedup import content_hash

logger = logging.getLogger(__name__)


class TwitterScraper(BaseScraper):
    """Twitter/X API v2 抓取器"""

    name = "twitter"
    BASE_URL = "https://api.twitter.com/2"

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {settings.scraper.twitter_bearer_token}",
        }

    async def scrape(self, query: Optional[str] = None, limit: int = 50) -> List[TrendItem]:
        if not settings.scraper.twitter_bearer_token:
            logger.warning("Twitter bearer token not configured, skipping")
            return []

        session = await self._get_session()
        items: List[TrendItem] = []

        # Search recent tweets
        search_query = query or "trending lang:zh OR lang:en"
        params = {
            "query": search_query,
            "max_results": min(limit, 100),  # API max is 100
            "tweet.fields": "created_at,public_metrics,author_id,lang",
            "expansions": "author_id",
            "user.fields": "name,username",
        }

        try:
            async with session.get(
                f"{self.BASE_URL}/tweets/search/recent",
                headers=self._headers(),
                params=params,
            ) as resp:
                if resp.status == 401:
                    logger.error("Twitter API authentication failed")
                    return []
                if resp.status == 429:
                    logger.warning("Twitter API rate limited")
                    return []
                if resp.status >= 400:
                    text = await resp.text()
                    logger.error("Twitter API error %d: %s", resp.status, text[:200])
                    return []

                data = await resp.json()

            # Build author lookup
            authors = {}
            for user in data.get("includes", {}).get("users", []):
                authors[user["id"]] = {
                    "name": user.get("name", ""),
                    "username": user.get("username", ""),
                }

            for tweet in data.get("data", []):
                metrics = tweet.get("public_metrics", {})
                engagement = (
                    metrics.get("like_count", 0)
                    + metrics.get("retweet_count", 0) * 2
                    + metrics.get("reply_count", 0)
                )
                author_info = authors.get(tweet.get("author_id", ""), {})
                text = tweet.get("text", "")

                items.append(TrendItem(
                    source_platform="twitter",
                    source_id=tweet["id"],
                    source_url=f"https://twitter.com/i/web/status/{tweet['id']}",
                    title=text[:100],
                    description=text,
                    author=author_info.get("name", ""),
                    author_id=tweet.get("author_id", ""),
                    language=tweet.get("lang", "en"),
                    engagement_score=float(engagement),
                    scraped_at=datetime.now(timezone.utc).isoformat(),
                    raw_data=tweet,
                    content_hash=content_hash(text),
                ))

        except Exception as e:
            logger.error("Twitter scraping failed: %s", e, exc_info=True)

        logger.info("Twitter scraped %d items", len(items))
        return items

    async def health_check(self) -> Dict:
        if not settings.scraper.twitter_bearer_token:
            return {"status": "unconfigured", "source": "twitter"}
        try:
            session = await self._get_session()
            async with session.get(
                f"{self.BASE_URL}/tweets/search/recent",
                headers=self._headers(),
                params={"query": "test", "max_results": 10},
            ) as resp:
                return {
                    "status": "healthy" if resp.status == 200 else "unhealthy",
                    "source": "twitter",
                    "http_status": resp.status,
                }
        except Exception as e:
            return {"status": "unhealthy", "source": "twitter", "error": str(e)}
