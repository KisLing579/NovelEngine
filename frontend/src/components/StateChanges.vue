<script setup>
import { displayValue } from '../dashboard'
defineProps({ log: Object })
const domainName = { roles: '角色', inventory: '物品', maps: '地图', lore: '设定' }
const fieldName = { name: '名称', alive: '生存状态', condition: '当前状态', location_id: '位置 ID', owner_id: '持有人 ID', quantity: '数量', description: '描述', fact: '设定内容' }
</script>
<template>
  <section class="card state-changes"><p class="eyebrow">Recent State Changes</p><h2>最近状态变化 <small v-if="log">· 第 {{ log.chapter }} 章已提交</small></h2>
    <p v-if="!log" class="empty">尚无章节提交。批准章节后，这里会展示正式状态的变化。</p><p v-else-if="!log.changes.length" class="empty">本章未改变角色、物品、地图或设定。剧情摘要已保存。</p>
    <ul v-else class="change-list"><li v-for="(change, index) in log.changes" :key="index"><span class="change-domain">{{ domainName[change.domain] }}</span><div><strong>{{ change.name }}</strong><p v-if="change.operation === 'updated'">{{ fieldName[change.field] || change.field }}：<span class="before">{{ displayValue(change.before) }}</span> → <span class="after">{{ displayValue(change.after) }}</span></p><template v-else><p>{{ change.operation === 'added' ? '新增记录' : '移除记录' }}</p><details><summary>查看变化详情</summary><pre>{{ JSON.stringify(change.after ?? change.before, null, 2) }}</pre></details></template></div></li></ul>
  </section>
</template>
