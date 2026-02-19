"""
CategorizerAgent - LLM 驱动的内容分类 Agent
"""

import json
import logging
from typing import Any, Dict, List

from trend_agent.agents.base import BaseAgent
from trend_agent.context.prompt_templates import CATEGORIES, categorize_prompt
from trend_agent.models.message import AgentMessage
from trend_agent.observability import metrics as obs

logger = logging.getLogger(__name__)


class CategorizerAgent(BaseAgent):
    """LLM 驱动的批量内容分类"""

    def __init__(self, llm_client):
        super().__init__("categorizer")
        self._llm = llm_client
        self._valid_categories = set(CATEGORIES)

    async def process(self, message: AgentMessage) -> AgentMessage:
        """
        payload 输入: {"items": List[dict]}
        payload 输出: {"items": List[dict]} (with category/tags/confidence filled)
        """
        items = message.payload.get("items", [])
        if not items:
            return message.create_reply("categorizer", {"items": []})

        # Batch classify in groups of 10
        batch_size = 10
        categorized = []

        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            results = await self._classify_batch(batch)
            for item, result in zip(batch, results):
                item["category"] = result.get("category", "其他")
                item["tags"] = result.get("tags", [])
                item["confidence"] = result.get("confidence", 0.5)
                obs.record_categorize(item["category"])
                categorized.append(item)

        self.logger.info("Categorized %d items", len(categorized))
        return message.create_reply("categorizer", {"items": categorized})

    async def _classify_batch(self, batch: List[Dict]) -> List[Dict]:
        """Batch classify items using LLM."""
        items_text = ""
        for idx, item in enumerate(batch):
            title = item.get("title", "")
            desc = item.get("description", "")[:200]
            items_text += f"\n{idx + 1}. 标题: {title}\n   内容: {desc}\n"

        prompt = categorize_prompt(items_text)

        try:
            response = await self._llm.generate_sync(prompt, max_tokens=1024)
            results = self._parse_classification(response, len(batch))
            return results
        except Exception as e:
            self.logger.error("Classification failed: %s", e)
            return [{"category": "其他", "tags": [], "confidence": 0.0}] * len(batch)

    def _parse_classification(self, response: str, expected_count: int) -> List[Dict]:
        """Parse LLM classification response."""
        try:
            # Try to extract JSON from response
            text = response.strip()
            # Find JSON array
            start = text.find("[")
            end = text.rfind("]") + 1
            if start >= 0 and end > start:
                json_str = text[start:end]
                results = json.loads(json_str)
                if isinstance(results, list):
                    # Validate and normalize
                    normalized = []
                    for r in results:
                        cat = r.get("category", "其他")
                        if cat not in self._valid_categories:
                            cat = "其他"
                        normalized.append({
                            "category": cat,
                            "tags": r.get("tags", [])[:3],
                            "confidence": min(1.0, max(0.0, float(r.get("confidence", 0.5)))),
                        })
                    # Pad if needed
                    while len(normalized) < expected_count:
                        normalized.append({"category": "其他", "tags": [], "confidence": 0.0})
                    return normalized[:expected_count]
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            self.logger.warning("Failed to parse classification: %s", e)

        return [{"category": "其他", "tags": [], "confidence": 0.0}] * expected_count
