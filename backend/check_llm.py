"""One tiny real-model request. Never reads or writes novel state."""
from .configuration import load_settings, create_provider
from .providers import MockLLMProvider, ProviderError


def main():
    try:
        provider = create_provider(load_settings())
        if isinstance(provider, MockLLMProvider):
            raise ValueError("当前仍为 Mock，请先设置 NOVEL_PROVIDER=deepseek 或 backend/config.json")
        result = provider.complete('connection_check: Return the JSON object {"ok": true}.', {},
            {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"], "additionalProperties": False})
        if result != {"ok": True}:
            raise ProviderError("模型响应不符合连接测试预期")
    except (ValueError, ProviderError) as exc:
        print(f"FAIL: {exc}")
        return 1
    print(f"PASS: {type(provider).__name__} / {provider.model} JSON response verified")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
