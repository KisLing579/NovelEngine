import { computed, ref } from 'vue'

export const statusLabel = (s) => ({ ready: 'ready · 就绪', reviewed: 'reviewed · 待人工批准', draft: 'draft · 草稿', approved: 'approved · 已批准', not_generated: 'not generated · 未生成' }[s] || s)
export const formatTime = (v) => v ? new Date(v).toLocaleString('zh-CN', { hour12: false }) : '时间未记录'
export const displayValue = (v) => v == null ? '—' : typeof v === 'object' ? JSON.stringify(v) : String(v)

function saveDownload(blob, filename) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function useDashboard(fetcher = globalThis.fetch, saveFile = saveDownload) {
  const dashboard = ref(null), selectedNumber = ref(null), record = ref(null), historicalPlanning = ref(null)
  const projects = ref([]), projectId = ref(null)
  const busy = ref(false), error = ref(''), message = ref('')
  const selectedChapter = computed(() => dashboard.value?.chapters.find(c => c.chapter_number === selectedNumber.value))
  const selectedPlanning = computed(() => selectedNumber.value === dashboard.value?.current_planning?.chapter_number
    ? dashboard.value.current_planning : historicalPlanning.value)
  const canGenerate = computed(() => !!dashboard.value?.project?.can_generate &&
    !!dashboard.value?.current_planning?.selected_branch_id && !busy.value)
  const canPlan = computed(() => !busy.value && !!dashboard.value?.project?.can_plan && !dashboard.value?.current_draft)
  const canApprove = computed(() => !busy.value && record.value?.status === 'draft' && record.value?.review.passed && record.value?.id === dashboard.value?.current_draft?.id)
  async function api(path, data) {
    const headers = projectId.value ? { 'X-Project-ID': encodeURIComponent(projectId.value) } : {}
    const response = await fetcher(`/api/${path}`, data === undefined ? { headers } : {
      method: 'POST', headers: { ...headers, 'Content-Type': 'application/json' }, body: JSON.stringify(data),
    })
    let result
    try { result = await response.json() } catch { throw new Error(`服务返回无效响应 (${response.status})`) }
    if (!response.ok || !result.ok) throw new Error(result.error?.message || `请求失败 (${response.status})`)
    return result.data
  }
  async function loadRecord() {
    record.value = null
    historicalPlanning.value = null
    const chapter = selectedChapter.value
    if (!chapter || chapter.status === 'not_generated') return
    if (chapter.status === 'draft') record.value = dashboard.value.current_draft
    else {
      const [text, planning] = await Promise.all([api(`chapter/draft/${chapter.chapter_number}`), api(`chapter/planning/${chapter.chapter_number}`)])
      record.value = text
      historicalPlanning.value = planning
    }
  }
  async function refresh(preferredNumber) {
    record.value = null
    try {
      const next = await api('dashboard')
      projectId.value = next.project_id ?? null
      projects.value = next.projects ?? []
      dashboard.value = next
      const preferred = preferredNumber ?? selectedNumber.value ?? next.project?.active_chapter_number
      selectedNumber.value = next.chapters.some(c => c.chapter_number === preferred) ? preferred : next.project?.active_chapter_number ?? null
      await loadRecord()
    } catch (e) { dashboard.value = null; throw e }
  }
  async function run(action) {
    if (busy.value) return
    busy.value = true; error.value = ''; message.value = ''
    try { await action() } catch (e) { error.value = e.message } finally { busy.value = false }
  }
  async function mutate(path, data, preferredNumber, successMessage) {
    let failure
    try { await api(path, data) } catch (e) { failure = e }
    // Failed review also saves a draft. Always reconcile with the server.
    await refresh(preferredNumber)
    if (failure) throw failure
    message.value = successMessage
  }
  const reload = () => run(async () => {
    try { await refresh() } catch (e) {
      // Keep project recovery available even if the selected project's data is damaged.
      try { projects.value = (await api('projects')).projects } catch { /* Preserve the original error. */ }
      throw e
    }
  })
  const downloadTxt = () => run(async () => {
    const response = await fetcher('/api/project/export/txt', {
      headers: projectId.value ? { 'X-Project-ID': encodeURIComponent(projectId.value) } : {},
    })
    if (!response.ok) {
      let result
      try { result = await response.json() } catch { /* Non-JSON proxy failure. */ }
      throw new Error(result?.error?.message || `下载失败 (${response.status})`)
    }
    const disposition = response.headers.get('Content-Disposition') || ''
    const filename = disposition.match(/filename="([^"]+)"/)?.[1] || 'chapters.txt'
    saveFile(await response.blob(), filename)
    message.value = '下载已开始，每三章一个 TXT，包含已保存的草稿与批准正文。'
  })
  const select = (number) => run(async () => { selectedNumber.value = number; await loadRecord() })
  async function switchProject(path, data, successMessage) {
    const result = await api(path, data)
    projectId.value = result.project_id
    dashboard.value = null
    selectedNumber.value = null
    record.value = null
    historicalPlanning.value = null
    await refresh()
    message.value = successMessage
  }
  const initialize = (prompt, name) => run(() => switchProject('project/init',
    { prompt, ...(name === undefined ? {} : { name }) }, '新项目已创建，state_0 已保存。原项目仍保留在历史列表中。'))
  const loadProject = (id) => run(() => switchProject('project/load', { project_id: id }, '项目已加载，可以继续创作。'))
  const generate = () => {
    if (!canGenerate.value) return
    return run(() => mutate('chapter/generate', {}, dashboard.value.project.chapter_number + 1, '机审通过。草稿尚未提交，请阅读后批准。'))
  }
  const approve = () => {
    if (!canApprove.value) return
    const { id, chapter_number } = record.value
    return run(() => mutate('chapter/approve', { draft_id: id }, chapter_number, '章节已批准，正式状态、变化记录和快照已更新。'))
  }
  const rollback = (number) => run(() => mutate('project/rollback', { chapter_number: number }, number || 1, `已回档到 state_${number}，后续草稿与状态已清除。`))
  const generateOptions = () => {
    if (!canPlan.value) return
    const planning = dashboard.value.current_planning
    const regenerate = planning.status !== 'none'
    const data = { chapter_number: planning.chapter_number }
    if (regenerate) data.planning_id = planning.id
    return run(() => mutate(`chapter/branches/${regenerate ? 'regenerate' : 'generate'}`, data,
      planning.chapter_number, '三个候选已保存，请选择一条剧情路线。'))
  }
  const chooseBranch = (branchId) => {
    if (!canPlan.value) return
    const planning = dashboard.value.current_planning
    return run(() => mutate('chapter/branches/select', { planning_id: planning.id, branch_id: branchId },
      planning.chapter_number, '所选剧情路线已保存，现在可以生成正文。'))
  }
  const discardDraft = () => {
    const draft = dashboard.value?.current_draft
    if (busy.value || !draft) return
    return run(() => mutate('chapter/draft/discard', { draft_id: draft.id }, draft.chapter_number,
      '未提交草稿已丢弃，保留候选与当前选择。现在可以更换路线。'))
  }
  return { dashboard, projects, projectId, loadProject, selectedNumber, selectedChapter, selectedPlanning, record, busy, error, message,
    canGenerate, canApprove, canPlan, reload, select, initialize, generate, approve, rollback,
    generateOptions, chooseBranch, discardDraft, downloadTxt }
}
