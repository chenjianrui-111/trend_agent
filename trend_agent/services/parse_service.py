"""
Parse-stage service:
- strict contract validation + schema version
- confidence scoring + low-confidence routing
- recoverable/unrecoverable error split
- DLQ + replay
- content-hash parse cache
"""

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

from pydantic import ValidationError

from trend_agent.config.settings import settings
from trend_agent.models.parse_contract import PARSE_SCHEMA_VERSION_V1, ParseContractV1
from trend_agent.services.content_store import ContentRepository
from trend_agent.services.llm_client import LLMCallError

logger = logging.getLogger(__name__)


ParserFunc = Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]


class ParseStageError(RuntimeError):
    def __init__(self, message: str, *, code: str, recoverable: bool):
        super().__init__(message)
        self.code = code
        self.recoverable = recoverable


class ParseRecoverableError(ParseStageError):
    def __init__(self, message: str, *, code: str = "recoverable_error"):
        super().__init__(message, code=code, recoverable=True)


class ParseUnrecoverableError(ParseStageError):
    def __init__(self, message: str, *, code: str = "unrecoverable_error"):
        super().__init__(message, code=code, recoverable=False)


class ParseService:
    def __init__(
        self,
        content_store: ContentRepository,
        llm_client: Optional[Any] = None,
        parser_func: Optional[ParserFunc] = None,
    ):
        self._repo = content_store
        self._llm = llm_client
        self._parser_func = parser_func

    async def parse_pending_sources(
        self,
        *,
        limit: Optional[int] = None,
        platform: Optional[str] = None,
        parse_statuses: Optional[List[str]] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        if not settings.parse.enabled and not force:
            return {"processed": 0, "parsed": 0, "delayed": 0, "manual_review": 0, "dlq": 0, "disabled": True}

        statuses = parse_statuses or ["pending", "delayed"]
        rows = await self._repo.list_sources_for_parsing(
            limit=max(1, int(limit or settings.parse.batch_size)),
            platform=platform,
            parse_statuses=statuses,
            due_before=datetime.now(timezone.utc),
        )

        counters = {"processed": 0, "parsed": 0, "delayed": 0, "manual_review": 0, "dlq": 0}
        for row in rows:
            result = await self.parse_source_row(row, force=force)
            status = str(result.get("status") or "")
            counters["processed"] += 1
            if status in counters:
                counters[status] += 1
        return counters

    async def parse_source_by_row_id(self, source_row_id: str, *, force: bool = False) -> Dict[str, Any]:
        source = await self._repo.get_source(source_row_id)
        if not source:
            raise ValueError(f"source row not found: {source_row_id}")
        return await self.parse_source_row(source, force=force)

    async def replay_dead_letter(self, dlq_id: str) -> Dict[str, Any]:
        row = await self._repo.get_parse_dead_letter(dlq_id)
        if not row:
            raise ValueError(f"DLQ row not found: {dlq_id}")
        source_row_id = str(row.get("source_row_id") or "")
        source = await self._repo.get_source(source_row_id)
        if not source:
            await self._repo.update_parse_dead_letter(
                dlq_id,
                {"status": "resolved", "error_message": "source row not found", "replayed_at": datetime.now(timezone.utc)},
            )
            return {"status": "resolved", "reason": "source_not_found"}

        result = await self.parse_source_row(source, force=True)
        if result.get("status") == "parsed":
            await self._repo.update_parse_dead_letter(
                dlq_id,
                {"status": "resolved", "replayed_at": datetime.now(timezone.utc)},
            )
        else:
            await self._repo.update_parse_dead_letter(
                dlq_id,
                {"status": "replayed", "replayed_at": datetime.now(timezone.utc)},
            )
        return result

    async def parse_source_row(self, source: Dict[str, Any], *, force: bool = False) -> Dict[str, Any]:
        source_row_id = str(source.get("id") or "")
        if not source_row_id:
            raise ValueError("source row id is required")

        schema_version = self._schema_version()
        current_status = str(source.get("parse_status") or "")
        attempts_done = int(source.get("parse_attempts") or 0)
        content_hash = str(source.get("content_hash") or "")

        if current_status == "parsed" and not force:
            return {"status": "parsed", "source_row_id": source_row_id, "cached": False, "skipped": True}

        if settings.parse.cache_enabled and content_hash and not force:
            cached = await self._repo.get_parse_cache(content_hash=content_hash, schema_version=schema_version)
            if cached:
                payload = cached.get("parse_payload") if isinstance(cached.get("parse_payload"), dict) else {}
                confidence = float(cached.get("parse_confidence") or 0.0)
                if confidence >= settings.parse.low_confidence_threshold:
                    await self._repo.update_source_parse_state(
                        source_row_id,
                        parse_status="parsed",
                        parse_payload=payload,
                        parse_schema_version=schema_version,
                        parse_confidence=confidence,
                        parse_attempts=attempts_done,
                        parse_error_kind="",
                        parse_last_error="",
                        parse_retry_at=None,
                    )
                    return {"status": "parsed", "source_row_id": source_row_id, "cached": True}

        per_run_attempts = max(1, int(settings.parse.max_attempts_per_run))
        low_conf_retry = max(0, int(settings.parse.low_confidence_retry_attempts))

        for run_attempt in range(1, per_run_attempts + 1):
            total_attempts = attempts_done + run_attempt
            try:
                raw = await self._invoke_parser(source)
                contract = self._validate_contract(raw)
                confidence = self._calc_confidence(contract)
                parse_payload = contract.model_dump()
                parse_payload["_meta"] = {
                    "schema_version": schema_version,
                    "confidence": confidence,
                    "parsed_at": datetime.now(timezone.utc).isoformat(),
                    "backend": settings.parse.backend,
                }

                if confidence < settings.parse.low_confidence_threshold:
                    if run_attempt <= low_conf_retry and total_attempts < settings.parse.low_confidence_manual_after_attempts:
                        continue
                    return await self._handle_low_confidence(
                        source=source,
                        parse_payload=parse_payload,
                        confidence=confidence,
                        attempts=total_attempts,
                    )

                await self._repo.update_source_parse_state(
                    source_row_id,
                    parse_status="parsed",
                    parse_payload=parse_payload,
                    parse_schema_version=schema_version,
                    parse_confidence=confidence,
                    parse_attempts=total_attempts,
                    parse_error_kind="",
                    parse_last_error="",
                    parse_retry_at=None,
                )
                if settings.parse.cache_enabled and content_hash:
                    await self._repo.upsert_parse_cache(
                        content_hash=content_hash,
                        schema_version=schema_version,
                        parse_payload=parse_payload,
                        parse_confidence=confidence,
                    )
                return {"status": "parsed", "source_row_id": source_row_id, "cached": False}

            except ParseStageError as e:
                if e.recoverable and run_attempt < per_run_attempts and total_attempts < settings.parse.recoverable_max_attempts:
                    continue
                return await self._handle_failure(source=source, error=e, attempts=total_attempts)
            except Exception as e:
                unknown = ParseRecoverableError(str(e), code="unexpected_error")
                if run_attempt < per_run_attempts and total_attempts < settings.parse.recoverable_max_attempts:
                    continue
                return await self._handle_failure(source=source, error=unknown, attempts=total_attempts)

        # Should not happen because loop either returns on success/failure.
        return {"status": "delayed", "source_row_id": source_row_id}

    async def _handle_low_confidence(
        self,
        *,
        source: Dict[str, Any],
        parse_payload: Dict[str, Any],
        confidence: float,
        attempts: int,
    ) -> Dict[str, Any]:
        source_row_id = str(source.get("id") or "")
        manual_after = max(1, int(settings.parse.low_confidence_manual_after_attempts))
        if attempts >= manual_after:
            status = "manual_review"
            retry_at = None
        else:
            status = "delayed"
            retry_at = self._next_retry_at(attempts)
        await self._repo.update_source_parse_state(
            source_row_id,
            parse_status=status,
            parse_payload=parse_payload,
            parse_schema_version=self._schema_version(),
            parse_confidence=float(confidence),
            parse_attempts=attempts,
            parse_error_kind="low_confidence",
            parse_last_error=f"confidence={confidence:.4f} below threshold={settings.parse.low_confidence_threshold:.4f}",
            parse_retry_at=retry_at,
        )
        return {"status": status, "source_row_id": source_row_id, "confidence": confidence}

    async def _handle_failure(self, *, source: Dict[str, Any], error: ParseStageError, attempts: int) -> Dict[str, Any]:
        source_row_id = str(source.get("id") or "")
        max_recoverable_attempts = max(1, int(settings.parse.recoverable_max_attempts))
        if error.recoverable and attempts < max_recoverable_attempts:
            retry_at = self._next_retry_at(attempts)
            await self._repo.update_source_parse_state(
                source_row_id,
                parse_status="delayed",
                parse_schema_version=self._schema_version(),
                parse_attempts=attempts,
                parse_error_kind="recoverable",
                parse_last_error=f"{error.code}:{str(error)}",
                parse_retry_at=retry_at,
            )
            return {"status": "delayed", "source_row_id": source_row_id, "error_code": error.code}

        await self._repo.create_parse_dead_letter(
            {
                "source_row_id": source_row_id,
                "source_platform": str(source.get("source_platform") or ""),
                "source_id": str(source.get("source_id") or ""),
                "content_hash": str(source.get("content_hash") or ""),
                "schema_version": self._schema_version(),
                "error_kind": "recoverable" if error.recoverable else "unrecoverable",
                "error_code": error.code,
                "error_message": str(error),
                "retryable": bool(error.recoverable),
                "attempts": attempts,
                "status": "pending",
                "payload_snapshot": source,
            }
        )
        await self._repo.update_source_parse_state(
            source_row_id,
            parse_status="dlq",
            parse_schema_version=self._schema_version(),
            parse_attempts=attempts,
            parse_error_kind="recoverable" if error.recoverable else "unrecoverable",
            parse_last_error=f"{error.code}:{str(error)}",
            parse_retry_at=None,
        )
        return {"status": "dlq", "source_row_id": source_row_id, "error_code": error.code}

    async def _invoke_parser(self, source: Dict[str, Any]) -> Dict[str, Any]:
        if self._parser_func:
            result = self._parser_func(source)
            if asyncio.iscoroutine(result):
                result = await result
            if not isinstance(result, dict):
                raise ParseUnrecoverableError("parser_func must return dict", code="parser_return_type")
            return result

        backend = (settings.parse.backend or "heuristic").strip().lower()
        if backend == "llm":
            return await self._invoke_llm_parser(source)
        if backend != "heuristic":
            raise ParseUnrecoverableError(f"unknown parse backend: {backend}", code="unsupported_backend")
        return self._heuristic_parse(source)

    async def _invoke_llm_parser(self, source: Dict[str, Any]) -> Dict[str, Any]:
        if not self._llm:
            raise ParseUnrecoverableError("llm parser backend requires llm client", code="llm_missing")
        prompt = self._build_llm_prompt(source)
        try:
            response = await self._llm.generate_sync(prompt, max_tokens=900)
        except LLMCallError as e:
            if e.retryable:
                raise ParseRecoverableError(str(e), code="llm_retryable")
            raise ParseUnrecoverableError(str(e), code="llm_unrecoverable")
        except Exception as e:
            raise ParseRecoverableError(str(e), code="llm_exception")

        text = str(response or "").strip()
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < start:
            raise ParseRecoverableError("llm output not json object", code="llm_output_format")
        try:
            obj = json.loads(text[start:end + 1])
        except json.JSONDecodeError as e:
            raise ParseRecoverableError(str(e), code="llm_output_json")
        if not isinstance(obj, dict):
            raise ParseRecoverableError("llm output json must be object", code="llm_output_json_type")
        return obj

    def _build_llm_prompt(self, source: Dict[str, Any]) -> str:
        title = str(source.get("title") or "")
        description = str(source.get("description") or "")
        language = str(source.get("language") or "zh")
        source_platform = str(source.get("source_platform") or "")
        source_id = str(source.get("source_id") or "")
        return (
            "You are a parser. Return STRICT JSON object only, no markdown.\n"
            "Required schema:\n"
            "{\n"
            '  "schema_version":"v1",\n'
            '  "source_platform":"string",\n'
            '  "source_id":"string",\n'
            '  "title":"string",\n'
            '  "summary":"string",\n'
            '  "key_points":["string"],\n'
            '  "keywords":["string"],\n'
            '  "sentiment":"positive|neutral|negative",\n'
            '  "language":"string",\n'
            '  "confidence_model":0.0\n'
            "}\n\n"
            f"source_platform={source_platform}\n"
            f"source_id={source_id}\n"
            f"language={language}\n"
            f"title={title}\n"
            f"description={description}\n"
        )

    def _heuristic_parse(self, source: Dict[str, Any]) -> Dict[str, Any]:
        title = str(source.get("title") or "").strip()
        description = str(source.get("description") or "").strip()
        text = (title + "\n" + description).strip()
        if not text:
            raise ParseUnrecoverableError("empty source text", code="empty_text")

        summary = description[:300] if description else title[:300]
        parts = re.split(r"[。！？\.\!\?\n]+", description)
        key_points = [p.strip() for p in parts if p.strip()][:4]
        if not key_points:
            key_points = [title]
        keywords = self._extract_keywords(text=text, source=source)
        language = str(source.get("language") or "zh")

        conf = 0.45
        if len(summary) >= 40:
            conf += 0.20
        if len(key_points) >= 2:
            conf += 0.15
        if len(keywords) >= 3:
            conf += 0.12
        if len(title) >= 8:
            conf += 0.10
        conf = max(0.0, min(conf, 0.95))

        return {
            "schema_version": self._schema_version(),
            "source_platform": str(source.get("source_platform") or ""),
            "source_id": str(source.get("source_id") or ""),
            "title": title or "untitled",
            "summary": summary or title or "n/a",
            "key_points": key_points[:6],
            "keywords": keywords[:10] if keywords else [str(source.get("source_platform") or "content")],
            "sentiment": "neutral",
            "language": language or "zh",
            "confidence_model": conf,
        }

    @staticmethod
    def _extract_keywords(text: str, source: Dict[str, Any]) -> List[str]:
        out: List[str] = []
        seen = set()
        for raw in source.get("hashtags", []) or []:
            token = str(raw).strip("# ").strip()
            if token and token not in seen:
                out.append(token)
                seen.add(token)
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_\-]{2,}", text):
            t = token.lower().strip()
            if t and t not in seen:
                out.append(t)
                seen.add(t)
            if len(out) >= 10:
                break
        return out

    def _validate_contract(self, raw: Dict[str, Any]) -> ParseContractV1:
        if self._schema_version() != PARSE_SCHEMA_VERSION_V1:
            raise ParseUnrecoverableError(
                f"unsupported schema_version={self._schema_version()}",
                code="schema_unsupported",
            )
        try:
            return ParseContractV1.model_validate(raw, strict=True)
        except ValidationError as e:
            raise ParseUnrecoverableError(str(e), code="contract_validation")

    @staticmethod
    def _calc_confidence(contract: ParseContractV1) -> float:
        model_conf = float(contract.confidence_model)
        summary_score = min(len(contract.summary) / 400.0, 1.0)
        point_score = min(len(contract.key_points) / 4.0, 1.0)
        keyword_score = min(len(contract.keywords) / 6.0, 1.0)
        richness = 0.4 * summary_score + 0.3 * point_score + 0.3 * keyword_score
        score = 0.7 * model_conf + 0.3 * richness
        return round(max(0.0, min(score, 1.0)), 6)

    @staticmethod
    def _next_retry_at(attempts: int) -> datetime:
        base = max(1.0, float(settings.parse.retry_base_delay_seconds))
        max_delay = max(base, float(settings.parse.retry_max_delay_seconds))
        delay = min(base * (2 ** max(0, attempts - 1)), max_delay)
        return datetime.now(timezone.utc) + timedelta(seconds=delay)

    @staticmethod
    def _schema_version() -> str:
        return str(settings.parse.schema_version or PARSE_SCHEMA_VERSION_V1).strip()
