from ...config import settings
from .openai_compatible import OpenAICompatibleProvider


class OmniRouteProvider(OpenAICompatibleProvider):
    provider_name = "omniroute"
    env_key_attr = "OMNIROUTE_API_KEY"
    default_model = "omni-mistral"

    @property
    def base_url(self) -> str:
        return settings.OMNIROUTE_BASE_URL

    @base_url.setter
    def base_url(self, value: str) -> None:
        return None