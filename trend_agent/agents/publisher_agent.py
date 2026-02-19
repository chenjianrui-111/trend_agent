"""
PublisherAgent - 多平台发布协调 Agent
"""

import asyncio
import logging
import time
from typing import Dict, List

from trend_agent.agents.base import BaseAgent
from trend_agent.models.message import AgentMessage, PublishResult
from trend_agent.observability import metrics as obs
from trend_agent.publishers.base import BasePublisher
from trend_agent.publishers.wechat_publisher import WechatPublisher
from trend_agent.publishers.xiaohongshu_publisher import XiaohongshuPublisher
from trend_agent.publishers.douyin_publisher import DouyinPublisher
from trend_agent.publishers.weibo_publisher import WeiboPublisher
from trend_agent.config.settings import settings

logger = logging.getLogger(__name__)

PUBLISHER_REGISTRY: Dict[str, type] = {
    "wechat": WechatPublisher,
    "xiaohongshu": XiaohongshuPublisher,
    "douyin": DouyinPublisher,
    "weibo": WeiboPublisher,
}


class PublisherAgent(BaseAgent):
    """多平台发布协调 Agent"""

    def __init__(self):
        super().__init__("publisher")
        self._publishers: Dict[str, BasePublisher] = {}

    async def startup(self):
        await super().startup()
        for name, cls in PUBLISHER_REGISTRY.items():
            self._publishers[name] = cls()

    async def shutdown(self):
        for pub in self._publishers.values():
            await pub.close()
        await super().shutdown()

    async def process(self, message: AgentMessage) -> AgentMessage:
        """
        payload 输入: {"drafts": List[dict]}
        payload 输出: {"publish_results": List[dict]}
        """
        drafts = message.payload.get("drafts", [])
        all_results: List[Dict] = []

        for draft in drafts:
            platform = draft.get("target_platform", "")
            publisher = self._publishers.get(platform)
            if not publisher:
                all_results.append(PublishResult(
                    draft_id=draft.get("draft_id", ""),
                    platform=platform,
                    success=False,
                    error=f"No publisher for platform: {platform}",
                ).__dict__)
                continue

            start = time.perf_counter()
            try:
                result = await self._publish_with_retry(publisher, draft)
                latency = time.perf_counter() - start
                obs.record_publish(platform, "success" if result.success else "failed", latency)
                all_results.append(result.__dict__)
            except Exception as e:
                latency = time.perf_counter() - start
                obs.record_publish(platform, "error", latency)
                all_results.append(PublishResult(
                    draft_id=draft.get("draft_id", ""),
                    platform=platform,
                    success=False,
                    error=str(e),
                ).__dict__)

        success_count = sum(1 for r in all_results if r.get("success"))
        self.logger.info("Published %d/%d drafts successfully", success_count, len(drafts))

        return message.create_reply("publisher", {"publish_results": all_results})

    async def _publish_with_retry(self, publisher: BasePublisher, draft: Dict) -> PublishResult:
        """Publish with retry logic."""
        max_retries = settings.publisher.publish_retry_max
        delay = settings.publisher.publish_retry_delay_seconds

        for attempt in range(1, max_retries + 1):
            result = await publisher.publish(draft)
            if result.success:
                return result
            if attempt < max_retries:
                self.logger.warning(
                    "Publish attempt %d failed for %s: %s, retrying...",
                    attempt, publisher.name, result.error,
                )
                await asyncio.sleep(delay * attempt)

        return result

    async def get_platform_health(self) -> Dict:
        results = {}
        for name, publisher in self._publishers.items():
            results[name] = {
                "configured": await publisher.validate_auth(),
            }
        return results
