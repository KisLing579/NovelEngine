<script setup>
import { onMounted, ref } from 'vue'
import { useDashboard } from './dashboard'
import ProjectHeader from './components/ProjectHeader.vue'
import ChapterNavigator from './components/ChapterNavigator.vue'
import ChapterWorkspace from './components/ChapterWorkspace.vue'
import StoryStatePanel from './components/StoryStatePanel.vue'
import StateChanges from './components/StateChanges.vue'
import SnapshotHistory from './components/SnapshotHistory.vue'
import StoryDirections from './components/StoryDirections.vue'
import ProjectLibrary from './components/ProjectLibrary.vue'
const { dashboard, projects, projectId, loadProject, selectedNumber, selectedChapter, selectedPlanning, record, busy, error, message,
  canGenerate, canApprove, canPlan, reload, select, initialize, generate, approve, rollback,
  generateOptions, chooseBranch, discardDraft, downloadTxt } = useDashboard()
const prompt = ref('一位旅人在陌生世界寻找回家的路，沿途收集路标石。')
const projectName = ref('')
const showNewProject = ref(false)
async function createProject() {
  await initialize(prompt.value, projectName.value.trim())
  if (!error.value) { showNewProject.value = false; projectName.value = '' }
}
async function openProject(id) {
  await loadProject(id)
  if (!error.value) showNewProject.value = false
}
const snapshotPanel = ref(null)
onMounted(reload)
</script>
<template>
  <main :aria-busy="busy">
    <ProjectHeader :dashboard="dashboard" :busy="busy" :can-generate="canGenerate" :can-approve="canApprove" @refresh="reload" @generate="generate" @approve="approve" @download-txt="downloadTxt" @snapshots="snapshotPanel?.$el.scrollIntoView({ block: 'center' })" />
    <div class="notifications" aria-live="polite"><p v-if="busy" class="notice">正在处理，请稍候…</p><p v-if="error" class="error" role="alert">{{ error }}</p><p v-if="message" class="success" role="status">{{ message }}</p></div>
    <ProjectLibrary :projects="projects" :project-id="projectId" :busy="busy" @create="showNewProject = true" @load="openProject" />
    <section v-if="showNewProject || (dashboard && !dashboard.initialized)" class="card setup">
      <p class="eyebrow">开始一个故事</p><h2>新建小说项目</h2><p class="muted">输入名称和设定，建立独立的角色、物品、地图和章节大纲。</p>
      <p v-if="dashboard?.provider.name === 'MockLLMProvider'" class="notice">当前为 Mock 模式：使用固定路标故事验证流程，并保留你的初始设定。</p>
      <label for="project-name">项目名称</label><input id="project-name" v-model="projectName" maxlength="80" :disabled="busy" placeholder="例如：旅人的归途" />
      <label for="premise">小说设定</label><textarea id="premise" v-model="prompt" rows="5" maxlength="20000" :disabled="busy" />
      <div class="header-actions"><button :disabled="busy || !prompt.trim() || !projectName.trim()" @click="createProject">创建项目</button><button v-if="dashboard?.initialized" class="secondary" :disabled="busy" @click="showNewProject = false">取消</button></div>
    </section>
    <div v-else-if="dashboard?.initialized" class="dashboard-layout">
      <ChapterNavigator :chapters="dashboard.chapters" :premise="dashboard.committed_state.outline.premise" :selected="selectedNumber" :busy="busy" @select="select" />
      <div class="workspace-column">
        <StoryDirections :planning="selectedPlanning" :chapter-number="selectedNumber" :busy="busy"
          :is-working="selectedNumber === dashboard.current_planning?.chapter_number"
          :can-plan="canPlan" :draft="record?.status === 'draft' ? record : null"
          @generate-options="generateOptions" @choose="chooseBranch" @discard="discardDraft" />
        <ChapterWorkspace :chapter="selectedChapter" :record="record" :busy="busy" :can-generate="canGenerate" :can-approve="canApprove" @generate="generate" @approve="approve" />
        <StateChanges :log="dashboard.recent_state_changes" />
        <SnapshotHistory ref="snapshotPanel" :snapshots="dashboard.snapshots" :busy="busy" @rollback="rollback" />
      </div>
      <StoryStatePanel :world="dashboard.committed_state" />
    </div>
    <section v-else-if="!busy" class="card empty">无法加载 Dashboard。请确认后端已启动，再点击刷新。</section>
  </main>
</template>
