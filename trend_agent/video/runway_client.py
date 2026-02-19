"""
Runway ML 视频生成客户端
"""

import logging
from typing import Dict, Optional, Tuple

from trend_agent.config.settings import settings
from trend_agent.video.base import BaseVideoGenerator

logger = logging.getLogger(__name__)


class RunwayClient(BaseVideoGenerator):
    """Runway ML API 客户端"""

    name = "runway"

    def __init__(self):
        super().__init__()
        self.base_url = settings.video.runway_base_url.rstrip("/")
        self._api_key = settings.video.runway_api_key

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "X-Runway-Version": "2024-11-06",
        }

    async def generate(self, prompt: str, config: Dict = None) -> str:
        """Submit video generation task to Runway."""
        if not self._api_key:
            raise ValueError("Runway API key not configured")

        session = await self._get_session()
        payload = {
            "promptText": prompt,
            "model": (config or {}).get("model", "gen3a_turbo"),
            "duration": (config or {}).get("duration", 5),
            "ratio": (config or {}).get("ratio", "16:9"),
        }

        async with session.post(
            f"{self.base_url}/image_to_video",
            json=payload,
            headers=self._headers(),
        ) as resp:
            data = await resp.json()
            if resp.status >= 400:
                raise ValueError(f"Runway API error: {data}")
            task_id = data.get("id", "")
            if not task_id:
                raise ValueError(f"Runway returned no task id: {data}")
            return task_id

    async def poll_status(self, task_id: str) -> Tuple[str, Optional[str]]:
        """Poll Runway task status."""
        session = await self._get_session()
        async with session.get(
            f"{self.base_url}/tasks/{task_id}",
            headers=self._headers(),
        ) as resp:
            data = await resp.json()
            status = data.get("status", "PENDING")

            if status == "SUCCEEDED":
                output = data.get("output", [])
                video_url = output[0] if output else ""
                return "completed", video_url
            elif status in ("FAILED", "CANCELLED"):
                return "failed", None
            else:
                return "processing", None

    async def health_check(self) -> Dict:
        if not self._api_key:
            return {"status": "unconfigured", "provider": "runway"}
        return {"status": "configured", "provider": "runway"}
