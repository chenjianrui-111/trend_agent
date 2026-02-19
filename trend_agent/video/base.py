"""
视频生成器抽象基类
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional, Tuple

import aiohttp


class BaseVideoGenerator(ABC):
    """AI 视频生成器基类"""

    name: str = ""

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=60),
            )
        return self._session

    @abstractmethod
    async def generate(self, prompt: str, config: Dict = None) -> str:
        """Submit video generation task. Returns task_id."""
        ...

    @abstractmethod
    async def poll_status(self, task_id: str) -> Tuple[str, Optional[str]]:
        """Poll task status. Returns (status, video_url)."""
        ...

    @abstractmethod
    async def health_check(self) -> Dict:
        ...

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
