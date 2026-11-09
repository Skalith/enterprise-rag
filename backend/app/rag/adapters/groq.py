from .openai_compatible import OpenAICompatibleProvider


class GroqProvider(OpenAICompatibleProvider):
    provider_name = "groq"
    base_url = "https://api.groq.com/openai/v1"
    env_key_attr = "GROQ_API_KEY"
    default_model = "openai/gpt-oss-120b"