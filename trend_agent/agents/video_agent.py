"""
VideoAgent - AI 视频生成协调 Agent
"""

import asyncio
import logging
from typing import Dict, Optional

from trend_agent.agents.base import BaseAgent
from trend_agent.config.settings import settings
from trend_agent.context.prompt_templates import video_prompt
from trend_agent.models.message import AgentMessage, VideoResult
from trend_agent.observability import metrics as obs
from trend_agent.video.base import BaseVideoGenerator
from trend_agent.video.keling_client import KeLingClient
from trend_agent.video.runway_client import RunwayClient
from trend_agent.video.pika_client import PikaClient

logger = logging.getLogger(__name__)

VIDEO_PROVIDERS: Dict[str, type] = {
    "keling": KeLingClient,
    "runway": RunwayClient,
    "pika": PikaClient,
}


class VideoAgent(BaseAgent):
    """AI 视频生成协调 Agent"""

    def __init__(self, llm_client):
        super().__init__("video")
        self._llm = llm_client
        self._providers: Dict[str, BaseVideoGenerator] = {}

    async def startup(self):
        await super().startup()
        for name, cls in VIDEO_PROVIDERS.items():
            self._providers[name] = cls()

    async def shutdown(self):
        for p in self._providers.values():
            await p.close()
        await super().shutdown()

    async def process(self, message: AgentMessage) -> AgentMessage:
        """
        payload 输入: {"draft": dict, "provider": str}
        payload 输出: {"video_url": str, "provider": str, "task_id": str, "status": str}
        """
        draft = message.payload.get("draft", {})
        provider_name = message.payload.get("provider") or settings.video.default_provider

        # Generate video prompt from content
        title = draft.get("title", "")
        summary = draft.get("summary", draft.get("body", "")[:200])
        category = draft.get("category", "")

        prompt_text = await self._generate_video_prompt(title, summary, category)

        # Try the requested provider, then fallback
        providers_to_try = [provider_name]
        if settings.video.fallback_enabled:
            for name in self._providers:
                if name != provider_name:
                    providers_to_try.append(name)

        for pname in providers_to_try:
            provider = self._providers.get(pname)
            if not provider:
                continue

            try:
                task_id = await provider.generate(prompt_text)
                video_url = await self._wait_for_completion(provider, task_id)

                if video_url:
                    obs.record_video(pname, "success")
                    return message.create_reply("video", {
                        "video_url": video_url,
                        "provider": pname,
                        "task_id": task_id,
                        "status": "completed",
                    })
                else:
                    obs.record_video(pname, "failed")
            except Exception as e:
                self.logger.warning("Video generation failed with %s: %s", pname, e)
                obs.record_video(pname, "error")
                if not settings.video.fallback_enabled:
                    return message.create_error("video_error", str(e))

        return message.create_error("video_error", "All video providers failed")

    async def _generate_video_prompt(self, title: str, summary: str, category: str) -> str:
        """Use LLM to generate an English video prompt."""
        prompt = video_prompt(title, summary, category)
        try:
            result = await self._llm.generate_sync(prompt, max_tokens=256)
            return result.strip()
        except Exception as e:
            self.logger.warning("Failed to generate video prompt via LLM: %s", e)
            return f"A professional news segment about: {title}. Modern, informative style."

    async def _wait_for_completion(
        self, provider: BaseVideoGenerator, task_id: str,
    ) -> Optional[str]:
        """Poll for video completion."""
        max_wait = settings.video.poll_max_wait_seconds
        interval = settings.video.poll_interval_seconds
        elapsed = 0

        while elapsed < max_wait:
            await asyncio.sleep(interval)
            elapsed += interval
            status, video_url = await provider.poll_status(task_id)

            if status == "completed" and video_url:
                return video_url
            elif status == "failed":
                return None

        self.logger.warning("Video generation timed out after %ds", max_wait)
        return None
