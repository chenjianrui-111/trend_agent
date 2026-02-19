"""
Selective multimodal enrichment for image/video heavy items.
"""

import json
import logging
from typing import Dict, List

from trend_agent.config.settings import settings
from trend_agent.models.message import TrendItem

logger = logging.getLogger(__name__)


class MultiModalEnricher:
    """Run multimodal analysis only on high-value candidates to control cost."""

    def __init__(self, llm_client):
        self._llm = llm_client

    async def enrich(self, items: List[TrendItem]) -> List[TrendItem]:
        if not settings.multimodal.enabled or not items:
            return items

        ranked = sorted(
            items,
            key=lambda x: float(x.normalized_heat_score or 0.0),
            reverse=True,
        )
        budget = max(0, settings.multimodal.enrich_top_n)
        if budget == 0:
            return items

        selected = [
            i for i in ranked
            if self._has_analyzable_media(i)
            and float(i.normalized_heat_score or 0.0) >= settings.multimodal.min_heat_score
        ][:budget]

        for item in selected:
            media_urls = self._select_media_urls(item)
            if not media_urls:
                continue
            try:
                response = await self._llm.analyze_media(
                    prompt=self._prompt(item),
                    media_urls=media_urls,
                    max_tokens=512,
                )
                parsed = self._parse_response(response)
                self._apply_enrichment(item, parsed, media_urls)
            except Exception as e:
                logger.warning("Multimodal enrichment failed for %s: %s", item.source_id, e)
                item.multimodal = {
                    "applied": False,
                    "error": str(e),
                    "media_urls": media_urls,
                }
        return items

    def _has_analyzable_media(self, item: TrendItem) -> bool:
        for m in item.media_assets:
            if m.get("media_type") == "image":
                return True
        return False

    def _select_media_urls(self, item: TrendItem) -> List[str]:
        selected: List[str] = []
        max_media = max(1, settings.multimodal.max_media_per_item)
        for m in item.media_assets:
            if m.get("media_type") == "image" and m.get("url"):
                selected.append(m["url"])
                if len(selected) >= max_media:
                    break
        return selected

    def _prompt(self, item: TrendItem) -> str:
        return (
            "You are a multimodal content analyst.\n"
            "Analyze these images and return strict JSON with fields:\n"
            '{"summary":"...", "tags":["..."], "ocr_text":"...", "risk_flags":["..."]}\n'
            f"Title: {item.title}\n"
            f"Description: {item.description}\n"
            "Output JSON only."
        )

    def _parse_response(self, response: str) -> Dict:
        text = (response or "").strip()
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                data = json.loads(text[start:end])
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                pass
        return {"summary": "", "tags": [], "ocr_text": "", "risk_flags": []}

    def _apply_enrichment(self, item: TrendItem, parsed: Dict, media_urls: List[str]):
        summary = str(parsed.get("summary", "")).strip()
        tags = [str(t).strip() for t in parsed.get("tags", []) if str(t).strip()]
        ocr_text = str(parsed.get("ocr_text", "")).strip()
        risk_flags = [str(t).strip() for t in parsed.get("risk_flags", []) if str(t).strip()]

        if summary:
            item.normalized_text = (item.normalized_text + "\n" + summary).strip()
        if ocr_text:
            item.normalized_text = (item.normalized_text + "\n" + ocr_text).strip()

        if tags:
            item.tags = sorted(set(item.tags + tags))[:12]
        item.multimodal = {
            "applied": True,
            "summary": summary,
            "tags": tags,
            "ocr_text": ocr_text,
            "risk_flags": risk_flags,
            "media_urls": media_urls,
        }

