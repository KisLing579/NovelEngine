import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from urllib.parse import quote

import pytest

from backend.app import create_app
from backend.engine import NovelEngine
from backend.providers import MockLLMProvider, ProviderError
from backend.repository import StateRepository
from backend.tests.helpers import select_default_branch


def create(client, name='同名小说'):
    response = client.post('/api/project/init', json={'name': name, 'prompt': f'{name}的故事'})
    assert response.status_code == 200
    return response.json['data']['project_id']


def generate(client):
    select_default_branch(client)
    response = client.post('/api/chapter/generate', json={})
    assert response.status_code == 200
    return response.json['data']


def test_projects_isolate_drafts_plans_snapshots_and_restore_after_restart(tmp_path):
    app = create_app(tmp_path, MockLLMProvider())
    client = app.test_client()
    first = create(client)
    draft = generate(client)
    assert client.post('/api/chapter/approve', json={'draft_id': draft['id']}).status_code == 200
    pending = generate(client)
    first_dashboard = client.get('/api/dashboard').json['data']
    first_bytes = (tmp_path / first / 'state.json').read_bytes()

    second = create(client)
    assert first != second
    assert not (tmp_path / 'state.json').exists()
    for project_id in (first, second):
        for path in ('state.json', 'snapshots/state_0.json', 'roles.json', 'chapters'):
            assert (tmp_path / project_id / path).exists()
    history = client.get('/api/projects').json['data']['projects']
    assert len(history) == 2 and all(p['name'] == '同名小说' for p in history)
    assert next(p for p in history if p['id'] == first)['draft_count'] == 1
    assert client.get('/api/chapter/draft/').status_code == 404
    assert client.post('/api/chapter/approve', json={'draft_id': pending['id']}).status_code == 409
    assert client.get('/api/project/export/txt').status_code == 404
    second_bytes = (tmp_path / second / 'state.json').read_bytes()
    assert client.post('/api/project/load', json={'project_id': first}).status_code == 200
    restored = client.get('/api/dashboard').json['data']
    for key in ('committed_state', 'current_draft', 'current_planning', 'snapshots'):
        assert restored[key] == first_dashboard[key]
    assert (tmp_path / first / 'state.json').read_bytes() == first_bytes
    assert client.get('/api/project/export/txt').status_code == 200
    assert client.post('/api/project/rollback', json={'chapter_number': 0}).status_code == 200
    assert (tmp_path / second / 'state.json').read_bytes() == second_bytes
    restarted = create_app(tmp_path, MockLLMProvider()).test_client()
    assert restarted.get('/api/dashboard').json['data']['project_id'] == first
    assert restarted.post('/api/project/load', json={'project_id': second}).status_code == 200


def test_discovers_legacy_root_and_named_directories_without_changing_state(tmp_path):
    for path in (tmp_path, tmp_path / '旅人', tmp_path / '清明上河图'):
        NovelEngine(StateRepository(path), MockLLMProvider()).initialize('旧故事')
    before = {p: p.read_bytes() for p in tmp_path.rglob('state.json')}
    client = create_app(tmp_path, MockLLMProvider()).test_client()
    history = client.get('/api/projects').json['data']['projects']
    assert {p['id'] for p in history} == {'@legacy', '旅人', '清明上河图'}
    assert client.get('/api/dashboard').json['data']['project_id'] == '@legacy'
    for project_id in ('旅人', '清明上河图', '@legacy'):
        assert client.post('/api/project/load', json={'project_id': project_id}).status_code == 200
        data = client.get('/api/dashboard', headers={'X-Project-ID': quote(project_id)}).json['data']
        assert data['project_id'] == project_id
    create(client)
    assert all(p.read_bytes() == content for p, content in before.items())


@pytest.mark.parametrize('project_id', ['', '../outside', '..\\outside', '.', 'C:\\data', '/tmp', 'x/y', 'x:stream', None, 42])
def test_invalid_project_ids_do_not_change_selection(tmp_path, project_id):
    client = create_app(tmp_path, MockLLMProvider()).test_client()
    original = create(client)
    assert client.post('/api/project/load', json={'project_id': project_id}).status_code == 400
    assert client.get('/api/dashboard').json['data']['project_id'] == original


def test_missing_or_corrupt_project_does_not_block_library(tmp_path):
    client = create_app(tmp_path, MockLLMProvider()).test_client()
    original = create(client)
    broken = tmp_path / 'broken'
    broken.mkdir()
    (broken / 'state.json').write_text('{bad json', encoding='utf-8')
    entries = client.get('/api/projects').json['data']['projects']
    assert not next(p for p in entries if p['id'] == 'broken')['available']
    assert client.post('/api/project/load', json={'project_id': 'broken'}).status_code == 422
    assert client.post('/api/project/load', json={'project_id': 'missing'}).status_code == 404
    assert client.get('/api/dashboard').json['data']['project_id'] == original


def test_initialization_failure_preserves_selected_project(tmp_path):
    class FailingProvider(MockLLMProvider):
        fail = False

        def complete(self, task, context, schema):
            if self.fail and task.startswith('initialize'):
                raise ProviderError('initialization failed')
            return super().complete(task, context, schema)

    provider = FailingProvider()
    client = create_app(tmp_path, provider).test_client()
    original = create(client)
    before = (tmp_path / original / 'state.json').read_bytes()
    provider.fail = True
    assert client.post('/api/project/init', json={'prompt': 'another story'}).status_code == 502
    assert client.get('/api/dashboard').json['data']['project_id'] == original
    assert len(client.get('/api/projects').json['data']['projects']) == 1
    assert (tmp_path / original / 'state.json').read_bytes() == before


def test_inflight_generation_and_other_tabs_keep_their_project(tmp_path):
    started, release = Event(), Event()

    class WaitingProvider(MockLLMProvider):
        def complete(self, task, context, schema):
            if task.startswith('generate'):
                started.set()
                assert release.wait(20)
            return super().complete(task, context, schema)

    app = create_app(tmp_path, WaitingProvider())
    client = app.test_client()
    first = create(client, '第一本')
    select_default_branch(client)
    second = create(client, '第二本')

    def generate_first():
        with app.test_client() as other:
            return other.post('/api/chapter/generate', json={}, headers={'X-Project-ID': first})

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(generate_first)
        try:
            assert started.wait(10)
            assert client.post('/api/project/load', json={'project_id': second}).status_code == 200
        finally:
            release.set()
        assert future.result().status_code == 200
    first_state = json.loads((tmp_path / first / 'state.json').read_text('utf-8'))
    second_state = json.loads((tmp_path / second / 'state.json').read_text('utf-8'))
    assert first_state['chapters']['1']['status'] == 'draft'
    assert second_state['chapters'] == {}
    assert client.get('/api/chapter/draft/').status_code == 404
    assert client.get('/api/chapter/draft/', headers={'X-Project-ID': first}).status_code == 200
    assert client.get('/api/project/export/txt', query_string={'project_id': first}).status_code == 200


@pytest.mark.parametrize('name', ['', ' ', 123, 'x' * 81])
def test_project_name_validation(tmp_path, name):
    client = create_app(tmp_path, MockLLMProvider()).test_client()
    assert client.post('/api/project/init', json={'name': name, 'prompt': 'story'}).status_code == 400
    assert client.get('/api/projects').json['data']['projects'] == []
