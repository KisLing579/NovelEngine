<script setup>
import { ref, watch } from 'vue'
const props = defineProps({ world: Object })
const active = ref('roles'), selectedRole = ref(null)
const tabs = [{ key: 'roles', label: 'Roles 角色' }, { key: 'inventory', label: 'Inventory 物品' }, { key: 'maps', label: 'Maps 地图' }, { key: 'lore', label: 'Lore 设定' }]
const location = (id) => props.world.maps.find(m => m.id === id)?.name || id
const owner = (id) => props.world.roles.find(r => r.id === id)?.name || id
const occupants = (id) => props.world.roles.filter(r => r.location_id === id).map(r => r.name).join('、') || '暂无角色'
watch(() => props.world, () => { selectedRole.value = null })
</script>
<template>
  <aside class="card story-state"><p class="eyebrow">Committed Story State</p><div class="section-heading"><h2>正式世界状态</h2><span class="badge approved">只读 · 第 {{ world.chapter_number }} 章</span></div><p class="muted small">仅展示已批准状态，不包含草稿中的新事件。</p>
    <div class="tabs" aria-label="状态分类"><button v-for="tab in tabs" :key="tab.key" :aria-pressed="active === tab.key" :class="{ active: active === tab.key }" @click="active = tab.key">{{ tab.label }} <span>{{ world[tab.key].length }}</span></button></div>
    <div v-if="active === 'roles'"><div v-for="role in world.roles" :key="role.id" class="entity-card"><div class="section-heading"><h3>{{ role.name }}</h3><span class="badge" :class="role.alive ? 'approved' : 'failed'">{{ role.alive ? '存活' : '死亡' }}</span></div><dl><dt>位置</dt><dd>{{ location(role.location_id) }}</dd><dt>当前状态</dt><dd>{{ role.condition }}</dd></dl><button class="text-button" @click="selectedRole = selectedRole === role.id ? null : role.id">{{ selectedRole === role.id ? '收起角色详情' : '查看角色详情' }}</button><pre v-if="selectedRole === role.id" aria-label="角色完整 JSON">{{ JSON.stringify(role, null, 2) }}</pre></div><p class="small muted">当前数据未记录角色类型与关系。</p></div>
    <div v-else-if="active === 'inventory'"><div class="table-scroll" v-if="world.inventory.length"><table><thead><tr><th>物品</th><th>持有人</th><th>数量 / 状态</th></tr></thead><tbody><tr v-for="item in world.inventory" :key="item.id"><td>{{ item.name }}<small class="entity-id">{{ item.id }}</small></td><td>{{ owner(item.owner_id) }}</td><td>{{ item.quantity }}<small class="entity-id">{{ item.quantity ? '持有' : '已耗尽 / 未持有' }}</small></td></tr></tbody></table></div><p v-else class="empty">暂无物品。</p><p class="small muted">当前数据未记录物品描述。</p></div>
    <div v-else-if="active === 'maps'"><div v-for="place in world.maps" :key="place.id" class="entity-card"><h3>{{ place.name }}</h3><p>{{ place.description || '暂无描述' }}</p><p class="small"><strong>当前角色：</strong>{{ occupants(place.id) }}</p><small class="muted">ID：{{ place.id }}</small></div><p class="small muted">地图列表为已有记录，当前未单独记录解锁状态。</p></div>
    <div v-else><div v-for="lore in world.lore" :key="lore.id" class="entity-card"><h3>{{ lore.id }}</h3><p>{{ lore.fact }}</p></div><p v-if="!world.lore.length" class="empty">暂无世界设定。</p></div>
  </aside>
</template>
