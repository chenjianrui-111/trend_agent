"""
Pika Labs 视频生成客户端
"""

import logging
from typing import Dict, Optional, Tuple

from trend_agent.config.settings import settings
from trend_agent.video.base import BaseVideoGenerator

logger = logging.getLogger(__name__)


class PikaClient(BaseVideoGenerator):
    """Pika Labs API 客户端"""

    name = "pika"

    def __init__(self):
        super().__init__()
        self.base_url = settings.video.pika_base_url.rstrip("/")
        self._api_key = settings.video.pika_api_key

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def generate(self, prompt: str, config: Dict = None) -> str:
        """Submit video generation task to Pika."""
        if not self._api_key:
            raise ValueError("Pika API key not configured")

        session = await self._get_session()
        payload = {
            "prompt": prompt,
            "style": (config or {}).get("style", "realistic"),
            "duration": (config or {}).get("duration", 3),
            "aspect_ratio": (config or {}).get("ratio", "16:9"),
        }

        async with session.post(
            f"{self.base_url}/generate",
            json=payload,
            headers=self._headers(),
        ) as resp:
            data = await resp.json()
            if resp.status >= 400:
                raise ValueError(f"Pika API error: {data}")
            task_id = data.get("id", data.get("task_id", ""))
            if not task_id:
                raise ValueError(f"Pika returned no task id: {data}")
            return task_id

    async def poll_status(self, task_id: str) -> Tuple[str, Optional[str]]:
        """Poll Pika task status."""
        session = await self._get_session()
        async with session.get(
            f"{self.base_url}/generate/{task_id}",
            headers=self._headers(),
        ) as resp:
            data = await resp.json()
            status = data.get("status", "pending")

            if status in ("completed", "finished"):
                video_url = data.get("video_url", data.get("output_url", ""))
                return "completed", video_url
            elif status == "failed":
                return "failed", None
            else:
                return "processing", None

    async def health_check(self) -> Dict:
        if not self._api_key:
            return {"status": "unconfigured", "provider": "pika"}
        return {"status": "configured", "provider": "pika"}
