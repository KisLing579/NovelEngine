from backend.tests.helpers import project_root
import copy
import json
from concurrent.futures import ThreadPoolExecutor
import pytest
from backend.app import create_app
from backend.models import World
from backend.providers import MockLLMProvider, ProviderError
from backend.repository import StateRepository
from backend.tests.helpers import select_default_branch


@pytest.fixture
def app(tmp_path):
    return create_app(tmp_path, MockLLMProvider(), {"max_review_retries": 2})


@pytest.fixture
def client(app):
    return app.test_client()


def initialize(client):
    response = client.post('/api/project/init', json={"prompt": "旅人寻找故乡"})
    assert response.status_code == 200
    return response.json['data']['world']


def generate(client):
    select_default_branch(client)
    response = client.post('/api/chapter/generate')
    assert response.status_code == 200
    return response.json['data']


def approve(client, draft):
    response = client.post('/api/chapter/approve', json={"draft_id": draft['id']})
    assert response.status_code == 200
    return response.json['data']['world']


def test_initialization_snapshot_and_schema(client, tmp_path):
    world = initialize(client)
    World.model_validate(world)
    assert world['chapter_number'] == 0
    assert json.loads((project_root(tmp_path) / 'snapshots/state_0.json').read_text('utf-8')) == world
    for name in ('roles', 'inventory', 'maps', 'lores', 'outline', 'state'):
        assert (project_root(tmp_path) / f'{name}.json').exists()
    assert client.post('/api/project/init', json={"prompt": "replace"}).status_code == 200
    assert len(client.get('/api/projects').json['data']['projects']) == 2


def test_generate_does_not_mutate_world(client, tmp_path):
    initial = initialize(client)
    before = {p.name: p.read_bytes() for p in project_root(tmp_path).glob('*.json') if p.name != 'state.json'}
    draft = generate(client)
    assert draft['status'] == 'draft' and draft['review']['passed']
    assert client.get('/api/project/status').json['data']['world'] == initial
    assert {p.name: p.read_bytes() for p in project_root(tmp_path).glob('*.json') if p.name != 'state.json'} == before
    assert not (project_root(tmp_path) / 'snapshots/state_1.json').exists()
    assert client.get('/api/chapter/draft/').json['data'] == draft
    assert client.get('/api/chapter/draft/1').json['data'] == draft


def test_approve_updates_all_domains_and_snapshot(client, tmp_path):
    initial = initialize(client)
    draft = generate(client)
    world = approve(client, draft)
    assert world['chapter_number'] == 1
    for key in ('roles', 'inventory', 'maps', 'lore', 'outline'):
        assert world[key] != initial[key]
    assert world['inventory'][0]['quantity'] == 1
    assert world['outline']['chapters'][0]['chapter_actual_summary']
    assert json.loads((project_root(tmp_path) / 'snapshots/state_1.json').read_text('utf-8')) == world
    assert client.post('/api/chapter/approve', json={'draft_id': draft['id']}).status_code == 409


def test_rollback_clears_future_and_restart(client, tmp_path):
    initial = initialize(client)
    first = approve(client, generate(client))
    approve(client, generate(client))
    stale = generate(client)
    response = client.post('/api/project/rollback', json={'chapter_number': 1})
    assert response.json['data']['world'] == first
    assert not (project_root(tmp_path) / 'snapshots/state_2.json').exists()
    assert not (project_root(tmp_path) / 'chapters/chapter_2.json').exists()
    assert not (project_root(tmp_path) / 'chapters/chapter_3.json').exists()
    assert client.post('/api/project/rollback', json={'chapter_number': 2}).status_code == 404
    assert client.post('/api/chapter/approve', json={'draft_id': stale['id']}).status_code == 409
    restarted = create_app(tmp_path, MockLLMProvider()).test_client()
    assert restarted.get('/api/project/status').json['data']['world'] == first
    regenerated = approve(restarted, generate(restarted))
    assert regenerated['inventory'][0]['quantity'] == 2
    assert restarted.post('/api/project/rollback', json={'chapter_number': 0}).json['data']['world'] == initial


def test_state_update_midway_failure_is_atomic(app, client, tmp_path, monkeypatch):
    initial = initialize(client)
    draft = generate(client)
    before = (project_root(tmp_path) / 'state.json').read_bytes()
    updater = app.extensions['novel_engine'].director.updater

    def fail(*args):
        raise RuntimeError('Failure after role changes were applied in memory')

    monkeypatch.setattr(updater.domains[1], 'apply', fail)
    assert client.post('/api/chapter/approve', json={'draft_id': draft['id']}).status_code == 500
    assert (project_root(tmp_path) / 'state.json').read_bytes() == before
    assert client.get('/api/project/status').json['data']['world'] == initial
    assert not (project_root(tmp_path) / 'snapshots/state_1.json').exists()


def test_canonical_write_failure_preserves_draft(app, client, tmp_path, monkeypatch):
    initialize(client)
    draft = generate(client)
    before = (project_root(tmp_path) / 'state.json').read_bytes()
    repo = app.extensions['novel_engine'].repository
    original = repo._atomic_json

    def fail(path, value):
        if path.name == 'state.json':
            raise OSError('Disk failure before commit')
        original(path, value)

    monkeypatch.setattr(repo, '_atomic_json', fail)
    assert client.post('/api/chapter/approve', json={'draft_id': draft['id']}).status_code == 500
    assert (project_root(tmp_path) / 'state.json').read_bytes() == before


def test_export_failure_recovers_from_canonical(app, client, tmp_path, monkeypatch):
    initialize(client)
    draft = generate(client)
    repo = app.extensions['novel_engine'].repository
    with monkeypatch.context() as m:
        def fail(bundle):
            raise OSError('Interrupted export')
        m.setattr(repo, '_export', fail)
        world = approve(client, draft)
    restarted = StateRepository(project_root(tmp_path))
    assert restarted.load()['world'] == world
    assert json.loads((project_root(tmp_path) / 'snapshots/state_1.json').read_text('utf-8')) == world


class RejectProvider(MockLLMProvider):
    def __init__(self):
        self.generations = 0
        self.feedbacks = []

    def complete(self, task, context, schema):
        if task.startswith('generate'):
            self.generations += 1
            self.feedbacks.append(context['review_feedback'])
        if task.startswith('review'):
            return {'passed': False, 'feedback': ['物品不存在']}
        return super().complete(task, context, schema)


def test_review_retry_limit_and_rejected_approval(tmp_path):
    provider = RejectProvider()
    client = create_app(tmp_path, provider).test_client()
    initial = initialize(client)
    select_default_branch(client)
    response = client.post('/api/chapter/generate')
    assert response.status_code == 422
    assert provider.generations == 3
    assert provider.feedbacks == [[], ['物品不存在'], ['物品不存在']]
    draft = response.json['error']['details']
    assert draft['attempts'] == 3 and draft['status'] == 'draft'
    assert client.post('/api/chapter/approve', json={'draft_id': draft['id']}).status_code == 409
    assert client.get('/api/project/status').json['data']['world'] == initial


def test_missing_summary_retries_then_no_commit(tmp_path):
    class BadSummary(MockLLMProvider):
        calls = 0

        def complete(self, task, context, schema):
            result = super().complete(task, context, schema)
            if task.startswith('extract'):
                self.calls += 1
                result['chapter_actual_summary'] = '   '
            return result

    provider = BadSummary()
    client = create_app(tmp_path, provider).test_client()
    initial = initialize(client)
    draft = generate(client)
    assert client.post('/api/chapter/approve', json={'draft_id': draft['id']}).status_code == 502
    assert provider.calls == 3
    assert client.get('/api/project/status').json['data']['world'] == initial


def test_regeneration_invalidates_previous_draft(client):
    initialize(client)
    old = generate(client)
    new = generate(client)
    assert client.post('/api/chapter/approve', json={'draft_id': old['id']}).status_code == 409
    approve(client, new)


def test_parallel_approval_commits_once(app, client):
    initialize(client)
    draft = generate(client)
    def approve_request(_):
        with app.test_client() as c:
            return c.post('/api/chapter/approve', json={'draft_id': draft['id']}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(approve_request, range(2))) == [200, 409]
    assert client.get('/api/project/status').json['data']['world']['inventory'][0]['quantity'] == 1


@pytest.mark.parametrize('payload', [{}, {'prompt': ''}, {'prompt': 4}, [], {'prompt': ' ' * 2}])
def test_bad_init_request(client, payload):
    response = client.post('/api/project/init', json=payload)
    assert response.status_code == 400 and not response.json['ok']


@pytest.mark.parametrize('value', [-1, True, '1', 1.5, None])
def test_bad_rollback_request(client, value):
    assert client.post('/api/project/rollback', json={'chapter_number': value}).status_code == 400


def test_uninitialized_and_unknown_routes(client):
    assert not client.get('/api/project/status').json['data']['initialized']
    assert client.post('/api/chapter/generate').status_code == 409
    assert client.get('/missing').json['error']['code'] == 'http_error'


def test_generator_cannot_mutate_committed_state(tmp_path):
    class MutatingProvider(MockLLMProvider):
        def complete(self, task, context, schema):
            result = super().complete(task, context, schema)
            if task.startswith('generate'):
                context['world']['roles'][0]['alive'] = False
            return result
    client = create_app(tmp_path, MutatingProvider()).test_client()
    initial = initialize(client)
    generate(client)
    assert client.get('/api/project/status').json['data']['world'] == initial


def test_export_pdf(client):
    assert client.get('/api/project/export/pdf').status_code == 409
    initialize(client)
    draft = generate(client)
    approve(client, draft)
    response = client.get('/api/project/export/pdf')
    assert response.status_code == 200
    assert response.mimetype == 'application/pdf'
    assert response.data[:5] == b'%PDF-'
