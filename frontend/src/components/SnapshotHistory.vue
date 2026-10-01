<script setup>
import { ref, watch } from 'vue'
import { formatTime } from '../dashboard'
const props = defineProps({ snapshots: Array, busy: Boolean })
defineEmits(['rollback'])
const selected = ref(null)
watch(() => props.snapshots, (snapshots) => { selected.value = snapshots.find(s => s.is_current)?.chapter_number ?? null }, { immediate: true })
</script>
<template>
  <section class="card snapshot-history"><p class="eyebrow">Snapshot History</p><h2>快照与回档</h2><p class="muted small">回档将恢复目标章节，并清除其后的正文、草稿、状态变化与快照。</p>
    <label for="snapshot-select">选择目标快照</label><div class="snapshot-controls"><select id="snapshot-select" v-model="selected" :disabled="busy"><option v-for="snapshot in snapshots" :key="snapshot.name" :value="snapshot.chapter_number">{{ snapshot.name }} · 第 {{ snapshot.chapter_number }} 章{{ snapshot.is_current ? '（当前）' : '' }}</option></select><button class="danger secondary" :disabled="busy || selected === null" @click="$emit('rollback', selected)">Rollback 回档</button></div>
    <div class="table-scroll"><table><thead><tr><th>快照</th><th>章节</th><th>创建时间</th><th>状态</th></tr></thead><tbody><tr v-for="snapshot in snapshots" :key="snapshot.name"><td>{{ snapshot.name }}</td><td>{{ snapshot.chapter_number }}</td><td>{{ formatTime(snapshot.created_at) }}</td><td><span v-if="snapshot.is_current" class="badge approved">当前</span><span v-else class="muted">历史</span></td></tr></tbody></table></div>
  </section>
</template>
