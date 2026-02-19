"""
发布器抽象基类
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Optional

import aiohttp

from trend_agent.config.settings import settings
from trend_agent.models.message import ContentDraftMsg, PublishResult

logger = logging.getLogger(__name__)


class BasePublisher(ABC):
    """平台发布器基类"""

    name: str = ""

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
            )
        return self._session

    @abstractmethod
    async def publish(self, draft: Dict) -> PublishResult:
        """发布内容到平台"""
        ...

    @abstractmethod
    async def validate_auth(self) -> bool:
        """验证平台认证是否有效"""
        ...

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
