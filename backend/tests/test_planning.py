from backend.tests.helpers import project_root
import copy
import json
import pytest
from backend.app import create_app
from backend.providers import MockLLMProvider, ProviderError
from backend.agents import ReviewAgent


@pytest.fixture
def app(tmp_path):
    return create_app(tmp_path, MockLLMProvider())


@pytest.fixture
def client(app):
    client = app.test_client()
    assert client.post('/api/project/init', json={'prompt': '旅人寻找归乡的路'}).status_code == 200
    return client


def options(client, number=1):
    response = client.post('/api/chapter/branches/generate', json={'chapter_number': number})
    assert response.status_code == 200, response.json
    return response.json['data']


def choose(client, planning, strategy='escalation'):
    branch = next(b for b in planning['branches'] if b['strategy'] == strategy)
    response = client.post('/api/chapter/branches/select', json={'planning_id': planning['id'], 'branch_id': branch['id']})
    assert response.status_code == 200, response.json
    return branch


def generate(client):
    response = client.post('/api/chapter/generate', json={})
    assert response.status_code == 200, response.json
    return response.json['data']


def dashboard(client):
    return client.get('/api/dashboard').json['data']


def test_exact_strategies_and_planning_selection_do_not_commit(client, app, tmp_path):
    before = app.extensions['novel_engine'].repository.load()
    assert dashboard(client)['current_planning']['status'] == 'none'
    assert not dashboard(client)['project']['can_generate']
    planning = options(client)
    assert len(planning['branches']) == 3
    assert {b['strategy'] for b in planning['branches']} == {'progression', 'escalation', 'revelation'}
    assert len({b['id'] for b in planning['branches']}) == 3
    assert planning['status'] == 'generated' and planning['selected_branch_id'] is None
    choose(client, planning)
    after = app.extensions['novel_engine'].repository.load()
    for key in ('world', 'snapshots', 'snapshot_metadata', 'chapters', 'revision'):
        assert before[key] == after[key]
    assert not (project_root(tmp_path) / 'snapshots/state_1.json').exists()
    state = dashboard(client)['current_planning']
    assert state['status'] == 'selected' and state['selected_at']
    restarted = create_app(tmp_path, MockLLMProvider()).test_client()
    assert dashboard(restarted)['current_planning'] == state


def test_generation_requires_selection_and_rejects_client_branch_text(client):
    for phase in ('none', 'generated'):
        if phase == 'generated':
            options(client)
        response = client.post('/api/chapter/generate')
        assert response.status_code == 409
        assert response.json['error']['code'] == 'branch_not_selected'
    response = client.post('/api/chapter/generate', json={'selected_branch': {'summary': 'injected'}})
    assert response.status_code == 400


def test_selected_branch_drives_generator_and_approve_preserves_history(client, app):
    initial = dashboard(client)['committed_state']
    planning = options(client)
    branch = choose(client, planning)
    draft = generate(client)
    assert draft['planning_id'] == planning['id'] and draft['selected_branch_id'] == branch['id']
    assert all(event in draft['text'] for event in branch['expected_events'])
    assert '落石' in draft['text'] and branch['hook'] in draft['text']
    assert dashboard(client)['committed_state'] == initial
    assert dashboard(client)['current_planning']['status'] == 'draft_generated'
    response = client.post('/api/chapter/approve', json={'draft_id': draft['id']})
    assert response.status_code == 200
    assert dashboard(client)['committed_state'] != initial
    history = client.get('/api/chapter/planning/1').json['data']
    assert history['status'] == 'approved'
    assert history['branches'] == planning['branches']
    assert history['selected_branch_id'] == branch['id'] and history['draft_id'] == draft['id']
    assert dashboard(client)['current_planning']['status'] == 'none'
    assert dashboard(client)['current_planning']['chapter_number'] == 2


def test_review_detects_deviation_and_retries_generator(client, app, monkeypatch):
    planning = options(client)
    branch = choose(client, planning)
    engine = app.extensions['novel_engine']
    feedback = []
    actual = engine.director.generator.generate
    def write(context):
        feedback.append(copy.deepcopy(context['review_feedback']))
        return '旅人在家里喝茶，什么也没有发生。' if len(feedback) == 1 else actual(context)
    monkeypatch.setattr(engine.director.generator, 'generate', write)
    draft = generate(client)
    assert draft['attempts'] == 2
    assert 'Plan adherence' in ' '.join(feedback[1])
    assert branch['expected_events'][0] in draft['text']


def test_severe_plan_deviation_exhausts_retry_limit(client, app, monkeypatch):
    choose(client, options(client))
    monkeypatch.setattr(app.extensions['novel_engine'].director.generator, 'generate', lambda _: '完全无关的茶会。')
    response = client.post('/api/chapter/generate')
    assert response.status_code == 422
    assert response.json['error']['details']['attempts'] == 3
    assert dashboard(client)['current_planning']['status'] == 'draft_generated'
    assert dashboard(client)['committed_state']['chapter_number'] == 0


def test_regeneration_clears_selection_and_invalidates_old_ids(client):
    initial = dashboard(client)['committed_state']
    old = options(client)
    branch = choose(client, old)
    response = client.post('/api/chapter/branches/regenerate', json={'chapter_number': 1, 'planning_id': old['id']})
    assert response.status_code == 200
    new = response.json['data']
    assert new['id'] != old['id'] and new['selected_branch_id'] is None and new['selected_at'] is None
    assert not ({b['id'] for b in old['branches']} & {b['id'] for b in new['branches']})
    assert dashboard(client)['committed_state'] == initial
    assert client.post('/api/chapter/branches/select', json={'planning_id': old['id'], 'branch_id': branch['id']}).status_code == 409
    assert client.post('/api/chapter/branches/select', json={'planning_id': new['id'], 'branch_id': branch['id']}).status_code == 400
    assert client.post('/api/chapter/generate').status_code == 409


def test_draft_locks_selection_and_discard_unlocks_without_committing(client):
    planning = options(client)
    choose(client, planning)
    initial = dashboard(client)['committed_state']
    draft = generate(client)
    other = next(b for b in planning['branches'] if b['strategy'] == 'revelation')
    selection = {'planning_id': planning['id'], 'branch_id': other['id']}
    assert client.post('/api/chapter/branches/select', json=selection).status_code == 409
    assert client.post('/api/chapter/branches/regenerate', json={'chapter_number': 1, 'planning_id': planning['id']}).status_code == 409
    assert client.post('/api/chapter/branches/generate', json={'chapter_number': 1}).status_code == 409
    assert client.post('/api/chapter/draft/discard', json={'draft_id': 'stale'}).status_code == 409
    assert client.post('/api/chapter/draft/discard', json={'draft_id': draft['id']}).status_code == 200
    assert client.get('/api/chapter/draft/').status_code == 404
    assert dashboard(client)['current_planning']['status'] == 'selected'
    assert client.post('/api/chapter/approve', json={'draft_id': draft['id']}).status_code == 409
    assert client.post('/api/chapter/branches/select', json=selection).status_code == 200
    changed = generate(client)
    assert other['expected_events'][0] in changed['text']
    assert dashboard(client)['committed_state'] == initial


def test_rollback_cleans_future_planning_but_preserves_approved_history(client, app):
    choose(client, options(client))
    draft = generate(client)
    client.post('/api/chapter/approve', json={'draft_id': draft['id']})
    history = client.get('/api/chapter/planning/1').json['data']
    future = options(client, 2)
    choose(client, future)
    future_draft = generate(client)
    client.post('/api/project/rollback', json={'chapter_number': 1})
    assert client.get('/api/chapter/planning/1').json['data'] == history
    assert dashboard(client)['current_planning']['status'] == 'none'
    assert dashboard(client)['current_planning']['chapter_number'] == 2
    assert dashboard(client)['current_draft'] is None
    bundle = app.extensions['novel_engine'].repository.load()
    assert set(bundle['narrative_planning']) == {'1'}
    assert client.post('/api/chapter/approve', json={'draft_id': future_draft['id']}).status_code == 409
    client.post('/api/project/rollback', json={'chapter_number': 0})
    assert app.extensions['novel_engine'].repository.load()['narrative_planning'] == {}


@pytest.mark.parametrize('fault', ['count', 'strategy', 'duplicate_id', 'missing_events', 'empty_events', 'blank', 'chapter', 'goal', 'character', 'invalid_json'])
def test_invalid_planner_output_never_saves_partial_state(tmp_path, fault):
    class Invalid(MockLLMProvider):
        calls = 0
        def complete(self, task, context, schema):
            result = super().complete(task, context, schema)
            if not task.startswith('plan'):
                return result
            self.calls += 1
            branches = result['branches']
            if fault == 'count': branches.pop()
            if fault == 'strategy': branches[1]['strategy'] = 'progression'
            if fault == 'duplicate_id': branches[1]['id'] = branches[0]['id']
            if fault == 'missing_events': branches[0].pop('expected_events')
            if fault == 'empty_events': branches[0]['expected_events'] = []
            if fault == 'blank': branches[0]['title'] = '  '
            if fault == 'chapter': branches[0]['chapter_number'] = 9
            if fault == 'goal': branches[0]['chapter_goal'] = 'unrelated'
            if fault == 'character': branches[0]['character_impacts'][0]['character_id'] = 'unknown'
            if fault == 'invalid_json': return 'not an object'
            return result
    provider = Invalid()
    client = create_app(tmp_path, provider).test_client()
    client.post('/api/project/init', json={'prompt': 'test'})
    before = (project_root(tmp_path) / 'state.json').read_bytes()
    response = client.post('/api/chapter/branches/generate', json={'chapter_number': 1})
    assert response.status_code == 502 and response.json['error']['code'] == 'planning_failed'
    assert provider.calls == 3
    assert (project_root(tmp_path) / 'state.json').read_bytes() == before


def test_planner_provider_failure_preserves_previous_selection(client, app, monkeypatch):
    planning = options(client)
    choose(client, planning)
    before = app.extensions['novel_engine'].repository.load()
    def fail(*args): raise ProviderError('offline')
    monkeypatch.setattr(app.extensions['novel_engine'].director.planner.provider, 'complete', fail)
    assert client.post('/api/chapter/branches/regenerate', json={'chapter_number': 1, 'planning_id': planning['id']}).status_code == 502
    assert app.extensions['novel_engine'].repository.load() == before


def test_planner_retries_recoverable_output_and_receives_full_context(tmp_path):
    class Recover(MockLLMProvider):
        contexts = []
        def complete(self, task, context, schema):
            result = super().complete(task, context, schema)
            if task.startswith('plan'):
                self.contexts.append(copy.deepcopy(context))
                if len(self.contexts) == 1: result['branches'].pop()
                context['world']['roles'][0]['alive'] = False
            return result
    provider = Recover()
    client = create_app(tmp_path, provider).test_client()
    client.post('/api/project/init', json={'prompt': 'test'})
    choose(client, options(client))
    assert len(provider.contexts) == 2 and 'validation_feedback' in provider.contexts[1]
    draft = generate(client)
    client.post('/api/chapter/approve', json={'draft_id': draft['id']})
    options(client, 2)
    assert provider.contexts[-1]['previous_summary']
    assert provider.contexts[-1]['recent_state_changes']['chapter'] == 1
    assert set(provider.contexts[-1]['world']) >= {'roles', 'inventory', 'maps', 'lore', 'outline'}
    assert dashboard(client)['committed_state']['roles'][0]['alive']


def test_legacy_draft_requires_discard_and_replanning(client, app):
    choose(client, options(client))
    draft = generate(client)
    repo = app.extensions['novel_engine'].repository
    bundle = repo.load()
    bundle.pop('narrative_planning')
    bundle['chapters']['1'].pop('planning_id')
    bundle['chapters']['1'].pop('selected_branch_id')
    repo.save(bundle)
    assert client.post('/api/chapter/approve', json={'draft_id': draft['id']}).status_code == 409
    assert client.post('/api/chapter/draft/discard', json={'draft_id': draft['id']}).status_code == 200
    assert options(client)['status'] == 'generated'


@pytest.mark.parametrize('payload', [{}, {'chapter_number': True}, {'chapter_number': 0}, {'chapter_number': '1'}, {'chapter_number': 2}])
def test_invalid_chapter_request(client, payload):
    assert client.post('/api/chapter/branches/generate', json=payload).status_code in (400, 409)


def test_atomic_planning_write_failure(client, app, monkeypatch):
    repo = app.extensions['novel_engine'].repository
    before = repo.load()
    original = repo._atomic_json
    def fail(path, value):
        if path.name == 'state.json': raise OSError('disk failure')
        original(path, value)
    monkeypatch.setattr(repo, '_atomic_json', fail)
    assert client.post('/api/chapter/branches/generate', json={'chapter_number': 1}).status_code == 500
    assert repo.load() == before
