from backend.tests.helpers import project_root
from io import BytesIO
from zipfile import ZipFile
import pytest
from backend.app import create_app
from backend.providers import MockLLMProvider
from backend.text_export import export_chapter_text


@pytest.mark.parametrize('count', [1, 3, 4, 6, 7, 10])
def test_groups_of_three_keep_every_text_in_numeric_order(count):
    # Reversed insertion order exercises sorting rather than dict/file order.
    records = {str(n): {'text': f'唯一正文标记{n}。\n原始换行。',
                        'status': 'draft' if n == count else 'approved'} for n in range(count, 0, -1)}
    content, filename, mime = export_chapter_text({'chapters': records})
    if count <= 3:
        assert filename == f'chapters_001-{count:03d}.txt'
        assert mime.startswith('text/plain')
        contents = [content]
    else:
        assert filename == 'chapters_txt.zip' and mime == 'application/zip'
        with ZipFile(BytesIO(content)) as archive:
            assert archive.namelist() == [f'chapters_{start:03d}-{min(start + 2, count):03d}.txt'
                                         for start in range(1, count + 1, 3)]
            contents = [archive.read(name) for name in archive.namelist()]
    for batch, raw in enumerate(contents):
        assert raw.startswith(b'\xef\xbb\xbf')
        text = raw.decode('utf-8-sig')
        expected = list(range(batch * 3 + 1, min(batch * 3 + 4, count + 1)))
        assert text.count('唯一正文标记') == len(expected)
        assert [text.index(records[str(n)]['text']) for n in expected] == sorted(text.index(records[str(n)]['text']) for n in expected)
    assert '未提交草稿' in contents[-1].decode('utf-8-sig')


def test_download_endpoint_is_read_only_and_reports_empty_project(tmp_path):
    app = create_app(tmp_path, MockLLMProvider())
    client = app.test_client()
    assert client.get('/api/project/export/txt').status_code == 409
    client.post('/api/project/init', json={'prompt': '测试小说'})
    response = client.get('/api/project/export/txt')
    assert response.status_code == 404 and response.json['error']['code'] == 'no_chapters'
    repo = app.extensions['novel_engine'].repository
    bundle = repo.load()
    bundle['chapters'] = {'1': {'text': '这是草稿正文。', 'status': 'draft'}}
    repo.save(bundle)
    before = (project_root(tmp_path) / 'state.json').read_bytes()
    response = client.get('/api/project/export/txt')
    assert response.status_code == 200
    assert 'attachment;' in response.headers['Content-Disposition']
    assert response.headers['Cache-Control'] == 'no-store'
    assert '这是草稿正文。' in response.data.decode('utf-8-sig')
    assert (project_root(tmp_path) / 'state.json').read_bytes() == before
    client.post('/api/project/rollback', json={'chapter_number': 0})
    assert client.get('/api/project/export/txt').status_code == 404
