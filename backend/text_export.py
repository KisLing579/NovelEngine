"""Export saved chapter text in batches of three; never change project state."""
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
from .repository import EngineError


def export_chapter_text(bundle):
    chapters = [(int(number), record) for number, record in bundle['chapters'].items()
                if isinstance(record.get('text'), str) and record['text'].strip()]
    chapters.sort(key=lambda chapter: chapter[0])
    if not chapters:
        raise EngineError('暂无可下载的章节正文，请先生成章节', 'no_chapters', 404)
    files = []
    for offset in range(0, len(chapters), 3):
        batch = chapters[offset:offset + 3]
        sections = []
        for number, record in batch:
            status = '已批准' if record.get('status') == 'approved' else '未提交草稿'
            sections.append(f'第 {number} 章（{status}）\n\n{record["text"]}')
        text = ('\n\n' + '=' * 40 + '\n\n').join(sections) + '\n'
        filename = f'chapters_{batch[0][0]:03d}-{batch[-1][0]:03d}.txt'
        files.append((filename, text.encode('utf-8-sig')))
    if len(files) == 1:
        filename, content = files[0]
        return content, filename, 'text/plain; charset=utf-8'
    archive = BytesIO()
    with ZipFile(archive, 'w', compression=ZIP_DEFLATED) as zip_file:
        for filename, content in files:
            zip_file.writestr(filename, content)
    return archive.getvalue(), 'chapters_txt.zip', 'application/zip'
