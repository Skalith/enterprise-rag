from typing import Dict, Optional, Type

from ..provider_interface import LLMProvider, ProviderError, ProviderNotConfigured
from .gemini import GeminiProvider
from .groq import GroqProvider
from .nvidia import NvidiaProvider
from .ollama import OllamaProvider
from .omniroute import OmniRouteProvider

PROVIDERS: Dict[str, Type[LLMProvider]] = {
    "ollama": OllamaProvider,
    "groq": GroqProvider,
    "gemini": GeminiProvider,
    "omniroute": OmniRouteProvider,
    "nvidia": NvidiaProvider,
}

PROVIDER_MODELS: Dict[str, str] = {
    "ollama": "llama3",
    "groq": "openai/gpt-oss-120b",
    "gemini": "gemini-1.5-flash",
    "omniroute": "omni-mistral",
    "nvidia": "meta/llama-3.1-70b-instruct",
}

__all__ = [
    "PROVIDERS",
    "PROVIDER_MODELS",
    "get_provider",
    "provider_health",
    "ProviderError",
    "ProviderNotConfigured",
    "OllamaProvider",
    "GroqProvider",
    "GeminiProvider",
    "OmniRouteProvider",
    "NvidiaProvider",
]


def get_provider(name: str, model: Optional[str] = None) -> LLMProvider:
    cls = PROVIDERS.get((name or "").lower())
    if not cls:
        raise ProviderError(name or "unknown", f"Unknown provider {name!r}")
    return cls(model) if model else cls()


def provider_health() -> Dict[str, bool]:
    """Configured/healthy state per provider, used by the admin console."""
    status: Dict[str, bool] = {}
    for name, cls in PROVIDERS.items():
        try:
            status[name] = bool(cls().health())
        except Exception:
            status[name] = False
    return status
