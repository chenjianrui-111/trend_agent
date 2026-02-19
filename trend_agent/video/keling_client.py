"""
可灵 AI 视频生成客户端
"""

import hashlib
import hmac
import json
import logging
import time
from typing import Dict, Optional, Tuple

from trend_agent.config.settings import settings
from trend_agent.video.base import BaseVideoGenerator

logger = logging.getLogger(__name__)


class KeLingClient(BaseVideoGenerator):
    """可灵 AI (KLing) 视频生成 API 客户端"""

    name = "keling"

    def __init__(self):
        super().__init__()
        self.base_url = settings.video.keling_base_url.rstrip("/")
        self._access_key = settings.video.keling_access_key
        self._secret_key = settings.video.keling_secret_key

    def _auth_headers(self) -> Dict[str, str]:
        # KeLing uses JWT-like auth with access_key + secret_key
        timestamp = str(int(time.time()))
        sign_str = f"{self._access_key}{timestamp}"
        signature = hmac.new(
            self._secret_key.encode(), sign_str.encode(), hashlib.sha256
        ).hexdigest()
        return {
            "Authorization": f"Bearer {self._access_key}",
            "X-Timestamp": timestamp,
            "X-Signature": signature,
            "Content-Type": "application/json",
        }

    async def generate(self, prompt: str, config: Dict = None) -> str:
        """Submit video generation task to KeLing."""
        if not self._access_key or not self._secret_key:
            raise ValueError("KeLing credentials not configured")

        session = await self._get_session()
        payload = {
            "prompt": prompt,
            "model_name": (config or {}).get("model", "kling-v1"),
            "cfg_scale": (config or {}).get("cfg_scale", 0.5),
            "mode": (config or {}).get("mode", "std"),  # std or pro
            "duration": (config or {}).get("duration", "5"),  # seconds
        }

        async with session.post(
            f"{self.base_url}/videos/text2video",
            json=payload,
            headers=self._auth_headers(),
        ) as resp:
            data = await resp.json()
            if resp.status >= 400:
                raise ValueError(f"KeLing API error: {data}")
            task_id = data.get("data", {}).get("task_id", "")
            if not task_id:
                raise ValueError(f"KeLing returned no task_id: {data}")
            return task_id

    async def poll_status(self, task_id: str) -> Tuple[str, Optional[str]]:
        """Poll KeLing task status."""
        session = await self._get_session()
        async with session.get(
            f"{self.base_url}/videos/text2video/{task_id}",
            headers=self._auth_headers(),
        ) as resp:
            data = await resp.json()
            task_data = data.get("data", {})
            status = task_data.get("task_status", "processing")

            if status == "succeed":
                videos = task_data.get("task_result", {}).get("videos", [])
                video_url = videos[0].get("url", "") if videos else ""
                return "completed", video_url
            elif status == "failed":
                return "failed", None
            else:
                return "processing", None

    async def health_check(self) -> Dict:
        if not self._access_key:
            return {"status": "unconfigured", "provider": "keling"}
        return {"status": "configured", "provider": "keling"}
