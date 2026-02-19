"""
PublisherAgent - 多平台发布协调 Agent
"""

import asyncio
import difflib
import logging
import time
from typing import Dict, List, Set

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
        self._published_body_signatures: Set[str] = set()

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
        accepted_texts: List[str] = []

        for draft in drafts:
            gate_ok, gate_reason = self._pass_stability_gate(draft, accepted_texts)
            if not gate_ok:
                all_results.append(PublishResult(
                    draft_id=draft.get("draft_id", ""),
                    platform=draft.get("target_platform", ""),
                    success=False,
                    error=f"stability_gate_blocked: {gate_reason}",
                ).__dict__)
                continue

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
                if result.success:
                    accepted_texts.append(self._draft_text(draft))
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

    def _pass_stability_gate(self, draft: Dict, accepted_texts: List[str]) -> tuple[bool, str]:
        if not settings.publisher.gate_enabled:
            return True, ""

        quality_score = float(draft.get("quality_score", 0.0) or 0.0)
        details = draft.get("quality_details", {}) if isinstance(draft.get("quality_details"), dict) else {}
        compliance_score = float(details.get("compliance_score", 0.0) or 0.0)
        repeat_ratio = float(details.get("repeat_ratio", 0.0) or 0.0)
        if quality_score < float(settings.publisher.gate_min_quality_score):
            return False, f"quality_score={quality_score:.2f} < {settings.publisher.gate_min_quality_score:.2f}"
        if compliance_score < float(settings.publisher.gate_min_compliance_score):
            return False, f"compliance_score={compliance_score:.2f} < {settings.publisher.gate_min_compliance_score:.2f}"
        if repeat_ratio > float(settings.publisher.gate_max_repeat_ratio):
            return False, f"repeat_ratio={repeat_ratio:.2f} > {settings.publisher.gate_max_repeat_ratio:.2f}"

        text = self._draft_text(draft)
        for prev in accepted_texts:
            near_dup = difflib.SequenceMatcher(None, text, prev).ratio()
            if near_dup > float(settings.publisher.gate_max_repeat_ratio):
                return False, f"near_duplicate_ratio={near_dup:.2f}"

        return True, ""

    @staticmethod
    def _draft_text(draft: Dict) -> str:
        return f"{draft.get('title', '')}\n{draft.get('body', '')}\n{draft.get('summary', '')}"

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
