from typing import List, Optional

import httpx

from ...config import settings
from ...observability.logging import get_logger
from ..provider_interface import ProviderError, ProviderNotConfigured, LLMProvider

logger = get_logger("adapters.gemini")

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class GeminiProvider(LLMProvider):
    provider_name = "gemini"

    def __init__(self, model: Optional[str] = None):
        self.model = model or "gemini-1.5-flash"

    def _key(self) -> str:
        if not settings.GEMINI_API_KEY:
            raise ProviderNotConfigured(self.provider_name, "GEMINI_API_KEY is not set")
        return settings.GEMINI_API_KEY

    async def generate(
        self,
        system_prompt: str,
        question: str,
        context: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> str:
        key = self._key()
        url = f"{GEMINI_BASE_URL}/models/{self.model}:generateContent"

        # systemInstruction carries the rules; contents carries only data+question.
        body = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [
                {"role": "user", "parts": [{"text": f"{context}\n\n{question}" if context else question}]}
            ],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=settings.PROVIDER_TIMEOUT_SEC) as client:
                response = await client.post(url, params={"key": key}, json=body)
                response.raise_for_status()
                payload = response.json()
                text = payload["candidates"][0]["content"]["parts"][0]["text"]
        except httpx.HTTPStatusError as exc:
            raise ProviderError(
                self.provider_name,
                f"HTTP {exc.response.status_code}: {exc.response.text[:300]}",
                status_code=exc.response.status_code,
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(self.provider_name, f"request failed: {exc}") from exc
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(
                self.provider_name, f"unexpected response shape: {exc}"
            ) from exc

        text = (text or "").strip()
        if not text:
            raise ProviderError(self.provider_name, "empty completion")
        return text

    async def embed(self, texts: List[str]) -> List[List[float]]:
        from ..retriever import embed_texts

        return embed_texts(texts)

    def health(self) -> bool:
        return bool(settings.GEMINI_API_KEY)