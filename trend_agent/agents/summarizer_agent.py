"""
SummarizerAgent - 按平台生成差异化内容摘要
"""

import json
import logging
from typing import Dict, List

from trend_agent.agents.base import BaseAgent
from trend_agent.context.prompt_templates import PLATFORM_PROMPTS
from trend_agent.models.message import AgentMessage, ContentDraftMsg

logger = logging.getLogger(__name__)


class SummarizerAgent(BaseAgent):
    """按目标平台生成差异化内容草稿"""

    def __init__(self, llm_client):
        super().__init__("summarizer")
        self._llm = llm_client

    async def process(self, message: AgentMessage) -> AgentMessage:
        """
        payload 输入: {"items": List[dict], "target_platforms": List[str]}
        payload 输出: {"drafts": List[dict]}
        """
        items = message.payload.get("items", [])
        target_platforms = message.payload.get("target_platforms", ["wechat"])

        if not items:
            return message.create_reply("summarizer", {"drafts": []})

        all_drafts: List[Dict] = []

        for item in items:
            for platform in target_platforms:
                try:
                    draft = await self._generate_draft(item, platform)
                    if draft:
                        all_drafts.append(draft)
                except Exception as e:
                    self.logger.error(
                        "Failed to generate draft for %s on %s: %s",
                        item.get("source_id"), platform, e,
                    )

        self.logger.info(
            "Generated %d drafts for %d items across %d platforms",
            len(all_drafts), len(items), len(target_platforms),
        )
        return message.create_reply("summarizer", {"drafts": all_drafts})

    async def _generate_draft(self, item: Dict, platform: str) -> Dict:
        """Generate a platform-specific content draft."""
        prompt_fn = PLATFORM_PROMPTS.get(platform)
        if not prompt_fn:
            self.logger.warning("No prompt template for platform: %s", platform)
            return {}

        title = item.get("title", "")
        description = item.get("description", "")
        category = item.get("category", "其他")

        prompt = prompt_fn(title, description, category)
        response = await self._llm.generate_sync(prompt, max_tokens=2048)

        # Parse JSON response
        parsed = self._parse_response(response)
        if not parsed:
            return {}

        draft = ContentDraftMsg(
            source_item_id=item.get("item_id", ""),
            target_platform=platform,
            title=parsed.get("title", title),
            body=parsed.get("body", ""),
            summary=parsed.get("summary", ""),
            hashtags=parsed.get("hashtags", []),
            media_urls=item.get("media_urls", []),
            language=item.get("language", "zh"),
        )

        return draft.__dict__

    def _parse_response(self, response: str) -> Dict:
        """Parse LLM JSON response."""
        text = response.strip()
        try:
            # Find JSON object
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(text[start:end])
        except (json.JSONDecodeError, ValueError):
            pass

        # Fallback: treat entire response as body
        if len(text) > 50:
            return {"title": text[:50], "body": text, "summary": text[:100], "hashtags": []}
        return {}
