"""
抓取器抽象基类
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

import aiohttp

from trend_agent.models.message import TrendItem
from trend_agent.config.settings import settings

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """数据源抓取器基类"""

    name: str = ""

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=settings.scraper.request_timeout_seconds)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    @abstractmethod
    async def scrape(self, query: Optional[str] = None, limit: int = 50) -> List[TrendItem]:
        """抓取热门内容"""
        ...

    @abstractmethod
    async def health_check(self) -> Dict:
        """检查数据源可用性"""
        ...

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
