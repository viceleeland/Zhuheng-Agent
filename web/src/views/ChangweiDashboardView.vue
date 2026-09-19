<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight, RefreshCw, FolderOpen } from '@lucide/vue'
import { cw } from '@/apis/changwei_api'

const router = useRouter()
const projects = ref([])
const projectId = ref('')
const tasks = ref([])
const materials = ref([])
const loading = ref(true)
const error = ref('')
let requestId = 0
const kinds = [
  ['supervision_log', '监理日志'],
  ['management_log', '项管日志'],
  ['supervision_report', '监理月报'],
  ['management_report', '项管月报'],
  ['scheme_review', '施工方案审核']
]
const pendingModules = (task) => (task.content?.modules || []).filter((m) => !m.confirmed_by).length
const pendingTasks = computed(() => tasks.value.filter((t) => pendingModules(t) > 0).length)
const pendingCount = computed(() => tasks.value.reduce((sum, t) => sum + pendingModules(t), 0))
const generatedCount = computed(() => tasks.value.filter((t) => t.status === 'generated').length)
const confirmedMaterials = computed(() => materials.value.filter((m) => m.confirmed).length)
const attentionMaterials = computed(
  () => materials.value.filter((m) => m.parse_status !== 'ready').length
)
const breakdown = computed(() =>
  kinds.map(([kind, name]) => {
    const items = tasks.value.filter((t) => t.kind === kind)
    return {
      kind,
      name,
      total: items.length,
      pending: items.filter((t) => pendingModules(t) > 0).length,
      generated: items.filter((t) => t.status === 'generated').length
    }
  })
)
const maxCount = computed(() => Math.max(1, ...breakdown.value.map((k) => k.total)))
const recentTasks = computed(() =>
  [...tasks.value]
    .sort((a, b) => String(b.updated_at || '').localeCompare(String(a.updated_at || '')))
    .slice(0, 8)
)
const statusText = (status) =>
  ({ draft: '待填报 / 待确认', confirmed: '已确认 · 可生成', generated: '已生成成果' })[status] ||
  '处理中'
const kindText = (kind) => kinds.find(([id]) => id === kind)?.[1] || '工程任务'
const dateText = (date) =>
  date
    ? new Date(date).toLocaleString('zh-CN', {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
      })
    : '—'
const openWork = (extra = {}) =>
  router.push({
    path: '/changwei',
    query: { ...(projectId.value ? { project: projectId.value } : {}), ...extra }
  })
async function loadProject() {
  const current = ++requestId
  tasks.value = []
  materials.value = []
  error.value = ''
  if (!projectId.value) {
    loading.value = false
    return
  }
  loading.value = true
  try {
    const [taskRows, materialRows] = await Promise.all([
      cw.get(`/projects/${projectId.value}/tasks`),
      cw.get(`/projects/${projectId.value}/materials`)
    ])
    if (current !== requestId) return
    tasks.value = taskRows
    materials.value = materialRows
  } catch (e) {
    if (current === requestId) error.value = e.message || '工程数据加载失败，请重试'
  } finally {
    if (current === requestId) loading.value = false
  }
}
async function refresh() {
  const current = ++requestId
  loading.value = true
  error.value = ''
  try {
    const rows = await cw.get('/projects')
    if (current !== requestId) return
    projects.value = rows
    if (!rows.some((p) => p.id === projectId.value)) projectId.value = rows[0]?.id || ''
    await loadProject()
  } catch (e) {
    if (current === requestId) {
      error.value = e.message || '工程列表加载失败，请重试'
      loading.value = false
    }
  }
}
onMounted(refresh)
</script>

<template>
  <main class="engineering-dashboard">
    <header class="page-header">
      <div>
        <h1>工程数据总览</h1>
        <p>查看当前工程的业务进度、确认事项与资料情况</p>
      </div>
      <button class="outline-button" :disabled="loading" @click="refresh">
        <RefreshCw :size="16" />刷新
      </button>
    </header>
    <section class="project-picker" aria-label="工程选择">
      <label for="overview-project">当前工程</label>
      <select
        id="overview-project"
        v-model="projectId"
        :disabled="loading || !projects.length"
        @change="loadProject"
      >
        <option v-if="!projects.length" value="">暂无可访问工程</option>
        <option v-for="project in projects" :key="project.id" :value="project.id">
          {{ project.name }}{{ project.lot ? ` · ${project.lot}` : '' }}
        </option>
      </select>
      <button class="primary-button" @click="openWork()">
        进入业务工作台<ArrowRight :size="16" />
      </button>
    </section>
    <div v-if="error" class="state-panel error" role="alert">
      <p>{{ error }}</p>
      <button class="outline-button" @click="refresh">重新加载</button>
    </div>
    <div v-else-if="loading" class="state-panel" role="status">正在读取工程数据…</div>
    <div v-else-if="!projectId" class="state-panel">
      <FolderOpen :size="32" />
      <h2>还没有可访问的工程</h2>
      <p>在业务工作台创建工程后，这里会显示实际任务进度。</p>
      <button class="primary-button" @click="openWork()">创建工程</button>
    </div>
    <template v-else>
      <section class="stats-grid" aria-label="任务统计">
        <article>
          <span>业务任务</span><strong>{{ tasks.length }}</strong
          ><small>当前工程全部任务</small>
        </article>
        <article>
          <span>待确认任务</span><strong>{{ pendingTasks }}</strong
          ><small>包含 {{ pendingCount }} 个未确认模块</small>
        </article>
        <article>
          <span>已生成任务</span><strong>{{ generatedCount }}</strong
          ><small>当前处于已生成状态</small>
        </article>
        <article>
          <span>工程资料</span><strong>{{ materials.length }}</strong
          ><small>{{ confirmedMaterials }} 份已确认 · {{ attentionMaterials }} 份解析待处理</small>
        </article>
      </section>
      <section class="panel">
        <div class="section-header">
          <h2>五类工程智能体</h2>
          <span>按业务任务统计</span>
        </div>
        <div class="kind-grid">
          <button
            v-for="item in breakdown"
            :key="item.kind"
            class="kind-card"
            @click="openWork({ kind: item.kind })"
          >
            <div class="kind-heading">
              <h3>{{ item.name }}</h3>
              <ArrowRight :size="16" />
            </div>
            <div class="kind-total">
              <strong>{{ item.total }}</strong
              ><span>项任务</span>
            </div>
            <div class="bar-track" aria-hidden="true">
              <div :style="{ width: `${(item.total / maxCount) * 100}%` }"></div>
            </div>
            <p>
              待确认 {{ item.pending }}<span>已生成 {{ item.generated }}</span>
            </p>
          </button>
        </div>
      </section>
      <section class="panel">
        <div class="section-header">
          <h2>最近更新的任务</h2>
          <button class="text-button" @click="openWork()">查看全部<ArrowRight :size="15" /></button>
        </div>
        <div v-if="!recentTasks.length" class="empty-tasks">
          <p>这个工程还没有业务任务</p>
          <button class="outline-button" @click="openWork()">开始创建任务</button>
        </div>
        <div v-else class="task-list">
          <button
            v-for="task in recentTasks"
            :key="task.id"
            class="task-row"
            @click="openWork({ task: task.id })"
          >
            <div class="task-title">
              <strong>{{ task.title }}</strong
              ><span>{{ kindText(task.kind) }}{{ task.period ? ` · ${task.period}` : '' }}</span>
            </div>
            <span class="status" :class="task.status">{{ statusText(task.status) }}</span>
            <time :datetime="task.updated_at">{{ dateText(task.updated_at) }}</time
            ><ArrowRight :size="16" />
          </button>
        </div>
      </section>
      <p class="data-note">
        统计来自当前工程的实际任务与资料；修改已生成任务后，其状态会重新进入确认流程。
      </p>
    </template>
  </main>
</template>

<style scoped>
.engineering-dashboard {
  padding: 28px;
  max-width: 1440px;
  margin: 0 auto;
  color: var(--gray-900);
}
h1,
h2,
h3,
p {
  margin: 0;
}
h1 {
  font-size: 24px;
  font-weight: 650;
}
h2 {
  font-size: 17px;
}
h3 {
  font-size: 15px;
}
.page-header,
.section-header,
.project-picker,
.kind-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.page-header p {
  color: var(--gray-600);
  margin-top: 8px;
  font-size: 14px;
}
button,
select {
  font: inherit;
}
button {
  cursor: pointer;
}
button:disabled {
  cursor: wait;
  opacity: 0.6;
}
button:focus-visible,
select:focus-visible {
  outline: 2px solid var(--main-color);
  outline-offset: 3px;
}
.outline-button,
.primary-button,
.text-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 9px 13px;
  border-radius: 8px;
  font-size: 14px;
  border: 1px solid var(--gray-200);
  background: var(--gray-0);
  color: var(--gray-900);
  white-space: nowrap;
}
.primary-button {
  background: var(--main-color);
  color: var(--gray-0);
  border-color: var(--main-color);
}
.text-button {
  padding: 0;
  border: 0;
  color: var(--main-color);
  background: transparent;
}
.project-picker {
  margin: 24px 0;
  padding: 16px;
  border: 1px solid var(--gray-150);
  border-radius: 10px;
  background: var(--gray-0);
}
.project-picker label {
  font-size: 14px;
  white-space: nowrap;
}
select {
  min-width: 0;
  flex: 1;
  padding: 9px;
  border: 1px solid var(--gray-200);
  border-radius: 7px;
  background: var(--gray-0);
  color: var(--gray-900);
}
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}
.stats-grid article {
  display: flex;
  flex-direction: column;
  gap: 10px;
  border: 1px solid var(--gray-150);
  border-radius: 10px;
  padding: 20px;
  background: var(--gray-0);
}
.stats-grid article > span {
  font-size: 14px;
  color: var(--gray-600);
}
.stats-grid strong {
  font-size: 30px;
  font-variant-numeric: tabular-nums;
}
.stats-grid small {
  font-size: 12px;
  color: var(--gray-600);
  line-height: 1.6;
}
.panel {
  margin-top: 24px;
  padding: 20px;
  background: var(--gray-0);
  border: 1px solid var(--gray-150);
  border-radius: 10px;
}
.section-header {
  margin-bottom: 18px;
}
.section-header > span {
  font-size: 12px;
  color: var(--gray-600);
}
.kind-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
}
.kind-card {
  text-align: left;
  border: 1px solid var(--gray-150);
  background: var(--gray-25);
  color: inherit;
  border-radius: 9px;
  padding: 16px;
  min-width: 0;
}
.kind-card:hover {
  border-color: var(--main-color);
}
.kind-heading {
  gap: 6px;
}
.kind-heading svg {
  flex-shrink: 0;
  color: var(--gray-600);
}
.kind-total {
  margin: 20px 0 12px;
  display: flex;
  gap: 8px;
  align-items: baseline;
}
.kind-total strong {
  font-size: 26px;
}
.kind-total span,
.kind-card p {
  font-size: 12px;
  color: var(--gray-600);
}
.kind-card p {
  display: flex;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 12px;
}
.bar-track {
  height: 5px;
  border-radius: 3px;
  background: var(--gray-150);
  overflow: hidden;
}
.bar-track div {
  height: 100%;
  background: var(--main-color);
}
.task-row {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 16px 0;
  border: 0;
  border-bottom: 1px solid var(--gray-100);
  color: inherit;
  background: transparent;
  text-align: left;
}
.task-row:last-child {
  border-bottom: 0;
}
.task-row:hover .task-title strong {
  color: var(--main-color);
}
.task-title {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.task-title strong {
  font-size: 14px;
  overflow-wrap: anywhere;
}
.task-title span,
time {
  font-size: 12px;
  color: var(--gray-600);
}
.status {
  font-size: 12px;
  border-radius: 5px;
  padding: 5px 8px;
  background: var(--gray-100);
  white-space: nowrap;
}
.status.generated {
  background: var(--color-success-50);
  color: var(--color-success-700);
}
.status.confirmed {
  background: var(--main-50);
  color: var(--main-color);
}
.state-panel,
.empty-tasks {
  text-align: center;
  padding: 44px 16px;
  color: var(--gray-600);
}
.state-panel {
  background: var(--gray-0);
  border: 1px solid var(--gray-150);
  border-radius: 10px;
}
.state-panel h2 {
  margin: 14px 0;
}
.state-panel button,
.empty-tasks button {
  margin-top: 18px;
}
.error {
  color: var(--color-error-700);
}
.data-note {
  font-size: 12px;
  color: var(--gray-600);
  margin-top: 18px;
  line-height: 1.7;
}
@media (max-width: 1100px) {
  .kind-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
@media (max-width: 700px) {
  .engineering-dashboard {
    padding: 18px 14px;
  }
  h1 {
    font-size: 21px;
  }
  .page-header {
    align-items: flex-start;
  }
  .project-picker {
    flex-wrap: wrap;
    gap: 10px;
  }
  .project-picker select {
    flex-basis: 70%;
  }
  .project-picker .primary-button {
    width: 100%;
  }
  .stats-grid,
  .kind-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .stats-grid article {
    padding: 15px;
  }
  .panel {
    padding: 15px;
  }
  .kind-card {
    padding: 12px;
  }
  .kind-grid .kind-card:last-child {
    grid-column: 1/-1;
  }
  .task-row {
    flex-wrap: wrap;
    gap: 10px;
  }
  .task-title {
    flex-basis: calc(100% - 28px);
  }
  .task-row > svg {
    display: none;
  }
  .task-row time {
    margin-left: auto;
  }
  .section-header {
    gap: 10px;
  }
  .section-header > span {
    display: none;
  }
}
</style>
