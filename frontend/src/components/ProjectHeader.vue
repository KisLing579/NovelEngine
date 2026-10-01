<script setup>
import { computed } from 'vue'
import { statusLabel } from '../dashboard'
const props = defineProps({ dashboard: Object, busy: Boolean, canGenerate: Boolean, canApprove: Boolean })
defineEmits(['refresh', 'generate', 'approve', 'snapshots', 'download-txt'])
const canExport = computed(() => !!props.dashboard?.project?.chapter_number)
const canExportTxt = computed(() => props.dashboard?.chapters?.some(chapter => chapter.status === 'approved' || chapter.status === 'draft'))
const downloadPdf = () => {
  const a = document.createElement('a')
  a.href = '/api/project/export/pdf' + (props.dashboard?.project_id
    ? `?project_id=${encodeURIComponent(props.dashboard.project_id)}` : '')
  a.download = 'novel.pdf'
  a.click()
}
</script>
<template>
  <header class="project-header">
    <div class="header-title"><p class="eyebrow">小说引擎 / Phase 3</p><h1>Story Dashboard</h1></div>
    <div class="header-project">
      <h2>{{ dashboard?.project?.name || (dashboard?.initialized ? '未命名项目' : '尚未初始化') }}</h2>
      <div class="meta-row" v-if="dashboard?.project"><span>当前卷：{{ dashboard.project.volume || '未分卷' }}</span><span>已批准至第 <strong>{{ dashboard.project.chapter_number }}</strong> 章</span><span>当前工作章：{{ dashboard.project.active_chapter_number }}</span><span class="badge" :class="dashboard.project.status">{{ statusLabel(dashboard.project.status) }}</span></div>
      <p class="muted small">{{ dashboard?.provider?.name || '等待连接' }}<template v-if="dashboard?.provider?.model"> / {{ dashboard.provider.model }}</template><span class="separator">·</span> 最近快照：{{ dashboard?.latest_snapshot?.name || '暂无' }}</p>
    </div>
    <div class="header-actions"><button class="secondary" :disabled="busy" @click="$emit('refresh')">刷新</button><button class="secondary" :disabled="!canExport" @click="downloadPdf">下载 PDF</button><button class="secondary" :disabled="busy || !canExportTxt" title="每三章一个 TXT，多个文件打包为 ZIP，包含草稿" @click="$emit('download-txt')">下载到txt</button><button :disabled="!canGenerate" @click="$emit('generate')">{{ dashboard?.current_draft ? 'Regenerate 重新生成' : 'Generate Chapter' }}</button><button :disabled="!canApprove" @click="$emit('approve')">Approve Chapter</button><button class="secondary" :disabled="busy || !dashboard?.initialized" @click="$emit('snapshots')">Rollback / 快照</button></div>
  </header>
</template>
