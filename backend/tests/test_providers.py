import httpx
import pytest
from backend.providers import OpenAICompatibleProvider, ProviderError, MockLLMProvider
from backend.agents import ReviewAgent


def test_compatible_request_contract(monkeypatch):
    captured = {}
    def post(url, **kwargs):
        captured.update(url=url, **kwargs)
        return httpx.Response(200, request=httpx.Request('POST', url),
                              json={'choices': [{'message': {'content': '{"text":"chapter"}'}}]})
    monkeypatch.setattr(httpx, 'post', post)
    provider = OpenAICompatibleProvider('https://example.test/v1/', 'test-key', 'test-model')
    assert provider.complete('generate', {}, {}) == {'text': 'chapter'}
    assert captured['url'] == 'https://example.test/v1/chat/completions'
    assert captured['json']['model'] == 'test-model'
    assert captured['headers']['Authorization'] == 'Bearer test-key'


def test_compatible_bounded_network_retry(monkeypatch):
    calls = []
    def post(*args, **kwargs):
        calls.append(1)
        raise httpx.ConnectError('offline')
    monkeypatch.setattr(httpx, 'post', post)
    monkeypatch.setattr('backend.providers.time.sleep', lambda _: None)
    with pytest.raises(ProviderError):
        OpenAICompatibleProvider('https://example.test/v1', '', 'test').complete('x', {}, {})
    assert len(calls) == 3


@pytest.mark.parametrize('content', ['', '[]', '{}', 'not json'])
def test_compatible_rejects_empty_or_invalid_json(monkeypatch, content):
    def post(url, **kwargs):
        return httpx.Response(200, request=httpx.Request('POST', url),
                              json={'choices': [{'message': {'content': content}}]})
    monkeypatch.setattr(httpx, 'post', post)
    with pytest.raises(ProviderError):
        OpenAICompatibleProvider('https://example.test', '', 'test', attempts=1).complete('x', {}, {})


@pytest.mark.parametrize('text', ['旅人继续行动', '使用不存在物品', '违反既定世界规则'])
def test_mock_review_checks_minimum_conflict_classes(text):
    provider = MockLLMProvider()
    world = provider.complete('initialize', {'prompt': 'test'}, {})
    world['roles'][0]['alive'] = False
    assert not ReviewAgent(provider).review(world, text).passed
