"""Shared base for OpenAI-compatible chat completion providers."""

from typing import Optional

import httpx

from ...config import settings
from ...observability.logging import get_logger
from ..provider_interface import LLMProvider, ProviderError, ProviderNotConfigured

logger = get_logger("adapters")


class OpenAICompatibleProvider(LLMProvider):
    """Implements the provider contract on top of /chat/completions APIs."""

    provider_name = "openai-compatible"
    base_url: str = ""
    env_key_attr = ""
    default_model = ""

    def __init__(self, model: Optional[str] = None):
        self.model = model or self.default_model

    # --- helpers -----------------------------------------------------------
    def api_key(self) -> Optional[str]:
        return getattr(settings, self.env_key_attr, None) if self.env_key_attr else None

    def require_key(self) -> str:
        key = self.api_key()
        if not key:
            raise ProviderNotConfigured(
                self.provider_name, f"{self.env_key_attr} is not configured"
            )
        return key

    def _messages(self, system_prompt: str, question: str, context: str) -> list:
        return [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"{context}\n\n{question}" if context else question,
            },
        ]

    def _extract(self, payload: dict) -> str:
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(
                self.provider_name, f"unexpected response shape: {exc}"
            ) from exc
        if not content:
            raise ProviderError(self.provider_name, "empty completion")
        return str(content).strip()

    # --- contract ----------------------------------------------------------
    async def generate(
        self,
        system_prompt: str,
        question: str,
        context: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> str:
        key = self.require_key()
        payload = {
            "model": self.model,
            "messages": self._messages(system_prompt, question, context),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        url = f"{self.base_url.rstrip('/')}/chat/completions"

        try:
            async with httpx.AsyncClient(timeout=settings.PROVIDER_TIMEOUT_SEC) as client:
                response = await client.post(
                    url,
                    headers={"Authorization": f"Bearer {key}"},
                    json=payload,
                )
                response.raise_for_status()
                return self._extract(response.json())
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:300]
            raise ProviderError(
                self.provider_name,
                f"HTTP {exc.response.status_code}: {detail}",
                status_code=exc.response.status_code,
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(self.provider_name, f"request failed: {exc}") from exc

    def health(self) -> bool:
        return bool(self.api_key())