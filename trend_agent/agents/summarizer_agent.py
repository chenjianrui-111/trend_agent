"""
SummarizerAgent - 按平台生成差异化内容摘要
"""

import difflib
import asyncio
import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Tuple

from trend_agent.agents.base import BaseAgent
from trend_agent.config.settings import settings
from trend_agent.context.generation_constraints import build_constraint_block, get_platform_constraint
from trend_agent.context.prompt_templates import PLATFORM_PROMPTS
from trend_agent.models.message import AgentMessage, ContentDraftMsg
from trend_agent.services.dedup import content_hash

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

        all_drafts: List[Dict[str, Any]] = []
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

    async def _generate_draft(self, item: Dict[str, Any], platform: str) -> Dict[str, Any]:
        prompt_fn = PLATFORM_PROMPTS.get(platform)
        if not prompt_fn:
            self.logger.warning("No prompt template for platform: %s", platform)
            return {}

        title = item.get("title", "")
        description = item.get("description", "")
        category = item.get("category", "其他")
        constraint = get_platform_constraint(platform)
        constraint_text = build_constraint_block(platform, settings.generation.banned_words)

        base_prompt = prompt_fn(title, description, category)
        prompt = (
            f"{constraint_text}\n\n"
            f"{base_prompt}\n\n"
            "输出要求:\n"
            '- 仅返回 JSON: {"title":"", "body":"", "summary":"", "hashtags":[]}\n'
            "- 不要输出 markdown 或额外解释。\n"
        )

        max_repairs = max(0, int(settings.generation.self_repair_max_attempts))
        deadline = time.monotonic() + max(1.0, float(settings.generation.stage_timeout_seconds))
        attempt = 0
        best_draft: Dict[str, Any] = {}
        best_eval: Dict[str, float] = {"quality_score": 0.0, "compliance_score": 0.0, "repeat_ratio": 1.0}
        last_issues: List[str] = []

        while attempt <= max_repairs:
            attempt += 1
            attempt_prompt = prompt if attempt == 1 else self._build_repair_prompt(prompt, best_draft, last_issues)
            llm_meta = await self._generate_with_budget(attempt_prompt, deadline)
            parsed = self._parse_response(str(llm_meta.get("text") or ""))
            candidate = self._build_draft(item, platform, parsed)
            eval_result, issues = self._evaluate_candidate(
                candidate=candidate,
                source_item=item,
                platform=platform,
                constraint=constraint,
            )
            if eval_result["quality_score"] > best_eval["quality_score"]:
                best_draft = candidate
                best_eval = eval_result
            if not issues:
                return self._attach_generation_meta(
                    draft=candidate,
                    prompt=attempt_prompt,
                    llm_meta=llm_meta,
                    eval_result=eval_result,
                    issues=[],
                    attempt=attempt,
                )
            last_issues = issues
            if attempt > max_repairs:
                break

        if not best_draft:
            return {}
        empty_meta = {
            "backend_role": "unknown",
            "backend": "unknown",
            "model": "",
            "used_fallback": False,
            "latency_ms": 0.0,
        }
        return self._attach_generation_meta(
            draft=best_draft,
            prompt=prompt,
            llm_meta=empty_meta,
            eval_result=best_eval,
            issues=last_issues,
            attempt=attempt,
            force_rejected=True,
        )

    async def _generate_with_budget(self, prompt: str, deadline: float) -> Dict[str, Any]:
        remain = max(0.1, deadline - time.monotonic())
        method = getattr(self._llm, "generate_sync_with_metadata", None)
        if method is None:
            text = await self._llm.generate_sync(
                prompt,
                max_tokens=max(128, int(settings.generation.max_tokens)),
            )
            return {
                "text": text,
                "backend_role": "primary",
                "backend": "mock",
                "model": "",
                "used_fallback": False,
                "latency_ms": 0.0,
            }
        try:
            maybe_coro = method(
                prompt,
                max_tokens=max(128, int(settings.generation.max_tokens)),
                timeout_seconds=remain,
            )
            if asyncio.iscoroutine(maybe_coro):
                return await maybe_coro
            if isinstance(maybe_coro, dict):
                return maybe_coro
        except Exception as e:
            remain2 = max(0.1, deadline - time.monotonic())
            if remain2 > 0.1:
                self.logger.warning("Primary generation failed, fallback degrade enabled: %s", e)
                return await self._llm.generate_sync_with_metadata(
                    prompt,
                    max_tokens=max(128, int(settings.generation.max_tokens)),
                    timeout_seconds=remain2,
                    prefer_fallback=True,
                )

        # Mock/legacy client path where method exists but isn't awaitable.
        try:
            text = await self._llm.generate_sync(
                prompt,
                max_tokens=max(128, int(settings.generation.max_tokens)),
            )
            return {
                "text": text,
                "backend_role": "primary",
                "backend": "mock",
                "model": "",
                "used_fallback": False,
                "latency_ms": 0.0,
            }
        except Exception:
            raise

    @staticmethod
    def _build_draft(item: Dict[str, Any], platform: str, parsed: Dict[str, Any]) -> Dict[str, Any]:
        title = str(parsed.get("title") or item.get("title") or "").strip()
        body = str(parsed.get("body") or "").strip()
        summary = str(parsed.get("summary") or "").strip()
        hashtags = [str(x).strip() for x in parsed.get("hashtags", []) if str(x).strip()]
        draft = ContentDraftMsg(
            source_item_id=item.get("item_id", ""),
            target_platform=platform,
            title=title,
            body=body,
            summary=summary,
            hashtags=hashtags,
            media_urls=item.get("media_urls", []),
            language=item.get("language", "zh"),
        )
        return draft.__dict__

    def _evaluate_candidate(
        self,
        *,
        candidate: Dict[str, Any],
        source_item: Dict[str, Any],
        platform: str,
        constraint,
    ) -> Tuple[Dict[str, float], List[str]]:
        del platform  # reserved for future platform-specific check expansion
        title = str(candidate.get("title") or "").strip()
        body = str(candidate.get("body") or "").strip()
        summary = str(candidate.get("summary") or "").strip()
        text = f"{title}\n{body}\n{summary}"
        issues: List[str] = []

        if len(title) < int(constraint.title_min):
            issues.append(f"title too short (<{constraint.title_min})")
        if len(title) > int(constraint.title_max):
            issues.append(f"title too long (>{constraint.title_max})")
        if len(body) < int(constraint.body_min):
            issues.append(f"body too short (<{constraint.body_min})")
        if len(body) > int(constraint.body_max):
            issues.append(f"body too long (>{constraint.body_max})")
        if not summary:
            issues.append("summary missing")

        for bw in settings.generation.banned_words:
            if bw and bw in text:
                issues.append(f"contains banned word: {bw}")

        source_text = f"{source_item.get('title', '')}\n{source_item.get('description', '')}"
        repeat_ratio = difflib.SequenceMatcher(None, source_text, body).ratio() if body and source_text else 0.0
        if repeat_ratio > float(settings.generation.max_repeat_ratio):
            issues.append(f"repeat ratio too high ({repeat_ratio:.3f})")

        quality_score = 1.0
        quality_score -= 0.10 * len([i for i in issues if "too short" in i or "too long" in i])
        quality_score -= 0.20 * len([i for i in issues if "banned word" in i])
        quality_score -= 0.35 * len([i for i in issues if "repeat ratio" in i])
        quality_score = max(0.0, min(1.0, quality_score))

        compliance_score = 1.0
        compliance_score -= 0.40 * len([i for i in issues if "banned word" in i])
        compliance_score -= 0.20 * len([i for i in issues if "repeat ratio" in i])
        compliance_score = max(0.0, min(1.0, compliance_score))

        if quality_score < float(settings.generation.min_quality_score):
            issues.append(
                f"quality below threshold {quality_score:.2f} < {settings.generation.min_quality_score:.2f}"
            )
        if compliance_score < float(settings.generation.min_compliance_score):
            issues.append(
                f"compliance below threshold {compliance_score:.2f} < {settings.generation.min_compliance_score:.2f}"
            )

        return (
            {
                "quality_score": round(quality_score, 6),
                "compliance_score": round(compliance_score, 6),
                "repeat_ratio": round(repeat_ratio, 6),
            },
            issues,
        )

    @staticmethod
    def _build_repair_prompt(original_prompt: str, draft: Dict[str, Any], issues: List[str]) -> str:
        draft_json = json.dumps(
            {
                "title": draft.get("title", ""),
                "body": draft.get("body", ""),
                "summary": draft.get("summary", ""),
                "hashtags": draft.get("hashtags", []),
            },
            ensure_ascii=False,
        )
        issue_text = "; ".join(issues) if issues else "内容质量不达标"
        return (
            f"{original_prompt}\n\n"
            f"上一次输出:\n{draft_json}\n"
            f"问题:\n- {issue_text}\n"
            "请根据问题修复，并输出新的 JSON。"
        )

    def _attach_generation_meta(
        self,
        *,
        draft: Dict[str, Any],
        prompt: str,
        llm_meta: Dict[str, Any],
        eval_result: Dict[str, float],
        issues: List[str],
        attempt: int,
        force_rejected: bool = False,
    ) -> Dict[str, Any]:
        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]
        output_hash = content_hash(f"{draft.get('title', '')}\n{draft.get('body', '')}\n{draft.get('summary', '')}")
        passed = (not issues) and (not force_rejected)

        draft["quality_score"] = float(eval_result.get("quality_score", 0.0))
        draft["quality_passed"] = passed
        draft["quality_issues"] = list(issues)
        draft["quality_details"] = {
            "compliance_score": float(eval_result.get("compliance_score", 0.0)),
            "repeat_ratio": float(eval_result.get("repeat_ratio", 0.0)),
            "issues": list(issues),
        }
        draft["status"] = "generated" if passed else "rejected"
        draft["generation_meta"] = {
            "schema_version": "gen.v1",
            "attempt": int(attempt),
            "prompt": prompt,
            "prompt_hash": prompt_hash,
            "backend_role": llm_meta.get("backend_role", ""),
            "backend": llm_meta.get("backend", ""),
            "model": llm_meta.get("model", ""),
            "used_fallback": bool(llm_meta.get("used_fallback", False)),
            "latency_ms": float(llm_meta.get("latency_ms", 0.0)),
            "params": {
                "max_tokens": int(settings.generation.max_tokens),
                "temperature": float(settings.llm.temperature),
            },
            "output_hash": output_hash,
            "quality_score": float(eval_result.get("quality_score", 0.0)),
            "compliance_score": float(eval_result.get("compliance_score", 0.0)),
            "repeat_ratio": float(eval_result.get("repeat_ratio", 0.0)),
        }
        return draft

    @staticmethod
    def _parse_response(response: str) -> Dict[str, Any]:
        text = response.strip()
        try:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                payload = json.loads(text[start:end])
                if isinstance(payload, dict):
                    return payload
        except (json.JSONDecodeError, ValueError):
            pass

        if len(text) > 20:
            return {"title": text[:30], "body": text, "summary": text[:120], "hashtags": []}
        return {}
