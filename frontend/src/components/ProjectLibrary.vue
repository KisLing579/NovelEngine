<script setup>
import { formatTime } from '../dashboard'
defineProps({ projects: Array, projectId: String, busy: Boolean })
defineEmits(['create', 'load'])
</script>

<template>
  <section class="card project-library">
    <div class="library-heading">
      <div><p class="eyebrow">项目空间</p><h2>项目历史 <span class="muted small">{{ projects.length }} 个项目</span></h2></div>
      <button :disabled="busy" @click="$emit('create')">＋ 新建项目</button>
    </div>
    <p class="muted small">每个项目独立保存正文、规划、世界状态和快照。切换项目会保留已保存的草稿。</p>
    <div v-if="projects.length" class="project-list">
      <article v-for="project in projects" :key="project.id" class="project-entry" :class="{ active: project.id === projectId }">
        <div class="library-heading"><h3>{{ project.name }}</h3><span v-if="project.id === projectId" class="badge">当前项目</span></div>
        <p class="muted small project-premise">{{ project.premise || '暂无设定摘要' }}</p>
        <p v-if="project.available" class="small">已批准 {{ project.chapter_number }} 章 · {{ project.draft_count }} 个草稿</p>
        <p class="muted small">最近保存：{{ formatTime(project.updated_at) }}</p>
        <p v-if="!project.available" class="error">{{ project.error }}</p>
        <button class="secondary" :disabled="busy || !project.available || project.id === projectId" @click="$emit('load', project.id)">
          {{ project.id === projectId ? '已加载' : '加载项目' }}
        </button>
      </article>
    </div>
    <p v-else class="muted">暂无历史项目，创建第一个故事开始创作。</p>
  </section>
</template>
