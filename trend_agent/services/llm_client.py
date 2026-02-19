"""
统一 LLM 调用接口 - 支持 Zhipu / OpenAI / Ollama 后端

aiohttp.ClientSession 在后端生命周期内复用。
"""

import asyncio
import json
import logging
import random
import re
import time
from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Dict, Optional

import aiohttp

from trend_agent.config.settings import settings

logger = logging.getLogger(__name__)

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def clean_llm_response(text: str) -> str:
    """Strip thinking blocks and clean response."""
    if not text:
        return text
    text = _THINK_RE.sub("", text)
    return text.strip()


class LLMCallError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = False, fallback_eligible: bool = False):
        super().__init__(message)
        self.retryable = retryable
        self.fallback_eligible = fallback_eligible


class LLMBackend(ABC):
    """LLM 后端抽象基类"""

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(limit=20, keepalive_timeout=30)
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=None),
                connector=connector,
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    @abstractmethod
    async def generate_sync(self, prompt: str, max_tokens: int = 2048, **kwargs) -> str:
        ...

    @abstractmethod
    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        yield ""

    @abstractmethod
    async def health_check(self) -> Dict:
        ...


class ZhipuBackend(LLMBackend):
    """智谱大模型后端 (OpenAI-compatible Chat Completions)"""

    def __init__(self, base_url: str, api_key: str, model: str):
        super().__init__()
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key.strip()
        self.model = model

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _extract_text(self, data: Dict[str, Any]) -> str:
        choices = data.get("choices", [])
        if not choices:
            return ""
        msg = choices[0].get("message", {})
        content = msg.get("content", "")
        return content if isinstance(content, str) else ""

    async def generate_sync(self, prompt: str, max_tokens: int = 2048, **kwargs) -> str:
        if not self.api_key:
            raise LLMCallError("zhipu api key missing", retryable=False)
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": kwargs.get("temperature", settings.llm.temperature),
            "max_tokens": max_tokens,
            "stream": False,
        }
        timeout = aiohttp.ClientTimeout(total=settings.llm.timeout_seconds)
        session = await self._get_session()
        async with session.post(
            f"{self.base_url}/chat/completions",
            json=payload, timeout=timeout, headers=self._headers(),
        ) as resp:
            if resp.status >= 400:
                detail = await resp.text()
                raise LLMCallError(
                    f"zhipu error status={resp.status}: {detail[:300]}",
                    retryable=resp.status >= 500,
                    fallback_eligible=resp.status != 401,
                )
            data = await resp.json(content_type=None)
            return self._extract_text(data)

    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        if not self.api_key:
            raise LLMCallError("zhipu api key missing", retryable=False)
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": kwargs.get("temperature", settings.llm.temperature),
            "max_tokens": kwargs.get("max_tokens", settings.llm.max_tokens),
            "stream": True,
        }
        timeout = aiohttp.ClientTimeout(total=settings.llm.timeout_seconds * 2)
        session = await self._get_session()
        async with session.post(
            f"{self.base_url}/chat/completions",
            json=payload, timeout=timeout, headers=self._headers(),
        ) as resp:
            if resp.status >= 400:
                detail = await resp.text()
                raise LLMCallError(
                    f"zhipu stream error status={resp.status}: {detail[:300]}",
                    retryable=resp.status >= 500,
                    fallback_eligible=True,
                )
            async for line in resp.content:
                raw = line.decode("utf-8").strip()
                if not raw or not raw.startswith("data:"):
                    continue
                body = raw[5:].strip()
                if body == "[DONE]":
                    return
                try:
                    data = json.loads(body)
                except json.JSONDecodeError:
                    continue
                choices = data.get("choices", [])
                if choices:
                    token = choices[0].get("delta", {}).get("content", "")
                    if token:
                        yield str(token)

    async def health_check(self) -> Dict:
        if not self.api_key:
            return {"status": "unhealthy", "error": "missing ZHIPU_API_KEY"}
        return {"status": "healthy", "backend": "zhipu", "model": self.model}


class OpenAIBackend(LLMBackend):
    """OpenAI-compatible 后端 (OpenAI, DeepSeek, etc.)"""

    def __init__(self, base_url: str, api_key: str, model: str):
        super().__init__()
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key.strip()
        self.model = model

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def generate_sync(self, prompt: str, max_tokens: int = 2048, **kwargs) -> str:
        if not self.api_key:
            raise LLMCallError("openai api key missing", retryable=False)
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": kwargs.get("temperature", settings.llm.temperature),
            "max_tokens": max_tokens,
        }
        timeout = aiohttp.ClientTimeout(total=settings.llm.timeout_seconds)
        session = await self._get_session()
        async with session.post(
            f"{self.base_url}/chat/completions",
            json=payload, timeout=timeout, headers=self._headers(),
        ) as resp:
            if resp.status >= 400:
                detail = await resp.text()
                raise LLMCallError(
                    f"openai error status={resp.status}: {detail[:300]}",
                    retryable=resp.status >= 500,
                    fallback_eligible=resp.status != 401,
                )
            data = await resp.json(content_type=None)
            choices = data.get("choices", [])
            if not choices:
                return ""
            return choices[0].get("message", {}).get("content", "")

    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        if not self.api_key:
            raise LLMCallError("openai api key missing", retryable=False)
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": kwargs.get("temperature", settings.llm.temperature),
            "max_tokens": kwargs.get("max_tokens", settings.llm.max_tokens),
            "stream": True,
        }
        timeout = aiohttp.ClientTimeout(total=settings.llm.timeout_seconds * 2)
        session = await self._get_session()
        async with session.post(
            f"{self.base_url}/chat/completions",
            json=payload, timeout=timeout, headers=self._headers(),
        ) as resp:
            if resp.status >= 400:
                detail = await resp.text()
                raise LLMCallError(
                    f"openai stream error: {detail[:300]}",
                    retryable=resp.status >= 500,
                    fallback_eligible=True,
                )
            async for line in resp.content:
                raw = line.decode("utf-8").strip()
                if not raw or not raw.startswith("data:"):
                    continue
                body = raw[5:].strip()
                if body == "[DONE]":
                    return
                try:
                    data = json.loads(body)
                except json.JSONDecodeError:
                    continue
                choices = data.get("choices", [])
                if choices:
                    token = choices[0].get("delta", {}).get("content", "")
                    if token:
                        yield str(token)

    async def health_check(self) -> Dict:
        if not self.api_key:
            return {"status": "unhealthy", "error": "missing API key"}
        return {"status": "healthy", "backend": "openai", "model": self.model}


class OllamaBackend(LLMBackend):
    """Ollama 后端"""

    def __init__(self, base_url: str, model: str):
        super().__init__()
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def generate_sync(self, prompt: str, max_tokens: int = 2048, **kwargs) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": kwargs.get("temperature", settings.llm.temperature),
                "num_predict": max_tokens,
            },
        }
        timeout = aiohttp.ClientTimeout(total=settings.llm.timeout_seconds)
        session = await self._get_session()
        async with session.post(
            f"{self.base_url}/api/generate",
            json=payload, timeout=timeout,
        ) as resp:
            if resp.status >= 400:
                detail = await resp.text()
                raise LLMCallError(
                    f"ollama error: {detail[:300]}",
                    retryable=True, fallback_eligible=True,
                )
            data = await resp.json(content_type=None)
            return data.get("response", "")

    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": kwargs.get("temperature", settings.llm.temperature),
                "num_predict": kwargs.get("max_tokens", settings.llm.max_tokens),
            },
        }
        timeout = aiohttp.ClientTimeout(total=settings.llm.timeout_seconds * 2)
        session = await self._get_session()
        async with session.post(
            f"{self.base_url}/api/generate",
            json=payload, timeout=timeout,
        ) as resp:
            if resp.status >= 400:
                detail = await resp.text()
                raise LLMCallError(f"ollama stream error: {detail[:300]}", retryable=True, fallback_eligible=True)
            async for line in resp.content:
                if not line:
                    continue
                try:
                    data = json.loads(line.decode("utf-8"))
                except json.JSONDecodeError:
                    continue
                if not data.get("done"):
                    yield data.get("response", "")

    async def health_check(self) -> Dict:
        try:
            session = await self._get_session()
            async with session.get(f"{self.base_url}/api/tags") as resp:
                return {"status": "healthy", "backend": "ollama", "model": self.model}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}


class LLMServiceClient:
    """
    统一 LLM 调用入口 - 自动切换后端，支持重试和 fallback
    """

    def __init__(self):
        self.backend = self._build_backend(settings.llm.primary_backend)
        self._fallback: Optional[LLMBackend] = None
        if settings.llm.fallback_enabled:
            self._fallback = self._build_backend(settings.llm.fallback_backend)
        self._retry_max = max(1, settings.llm.retry_max_attempts)
        self._retry_delay = max(0.0, settings.llm.retry_base_delay_seconds)
        logger.info("LLMServiceClient initialized: primary=%s", settings.llm.primary_backend)

    def _build_backend(self, backend_type: str) -> LLMBackend:
        backend_type = (backend_type or "zhipu").strip().lower()
        if backend_type == "zhipu":
            return ZhipuBackend(
                base_url=settings.llm.zhipu_base_url,
                api_key=settings.llm.zhipu_api_key,
                model=settings.llm.zhipu_model,
            )
        if backend_type == "openai":
            return OpenAIBackend(
                base_url=settings.llm.openai_base_url,
                api_key=settings.llm.openai_api_key,
                model=settings.llm.openai_model,
            )
        if backend_type == "ollama":
            return OllamaBackend(
                base_url=settings.llm.ollama_base_url,
                model=settings.llm.ollama_model,
            )
        logger.warning("Unknown backend type %s, fallback to zhipu", backend_type)
        return ZhipuBackend(
            base_url=settings.llm.zhipu_base_url,
            api_key=settings.llm.zhipu_api_key,
            model=settings.llm.zhipu_model,
        )

    async def generate_sync(self, prompt: str, max_tokens: int = 2048, **kwargs) -> str:
        """同步生成，带重试和 fallback"""
        last_error: Optional[Exception] = None
        for attempt in range(1, self._retry_max + 1):
            try:
                result = await self.backend.generate_sync(prompt, max_tokens, **kwargs)
                return clean_llm_response(result)
            except LLMCallError as e:
                last_error = e
                if e.retryable and attempt < self._retry_max:
                    delay = self._retry_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.3)
                    await asyncio.sleep(delay)
                    continue
                break
            except Exception as e:
                last_error = e
                break

        # fallback
        if self._fallback:
            try:
                logger.warning("Primary LLM failed, trying fallback: %s", last_error)
                result = await self._fallback.generate_sync(prompt, max_tokens, **kwargs)
                return clean_llm_response(result)
            except Exception as fb_err:
                logger.error("Fallback also failed: %s", fb_err)

        raise last_error or LLMCallError("LLM generation failed", retryable=False)

    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """流式生成"""
        try:
            async for token in self.backend.generate_stream(prompt, **kwargs):
                yield token
        except LLMCallError as e:
            if self._fallback and e.fallback_eligible:
                logger.warning("Primary stream failed, switching to fallback")
                async for token in self._fallback.generate_stream(prompt, **kwargs):
                    yield token
            else:
                raise

    async def health_check(self) -> Dict:
        return await self.backend.health_check()

    async def close(self):
        await self.backend.close()
        if self._fallback:
            await self._fallback.close()
