import test from 'node:test'
import assert from 'node:assert/strict'
import { useDashboard } from '../src/dashboard.js'

const draft = { id: 'd1', status: 'draft', chapter_number: 1, text: '正文', review: { passed: true, feedback: [] } }
function view(record = draft) {
  return { initialized: true, project: { chapter_number: record?.status === 'approved' ? 1 : 0, active_chapter_number: 1, can_generate: true },
    current_planning: { chapter_number: 1, status: 'selected', selected_branch_id: 'b1' },
    current_draft: record?.status === 'draft' ? record : null, committed_state: { chapter_number: record?.status === 'approved' ? 1 : 0 },
    chapters: [{ chapter_number: 1, status: record?.status || 'not_generated' }, { chapter_number: 2, status: 'not_generated' }], snapshots: [] }
}
const ok = data => ({ ok: true, status: 200, json: async () => ({ ok: true, data }) })

test('TXT download saves server file without changing dashboard data', async () => {
  const blob = new Blob(['正文'])
  const saved = []
  const ui = useDashboard(async url => {
    assert.equal(url, '/api/project/export/txt')
    return { ok: true, headers: new Headers({ 'Content-Disposition': 'attachment; filename="chapters_txt.zip"' }), blob: async () => blob }
  }, (content, name) => saved.push({ content, name }))
  await ui.downloadTxt()
  assert.deepEqual(saved, [{ content: blob, name: 'chapters_txt.zip' }])
  assert.equal(ui.dashboard.value, null)
  assert.equal(ui.error.value, '')
})

test('TXT download errors are shown rather than saved as text files', async () => {
  const ui = useDashboard(async () => ({ ok: false, status: 404, json: async () => ({ error: { message: '暂无正文' } }) }), () => assert.fail('Must not download error response'))
  await ui.downloadTxt()
  assert.equal(ui.error.value, '暂无正文')
  assert.equal(ui.busy.value, false)
})

test('approval refreshes server state and loads approved text', async () => {
  const calls = []; let approved = false
  const ui = useDashboard(async (url, options) => {
    calls.push(url)
    if (url.endsWith('/approve')) { assert.equal(JSON.parse(options.body).draft_id, 'd1'); approved = true; return ok({}) }
    if (url.endsWith('/dashboard')) return ok(view(approved ? { ...draft, status: 'approved' } : draft))
    return ok({ ...draft, status: 'approved' })
  })
  await ui.reload(); assert.equal(ui.canApprove.value, true)
  await ui.approve()
  assert.equal(ui.record.value.status, 'approved')
  assert.equal(ui.dashboard.value.committed_state.chapter_number, 1)
  assert.equal(ui.canApprove.value, false)
  assert.deepEqual(calls, ['/api/dashboard', '/api/chapter/approve', '/api/dashboard', '/api/chapter/draft/1', '/api/chapter/planning/1'])
})

test('failed review refreshes feedback and blocks approve', async () => {
  let failed = false
  const ui = useDashboard(async (url) => {
    if (url.endsWith('/generate')) { failed = true; return { ok: false, status: 422, json: async () => ({ ok: false, error: { message: '机审失败' } }) } }
    return ok(view(failed ? { ...draft, review: { passed: false, feedback: ['物品冲突'] } } : null))
  })
  await ui.reload(); await ui.generate()
  assert.equal(ui.error.value, '机审失败')
  assert.deepEqual(ui.record.value.review.feedback, ['物品冲突'])
  assert.equal(ui.canApprove.value, false)
})

test('rollback removes stale draft from selected workspace', async () => {
  let rolledBack = false
  const ui = useDashboard(async (url) => {
    if (url.endsWith('/rollback')) { rolledBack = true; return ok({}) }
    return ok(view(rolledBack ? null : draft))
  })
  await ui.reload(); await ui.rollback(0)
  assert.equal(ui.record.value, null)
  assert.equal(ui.selectedChapter.value.status, 'not_generated')
  assert.equal(ui.canApprove.value, false)
})

test('future chapter does not load old text and cannot be approved', async () => {
  const calls = []
  const ui = useDashboard(async url => { calls.push(url); return ok(view()) })
  await ui.reload(); await ui.select(2)
  assert.equal(ui.record.value, null)
  assert.equal(ui.canApprove.value, false)
  assert.deepEqual(calls, ['/api/dashboard'])
})

test('refresh failure clears stale actions', async () => {
  let fail = false
  const ui = useDashboard(async () => { if (fail) throw new Error('offline'); return ok(view()) })
  await ui.reload(); fail = true; await ui.reload()
  assert.equal(ui.dashboard.value, null)
  assert.equal(ui.canApprove.value, false)
  assert.equal(ui.canGenerate.value, false)
})

test('concurrent refresh does not duplicate requests', async () => {
  let resolve, calls = 0
  const ui = useDashboard(() => { calls++; return new Promise(r => { resolve = r }) })
  const first = ui.reload(); await ui.reload()
  assert.equal(calls, 1)
  resolve(ok(view())); await first
  assert.equal(ui.busy.value, false)
})

test('no selected branch disables chapter generation even if stale server flag is true', async () => {
  const data = view(null); data.current_planning.selected_branch_id = null
  const calls = []
  const ui = useDashboard(async url => { calls.push(url); return ok(data) })
  await ui.reload(); await ui.generate()
  assert.equal(ui.canGenerate.value, false)
  assert.deepEqual(calls, ['/api/dashboard'])
})

test('regenerate clears selection and posts only planning identifiers', async () => {
  const data = view(null); data.project.can_plan = true
  data.current_planning.id = 'p1'
  const ui = useDashboard(async (url, options) => {
    if (url.endsWith('/regenerate')) {
      assert.deepEqual(JSON.parse(options.body), { chapter_number: 1, planning_id: 'p1' })
      data.current_planning = { chapter_number: 1, id: 'p2', status: 'generated', selected_branch_id: null }
    }
    return ok(data)
  })
  await ui.reload(); await ui.generateOptions()
  assert.equal(ui.canGenerate.value, false)
  assert.equal(ui.selectedPlanning.value.id, 'p2')
})

test('draft blocks changing branch; discard refreshes planning and unlocks', async () => {
  const data = view(); data.project.can_plan = true
  data.current_planning.id = 'p1'; data.current_planning.status = 'draft_generated'
  const calls = []
  const ui = useDashboard(async (url, options) => {
    calls.push(url)
    if (url.endsWith('/discard')) {
      assert.deepEqual(JSON.parse(options.body), { draft_id: 'd1' })
      data.current_draft = null; data.chapters[0].status = 'not_generated'; data.current_planning.status = 'selected'
    }
    if (url.endsWith('/select')) {
      assert.deepEqual(JSON.parse(options.body), { planning_id: 'p1', branch_id: 'b2' })
      data.current_planning.selected_branch_id = 'b2'
    }
    return ok(data)
  })
  await ui.reload(); await ui.chooseBranch('b2'); await ui.generateOptions()
  assert.deepEqual(calls, ['/api/dashboard'])
  await ui.discardDraft(); await ui.chooseBranch('b2')
  assert.equal(ui.selectedPlanning.value.selected_branch_id, 'b2')
  assert.equal(ui.record.value, null)
})

test('creating and loading projects resets chapter selection and scopes subsequent requests', async () => {
  let active = 'first'
  const headers = []
  const ui = useDashboard(async (url, options) => {
    headers.push([url, options.headers?.['X-Project-ID']])
    if (url.endsWith('/init')) {
      assert.deepEqual(JSON.parse(options.body), { prompt: 'new story', name: 'New project' })
      active = 'second'
      return ok({ project_id: active })
    }
    if (url.endsWith('/load')) {
      active = JSON.parse(options.body).project_id
      return ok({ project_id: active })
    }
    const data = view(active === 'first' ? draft : null)
    return ok({ ...data, project_id: active, projects: [{ id: 'first' }, { id: 'second' }] })
  })
  await ui.reload()
  await ui.select(2)
  await ui.initialize('new story', 'New project')
  assert.equal(ui.projectId.value, 'second')
  assert.equal(ui.selectedNumber.value, 1)
  assert.equal(ui.record.value, null)
  assert.equal(ui.canApprove.value, false)
  await ui.loadProject('first')
  assert.equal(ui.record.value.id, draft.id)
  assert.equal(ui.projects.value.length, 2)
  assert.deepEqual(headers.filter(([url]) => url.endsWith('/dashboard')).map(([, id]) => id),
    [undefined, 'second', 'first'])
})

test('failed project load leaves the current workspace intact', async () => {
  const ui = useDashboard(async url => {
    if (url.endsWith('/load')) return { ok: false, status: 404, json: async () => ({ error: { message: '项目不存在' } }) }
    return ok({ ...view(), project_id: 'original', projects: [] })
  })
  await ui.reload()
  await ui.loadProject('missing')
  assert.equal(ui.projectId.value, 'original')
  assert.equal(ui.record.value.id, draft.id)
  assert.equal(ui.error.value, '项目不存在')
  assert.equal(ui.busy.value, false)
})

test('Chinese legacy directory IDs are encoded in request headers and downloads', async () => {
  const seen = []
  const ui = useDashboard(async (url, options) => {
    seen.push(options.headers?.['X-Project-ID'])
    if (url.endsWith('/txt')) return { ok: true, headers: new Headers(), blob: async () => new Blob(['text']) }
    return ok({ ...view(), project_id: '旅人', projects: [] })
  }, () => {})
  await ui.reload()
  await ui.reload()
  await ui.downloadTxt()
  assert.deepEqual(seen, [undefined, encodeURIComponent('旅人'), encodeURIComponent('旅人')])
})

test('project history remains accessible when the selected project cannot be read', async () => {
  const ui = useDashboard(async url => {
    if (url.endsWith('/projects')) return ok({ projects: [{ id: 'healthy' }] })
    throw new Error('项目数据损坏')
  })
  await ui.reload()
  assert.equal(ui.dashboard.value, null)
  assert.equal(ui.projects.value[0].id, 'healthy')
  assert.equal(ui.error.value, '项目数据损坏')
})
