"""Configuration only; no repository access or model calls at import time."""
import json
import os
from pathlib import Path
from .providers import DeepSeekProvider, MockLLMProvider, OpenAICompatibleProvider


def load_settings(overrides=None):
    settings = {"provider": "mock", "max_review_retries": 2, "provider_attempts": 3}
    path = Path(__file__).with_name("config.json")
    if path.exists():
        settings.update(json.loads(path.read_text(encoding="utf-8")))
    for name, key, parser in (
        ("NOVEL_PROVIDER", "provider", str), ("NOVEL_MODEL", "model", str),
        ("NOVEL_BASE_URL", "base_url", str), ("NOVEL_TIMEOUT_SECONDS", "timeout_seconds", float),
        ("NOVEL_MAX_TOKENS", "max_tokens", int), ("NOVEL_TEMPERATURE", "temperature", float),
        ("NOVEL_THINKING", "thinking", str),
    ):
        if name in os.environ:
            try:
                settings[key] = parser(os.environ[name])
            except ValueError:
                raise ValueError(f"{name} 配置类型无效") from None
    settings.update(overrides or {})
    return settings


def create_provider(settings):
    name = settings["provider"]
    if name == "mock":
        return MockLLMProvider()
    if name not in ("deepseek", "openai_compatible"):
        raise ValueError("Unknown provider")
    options = {key: settings[key] for key in ("base_url", "model", "temperature", "max_tokens", "thinking") if key in settings}
    options["attempts"] = settings.get("provider_attempts", 3)
    options["timeout"] = settings.get("timeout_seconds", 180 if name == "deepseek" else 60)
    key = os.getenv("NOVEL_API_KEY") or (os.getenv("DEEPSEEK_API_KEY") if name == "deepseek" else None) or settings.get("api_key", "")
    if not isinstance(key, str) or not key.strip():
        raise ValueError("缺少 API Key，请设置 NOVEL_API_KEY（DeepSeek 也支持 DEEPSEEK_API_KEY）")
    options["api_key"] = key.strip()
    if name == "deepseek":
        return DeepSeekProvider(**options)
    if not settings.get("base_url") or not settings.get("model"):
        raise ValueError("OpenAI-compatible 必须配置 base_url 和 model")
    return OpenAICompatibleProvider(**options)
