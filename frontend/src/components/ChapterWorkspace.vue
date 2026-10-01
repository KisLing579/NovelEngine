<script setup>
import { statusLabel } from '../dashboard'
defineProps({ chapter: Object, record: Object, busy: Boolean, canGenerate: Boolean, canApprove: Boolean })
defineEmits(['generate', 'approve'])
</script>
<template>
  <section class="card chapter-workspace"><p class="eyebrow">Current Chapter Workspace</p>
    <template v-if="chapter">
      <div class="section-heading"><h2>第 {{ chapter.chapter_number }} 章</h2><span class="badge" :class="chapter.status">{{ statusLabel(chapter.status) }}</span></div>
      <div class="chapter-plan"><h3>本章目标</h3><p>{{ chapter.goal }}</p></div>
      <template v-if="record">
        <div class="workspace-notice" :class="record.status === 'approved' ? 'committed' : 'uncommitted'">{{ record.status === 'approved' ? '正式正文 · 本章已批准并提交状态' : '未提交草稿 · 机审通过也不会改变正式世界状态' }}</div>
        <article class="chapter-body" :aria-label="record.status === 'approved' ? '正式正文' : '草稿正文'">{{ record.text }}</article>
        <section class="review-box" aria-label="机审反馈"><div class="section-heading"><h3>Review Feedback</h3><span class="badge" :class="record.review.passed ? 'approved' : 'failed'">{{ record.review.passed ? 'PASS · 机审通过' : 'FAIL · 机审未通过' }}</span></div><p class="small muted">生成 {{ record.attempts }} 次</p><ul v-if="record.review.feedback.length"><li v-for="(item, index) in record.review.feedback" :key="index">{{ item }}</li></ul><p v-else class="muted">未检测到冲突。</p></section>
      </template>
      <p v-else class="empty">{{ busy ? '正在读取章节…' : '本章尚未生成，以上为章节计划。' }}</p>
      <div v-if="chapter.chapter_actual_summary" class="actual-summary"><h3>本章实际剧情摘要</h3><p>{{ chapter.chapter_actual_summary }}</p></div>
      <div class="actions" v-if="chapter.is_current && chapter.status !== 'approved'"><button :disabled="!canGenerate" @click="$emit('generate')">{{ record ? 'Regenerate 重新生成草稿' : 'Generate 生成本章' }}</button><button :disabled="!canApprove" @click="$emit('approve')">Approve 批准并提交</button></div>
    </template><p v-else class="empty">选择章节以查看正文或大纲。</p>
  </section>
</template>
