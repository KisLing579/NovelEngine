<script setup>
import { computed, ref, watch } from 'vue'
import { formatTime } from '../dashboard'
const props = defineProps({ planning: Object, chapterNumber: Number, busy: Boolean, isWorking: Boolean, canPlan: Boolean, draft: Object })
defineEmits(['generate-options', 'choose', 'discard'])
const confirmDiscard = ref(false)
const selected = computed(() => props.planning?.branches?.find(b => b.id === props.planning.selected_branch_id))
const strategies = { progression: 'A · Progression 稳步推进', escalation: 'B · Escalation 升级冲突', revelation: 'C · Revelation 揭示秘密' }
watch(() => props.draft?.id, () => { confirmDiscard.value = false })
</script>
<template>
  <section class="card story-directions">
    <p class="eyebrow">Narrative Planning / Story Directions</p>
    <div class="section-heading"><h2>第 {{ chapterNumber }} 章 · 剧情路线</h2><span class="badge" :class="planning?.status === 'approved' ? 'approved' : 'draft'">{{ planning?.status || 'none' }}</span></div>
    <p class="small muted">候选与选择是未提交计划；正式世界只在批准正文后更新。</p>
    <p v-if="!planning?.branches?.length" class="empty">{{ isWorking ? '先生成三个不同策略的候选，再选择路线并生成正文。' : '该章节暂无规划记录。只有当前工作章可以生成候选。' }}</p>
    <div v-if="selected" class="selected-direction"><strong>Selected Story Direction：{{ selected.title }}</strong><p class="small">{{ strategies[selected.strategy] }} · 选择于 {{ formatTime(planning.selected_at) }}</p></div>
    <div v-if="planning?.branches?.length" class="branch-cards">
      <article v-for="branch in planning.branches" :key="branch.id" class="branch-card" :class="{ chosen: branch.id === planning.selected_branch_id }">
        <div class="section-heading"><span class="badge" :class="branch.strategy">{{ strategies[branch.strategy] }}</span><strong v-if="branch.id === planning.selected_branch_id" class="selected-badge">Selected</strong></div>
        <h3>{{ branch.title }}</h3><p>{{ branch.summary }}</p>
        <h4>章节目标</h4><p>{{ branch.chapter_goal }}</p>
        <h4>Expected Events</h4><ul><li v-for="(event, i) in branch.expected_events" :key="i">{{ event }}</li></ul>
        <h4>Character Impacts</h4><ul><li v-for="(impact, i) in branch.character_impacts" :key="i">{{ impact.character_id }}：{{ impact.description }}</li></ul><p v-if="!branch.character_impacts.length">无计划变化</p>
        <h4>World Impacts</h4><ul><li v-for="(impact, i) in branch.world_impacts" :key="i">{{ impact }}</li></ul><p v-if="!branch.world_impacts.length">无计划变化</p>
        <h4>Hook</h4><p>{{ branch.hook }}</p><h4>Risk</h4><p>{{ branch.risk }}</p>
        <button v-if="isWorking" class="secondary" :disabled="!canPlan || !!draft || branch.id === planning.selected_branch_id" @click="$emit('choose', branch.id)">{{ branch.id === planning.selected_branch_id ? '已选择' : `Choose ${branch.strategy}` }}</button>
      </article>
    </div>
    <div v-if="isWorking" class="actions">
      <button :disabled="!canPlan || !!draft" @click="$emit('generate-options')">{{ planning?.branches?.length ? 'Regenerate Story Options' : 'Generate Story Options' }}</button>
      <button v-if="draft && !confirmDiscard" class="secondary danger" :disabled="busy" @click="confirmDiscard = true">Discard Draft</button>
    </div>
    <div v-if="draft && isWorking" class="small notice discard-notice">
      <p>已有未提交草稿。更换或重新生成路线前，必须先丢弃草稿。</p>
      <template v-if="confirmDiscard"><p>将删除本章未提交正文与机审记录，保留候选和当前选择；已批准状态不受影响。</p><div class="actions"><button class="danger secondary" :disabled="busy" @click="$emit('discard')">确认丢弃草稿</button><button class="secondary" :disabled="busy" @click="confirmDiscard = false">取消</button></div></template>
    </div>
    <p v-if="planning?.status === 'approved'" class="small muted">历史规划已随本章批准保留，仅供查阅。</p>
  </section>
</template>
