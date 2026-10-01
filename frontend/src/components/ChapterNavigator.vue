<script setup>
import { statusLabel } from '../dashboard'
defineProps({ chapters: Array, premise: String, selected: Number, busy: Boolean })
defineEmits(['select'])
</script>
<template>
  <aside class="card navigator"><p class="eyebrow">Outline / Chapters</p><h2>故事导航</h2>
    <details class="premise"><summary>小说设定 · 未分卷</summary><p>{{ premise }}</p></details>
    <nav aria-label="章节导航"><button v-for="chapter in chapters" :key="chapter.chapter_number" class="chapter-link" :class="{ selected: selected === chapter.chapter_number }" :disabled="busy" :aria-current="selected === chapter.chapter_number ? 'page' : undefined" @click="$emit('select', chapter.chapter_number)">
      <span class="chapter-heading">第 {{ chapter.chapter_number }} 章 <small v-if="chapter.is_current">当前工作章</small><small v-else-if="chapter.is_committed_head">最新批准</small></span><span class="chapter-goal">{{ chapter.goal }}</span><span class="badge" :class="chapter.status">{{ statusLabel(chapter.status) }}</span>
    </button></nav>
  </aside>
</template>
