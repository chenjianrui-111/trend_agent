"""
QualityAgent - 内容质量和合规检查
"""

import json
import logging
import os
from typing import Dict, List, Set

from trend_agent.agents.base import BaseAgent
from trend_agent.config.settings import settings
from trend_agent.context.prompt_templates import quality_check_prompt
from trend_agent.models.message import AgentMessage, QualityResult
from trend_agent.observability import metrics as obs

logger = logging.getLogger(__name__)


class QualityAgent(BaseAgent):
    """内容质量和合规检查 Agent"""

    def __init__(self, llm_client):
        super().__init__("quality")
        self._llm = llm_client
        self._sensitive_words: Set[str] = set()

    async def startup(self):
        await super().startup()
        self._load_sensitive_words()

    def _load_sensitive_words(self):
        """Load sensitive word list from file."""
        path = settings.quality.sensitive_word_list_path
        if path and os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    word = line.strip()
                    if word and not word.startswith("#"):
                        self._sensitive_words.add(word)
            self.logger.info("Loaded %d sensitive words", len(self._sensitive_words))

    async def process(self, message: AgentMessage) -> AgentMessage:
        """
        payload 输入: {"drafts": List[dict]}
        payload 输出: {"drafts": List[dict], "quality_results": List[dict]}
        """
        drafts = message.payload.get("drafts", [])
        if not drafts:
            return message.create_reply("quality", {"drafts": [], "quality_results": []})

        checked_drafts = []
        quality_results = []

        for draft in drafts:
            result = await self._check_quality(draft)
            draft["quality_score"] = result.overall_score
            draft["quality_passed"] = result.passed
            draft["quality_issues"] = result.sensitive_words + result.compliance_issues
            if draft.get("status") != "rejected":
                draft["status"] = "quality_checked" if result.passed else "rejected"
            checked_drafts.append(draft)
            quality_results.append(result.__dict__)
            obs.record_quality(result.overall_score)

        passed = sum(1 for r in quality_results if r["passed"])
        self.logger.info("Quality check: %d/%d passed", passed, len(drafts))

        return message.create_reply("quality", {
            "drafts": checked_drafts,
            "quality_results": quality_results,
        })

    async def _check_quality(self, draft: Dict) -> QualityResult:
        """Run quality checks on a draft."""
        title = draft.get("title", "")
        body = draft.get("body", "")
        platform = draft.get("target_platform", "wechat")

        result = QualityResult()

        # 1. Sensitive word check
        text = title + " " + body
        found_sensitive = []
        for word in self._sensitive_words:
            if word in text:
                found_sensitive.append(word)
        result.sensitive_words = found_sensitive

        # 2. Min length check
        if len(body) < settings.quality.min_body_length:
            result.compliance_issues.append(
                f"Content too short ({len(body)} chars, min {settings.quality.min_body_length})"
            )

        # 3. LLM-based quality review (optional)
        if settings.quality.enable_llm_review and not found_sensitive:
            try:
                llm_result = await self._llm_quality_check(title, body, platform)
                result.overall_score = llm_result.get("score", 0.7)
                result.suggestions = llm_result.get("suggestions", [])
                if llm_result.get("issues"):
                    result.compliance_issues.extend(llm_result["issues"])
            except Exception as e:
                self.logger.warning("LLM quality check failed: %s", e)
                result.overall_score = 0.7

        # Calculate final score
        if not found_sensitive and not result.compliance_issues:
            if result.overall_score == 0.0:
                result.overall_score = 0.8
            result.passed = True
        elif found_sensitive:
            result.overall_score = 0.1
            result.passed = False
        else:
            result.overall_score = max(0.3, result.overall_score)
            result.passed = result.overall_score >= 0.5

        return result

    async def _llm_quality_check(self, title: str, body: str, platform: str) -> Dict:
        """Use LLM for quality assessment."""
        prompt = quality_check_prompt(title, body, platform)
        response = await self._llm.generate_sync(prompt, max_tokens=512)

        try:
            text = response.strip()
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(text[start:end])
        except (json.JSONDecodeError, ValueError):
            pass
        return {"score": 0.7, "passed": True, "issues": [], "suggestions": []}
