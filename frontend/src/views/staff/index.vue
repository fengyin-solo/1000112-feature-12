<template>
  <section class="page" data-module="staff">
    <header class="page-head">
      <div>
        <h2>检测人员管理</h2>
        <p class="page-desc">维护检测员，围绕员工编号、姓名、技术职称、资质证书做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记检测员</button>
        <button class="btn" type="button" @click="exportRows">导出检测人员清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in availableActions(row)"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
            <span v-if="!availableActions(row).length">—</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无检测人员数据，可先登记检测员</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条检测人员记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/staff'
const columns = ["员工编号", "姓名", "技术职称", "资质证书", "授权项目", "在岗状态", "考核日期", "考核结果"]
// 服务端会随每行下发 available_actions；这里的映射只是接口异常时的兜底。
const STATUS_ACTIONS: Record<string, string[]> = {
  在岗: ['安排培训', '确认离岗'],
  培训中: ['恢复在岗', '退回', '确认离岗'],
  离岗: ['恢复在岗', '归档'],
}
const statuses = ["在岗", "培训中", "离岗", "停岗", "已归档"]
const stats = [{"label": "在岗人员", "value": 0}, {"label": "培训中人员", "value": 0}, {"label": "离岗人员", "value": 0}]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

function availableActions(row: Row): string[] {
  const fromServer = row.available_actions
  if (Array.isArray(fromServer)) {
    return fromServer as string[]
  }
  return STATUS_ACTIONS[String(row.status ?? '')] ?? []
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '检测员登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  let failure = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action, version: row.version ?? null } }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok) {
      throw new Error(payload?.detail ?? '检测人员动作未生效，请稍后重试')
    }
    if (payload && payload.ok === false) {
      throw new Error(payload.message ?? '检测人员动作未生效，请稍后重试')
    }
  } catch (error) {
    failure = error instanceof Error ? error.message : '检测人员操作失败'
  }
  // 无论成败都重新拉取：按钮以服务端最新状态为准，退回、恢复、归档后不残留旧按钮。
  await reload()
  errorMessage.value = failure
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('检测员列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '检测人员列表读取失败'
  }
}

onMounted(reload)
</script>
