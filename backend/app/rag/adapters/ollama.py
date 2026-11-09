from typing import List, Optional

import httpx

from ...config import settings
from ...observability.logging import get_logger
from ..provider_interface import LLMProvider, ProviderError

logger = get_logger("adapters.ollama")


class OllamaProvider(LLMProvider):
    provider_name = "ollama"

    def __init__(self, model: Optional[str] = None):
        self.model = model or settings.OLLAMA_DEFAULT_MODEL

    async def generate(
        self,
        system_prompt: str,
        question: str,
        context: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> str:
        try:
            async with httpx.AsyncClient(timeout=settings.PROVIDER_TIMEOUT_SEC) as client:
                response = await client.post(
                    f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/generate",
                    json={
                        "model": self.model,
                        "system": system_prompt,
                        "prompt": f"{context}\n\n{question}" if context else question,
                        "stream": False,
                        "options": {
                            "temperature": temperature,
                            "num_predict": max_tokens,
                        },
                    },
                )
                response.raise_for_status()
                text = response.json().get("response", "").strip()
        except httpx.HTTPStatusError as exc:
            raise ProviderError(
                self.provider_name,
                f"HTTP {exc.response.status_code}: {exc.response.text[:300]}",
                status_code=exc.response.status_code,
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(self.provider_name, f"request failed: {exc}") from exc

        if not text:
            raise ProviderError(self.provider_name, "empty completion")
        return text

    async def embed(self, texts: List[str]) -> List[List[float]]:
        """Ollama /api/embeddings returns one vector per request."""
        vectors: List[List[float]] = []
        try:
            async with httpx.AsyncClient(timeout=settings.PROVIDER_TIMEOUT_SEC) as client:
                for text in texts:
                    response = await client.post(
                        f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/embeddings",
                        json={"model": self.model, "prompt": text},
                    )
                    response.raise_for_status()
                    vectors.append(response.json().get("embedding", []))
        except httpx.HTTPError as exc:
            raise ProviderError(self.provider_name, f"embedding failed: {exc}") from exc
        return vectors

    def health(self) -> bool:
        try:
            response = httpx.get(f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/tags", timeout=3)
            return response.status_code == 200
        except Exception as exc:
            logger.warning("adapters.ollama_unhealthy", error=str(exc))
            return False