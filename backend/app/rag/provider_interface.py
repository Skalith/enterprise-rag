"""Provider contract.

Every adapter receives the already-built system prompt and the user question as
separate arguments, so no provider can accidentally merge the question into the
instructions.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class ProviderError(RuntimeError):
    """Raised when a provider cannot produce a completion."""

    def __init__(self, provider: str, message: str, status_code: Optional[int] = None):
        super().__init__(f"{provider}: {message}")
        self.provider = provider
        self.message = message
        self.status_code = status_code


class ProviderNotConfigured(ProviderError):
    """Raised when credentials for a provider are missing."""


class LLMProvider(ABC):
    provider_name: str

    @abstractmethod
    async def generate(
        self,
        system_prompt: str,
        question: str,
        context: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> str:
        """Return the completion text for `question` grounded in `context`."""

    @abstractmethod
    def health(self) -> bool:
        """True when the provider is configured and reachable."""

    async def embed(self, texts: List[str]) -> List[List[float]]:
        """Embed texts. Defaults to the shared local embedding model."""
        from .retriever import embed_texts

        return embed_texts(texts)

    def usage(self, prompt: str, completion: str) -> Dict[str, int]:
        """Best-effort token accounting for observability."""
        prompt_tokens = max(1, len(prompt) // 4)
        completion_tokens = max(1, len(completion) // 4)
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }