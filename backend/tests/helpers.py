import json


def project_root(data_dir):
    """Resolve the selected project when checking its on-disk state."""
    selected = json.loads((data_dir / '.active-project.json').read_text('utf-8'))['project_id']
    return data_dir if selected == '@legacy' else data_dir / selected


def select_default_branch(client):
    """Add the new Phase 3 precondition without changing earlier assertions."""
    planning = client.get('/api/chapter/planning/').json['data']
    if planning['status'] == 'none':
        response = client.post('/api/chapter/branches/generate', json={'chapter_number': planning['chapter_number']})
        assert response.status_code == 200
        planning = response.json['data']
    if not planning['selected_branch_id']:
        branch = next(b for b in planning['branches'] if b['strategy'] == 'progression')
        response = client.post('/api/chapter/branches/select', json={'planning_id': planning['id'], 'branch_id': branch['id']})
        assert response.status_code == 200
