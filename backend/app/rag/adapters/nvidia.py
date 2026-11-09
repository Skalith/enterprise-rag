from .openai_compatible import OpenAICompatibleProvider


class NvidiaProvider(OpenAICompatibleProvider):
    provider_name = "nvidia"
    base_url = "https://integrate.api.nvidia.com/v1"
    env_key_attr = "NVIDIA_API_KEY"
    default_model = "meta/llama-3.1-70b-instruct"