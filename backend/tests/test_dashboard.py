from backend.tests.helpers import project_root
import json
from datetime import datetime
import pytest
from backend.app import create_app
from backend.providers import MockLLMProvider, OpenAICompatibleProvider
from backend.dashboard import summarize_changes
from backend.tests.helpers import select_default_branch


@pytest.fixture
def app(tmp_path):
    return create_app(tmp_path, MockLLMProvider())


def dashboard(client):
    response = client.get('/api/dashboard')
    assert response.status_code == 200
    return response.json['data']


def initialize(client):
    assert client.post('/api/project/init', json={'prompt': '旅人寻找故乡'}).status_code == 200


def generate(client):
    select_default_branch(client)
    response = client.post('/api/chapter/generate')
    assert response.status_code == 200
    return response.json['data']


def approve(client, draft):
    assert client.post('/api/chapter/approve', json={'draft_id': draft['id']}).status_code == 200


def test_uninitialized_dashboard(app):
    data = dashboard(app.test_client())
    assert not data['initialized']
    assert data['committed_state'] is None and data['current_draft'] is None
    assert data['chapters'] == data['snapshots'] == []


def test_read_only_committed_state_and_initial_metadata(app, tmp_path):
    client = app.test_client()
    initialize(client)
    before = (project_root(tmp_path) / 'state.json').read_bytes()
    data = dashboard(client)
    assert data['committed_state'] == client.get('/api/project/status').json['data']['world']
    assert data['project']['status'] == 'ready'
    assert data['project']['volume'] is None and data['project']['name'] == '旅人寻找故乡'
    assert data['chapters'][0]['is_current']
    assert all(c['status'] == 'not_generated' for c in data['chapters'])
    assert data['latest_snapshot']['name'] == 'state_0'
    assert datetime.fromisoformat(data['snapshots'][0]['created_at']).tzinfo is not None
    assert (project_root(tmp_path) / 'state.json').read_bytes() == before


def test_draft_is_distinct_and_approval_updates_dashboard(app, tmp_path):
    client = app.test_client()
    initialize(client)
    initial = dashboard(client)
    draft = generate(client)
    data = dashboard(client)
    assert data['committed_state'] == initial['committed_state']
    assert data['snapshots'] == initial['snapshots']
    assert data['recent_state_changes'] is None
    assert data['current_draft'] == draft
    assert data['project']['status'] == 'reviewed'
    assert data['chapters'][0]['status'] == 'draft'
    approve(client, draft)
    data = dashboard(client)
    assert data['project']['chapter_number'] == 1
    assert data['project']['status'] == 'approved'
    assert data['current_draft'] is None
    assert data['latest_snapshot']['name'] == 'state_1'
    assert data['chapters'][0]['status'] == 'approved'
    assert data['chapters'][0]['chapter_actual_summary']
    assert data['recent_state_changes']['chapter'] == 1
    changes = data['recent_state_changes']['changes']
    assert {c['domain'] for c in changes} == {'roles', 'inventory', 'maps', 'lore'}
    item = next(c for c in changes if c['domain'] == 'inventory')
    assert (item['field'], item['before'], item['after']) == ('quantity', 0, 1)
    assert json.loads((project_root(tmp_path) / 'state.json').read_text('utf-8'))['change_logs']['1'] == data['recent_state_changes']


def test_navigator_history_future_and_rollback(app, tmp_path):
    client = app.test_client()
    initialize(client)
    approve(client, generate(client))
    chapter1 = dashboard(client)
    approve(client, generate(client))
    generate(client)
    data = dashboard(client)
    assert [c['status'] for c in data['chapters'][:4]] == ['approved', 'approved', 'draft', 'not_generated']
    assert client.get('/api/chapter/draft/1').json['data']['status'] == 'approved'
    assert client.post('/api/project/rollback', json={'chapter_number': 1}).status_code == 200
    data = dashboard(client)
    assert data['committed_state'] == chapter1['committed_state']
    assert data['snapshots'] == chapter1['snapshots']
    assert data['recent_state_changes'] == chapter1['recent_state_changes']
    assert data['current_draft'] is None
    assert [c['status'] for c in data['chapters'][:3]] == ['approved', 'not_generated', 'not_generated']
    bundle = json.loads((project_root(tmp_path) / 'state.json').read_text('utf-8'))
    assert set(bundle['change_logs']) == {'1'}
    assert set(bundle['snapshot_metadata']) == {'0', '1'}
    client.post('/api/project/rollback', json={'chapter_number': 0})
    assert dashboard(client)['recent_state_changes'] is None
    assert dashboard(client)['project']['status'] == 'ready'


def test_old_phase1_bundle_is_readable_without_migration(app, tmp_path):
    client = app.test_client()
    initialize(client)
    approve(client, generate(client))
    expected = dashboard(client)['recent_state_changes']
    repo = app.extensions['novel_engine'].repository
    bundle = repo.load()
    bundle.pop('change_logs')
    bundle.pop('snapshot_metadata')
    repo.save(bundle)
    before = (project_root(tmp_path) / 'state.json').read_bytes()
    restarted = create_app(tmp_path, MockLLMProvider()).test_client()
    data = dashboard(restarted)
    assert data['recent_state_changes'] == expected
    assert all(s['created_at'] is None for s in data['snapshots'])
    assert (project_root(tmp_path) / 'state.json').read_bytes() == before
    approve(restarted, generate(restarted))
    assert dashboard(restarted)['recent_state_changes']['chapter'] == 2


def test_dashboard_never_serializes_provider_secrets(tmp_path):
    provider = OpenAICompatibleProvider('https://secret-host.test/v1', 'TOP-SECRET-KEY', 'demo-model')
    client = create_app(tmp_path, provider).test_client()
    data = dashboard(client)
    assert data['provider'] == {'name': 'OpenAICompatibleProvider', 'model': 'demo-model'}
    encoded = json.dumps(data)
    for secret in ('TOP-SECRET-KEY', 'secret-host', 'api_key', 'base_url', 'Authorization'):
        assert secret not in encoded


def test_failed_review_is_draft_and_does_not_create_changes(tmp_path):
    class Reject(MockLLMProvider):
        def complete(self, task, context, schema):
            if task.startswith('review'):
                return {'passed': False, 'feedback': ['角色状态冲突']}
            return super().complete(task, context, schema)
    client = create_app(tmp_path, Reject()).test_client()
    initialize(client)
    select_default_branch(client)
    assert client.post('/api/chapter/generate').status_code == 422
    data = dashboard(client)
    assert data['project']['status'] == 'draft'
    assert data['current_draft']['review']['feedback'] == ['角色状态冲突']
    assert data['recent_state_changes'] is None and len(data['snapshots']) == 1


def test_failed_approval_does_not_publish_log_or_metadata(app, tmp_path, monkeypatch):
    client = app.test_client()
    initialize(client)
    draft = generate(client)
    before = dashboard(client)
    repo = app.extensions['novel_engine'].repository
    atomic_json = repo._atomic_json
    def fail(path, value):
        if path.name == 'state.json':
            raise OSError('Commit failed')
        atomic_json(path, value)
    monkeypatch.setattr(repo, '_atomic_json', fail)
    assert client.post('/api/chapter/approve', json={'draft_id': draft['id']}).status_code == 500
    assert dashboard(client) == before


def test_change_summary_ignores_unchanged_fields_and_handles_additions():
    before = {'roles': [], 'inventory': [{'id': 'x', 'name': 'key', 'quantity': 2}], 'maps': [], 'lore': []}
    after = {**before, 'inventory': [{'id': 'x', 'name': 'key', 'quantity': 0}]}
    assert summarize_changes(before, before) == []
    changes = summarize_changes(before, after)
    assert len(changes) == 1 and changes[0]['before'] == 2 and changes[0]['after'] == 0
