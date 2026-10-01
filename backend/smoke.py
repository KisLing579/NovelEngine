"""Run against a running server with a NEW, disposable NOVEL_DATA_DIR."""
import argparse
import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:5000')
    args = parser.parse_args()
    with httpx.Client(base_url=args.base_url, timeout=30) as client:
        def call(method, path, data=None):
            response = client.request(method, '/api/' + path, json=data)
            response.raise_for_status()
            payload = response.json()
            assert payload['ok'], payload
            return payload['data']

        status = call('GET', 'project/status')
        if status['initialized']:
            raise SystemExit('Use a fresh disposable data directory; smoke test will not overwrite an existing project.')
        initial = call('POST', 'project/init', {'prompt': '旅人寻找归乡路，沿途收集路标。'})['world']
        planning = call('POST', 'chapter/branches/generate', {'chapter_number': 1})
        branch = next(b for b in planning['branches'] if b['strategy'] == 'progression')
        call('POST', 'chapter/branches/select', {'planning_id': planning['id'], 'branch_id': branch['id']})
        draft = call('POST', 'chapter/generate', {})
        assert call('GET', 'chapter/draft/')['id'] == draft['id']
        assert call('GET', 'project/status')['world'] == initial
        approved = call('POST', 'chapter/approve', {'draft_id': draft['id']})
        assert approved['chapter_number'] == 1
        assert approved['world']['inventory'][0]['quantity'] == 1
        assert approved['snapshots'] == [0, 1]
        assert call('POST', 'project/rollback', {'chapter_number': 0})['world'] == initial
        print('PASS: status -> init -> generate -> draft -> approve -> snapshot -> rollback')


if __name__ == '__main__':
    main()
