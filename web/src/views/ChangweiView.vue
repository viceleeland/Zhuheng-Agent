<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ClipboardList,
  FileText,
  FolderOpen,
  Layers,
  Plus,
  ArrowLeft,
  Download,
  RefreshCw,
  Sparkles,
  Check,
  Upload,
  Users,
  Clock,
  Mic
} from '@lucide/vue'
import { cw } from '@/apis/changwei_api'
import { useChangweiTranscription } from '@/composables/useChangweiTranscription'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const route = useRoute()
const initialized = ref(false)
const user = useUserStore()
const section = ref('tasks')
const projects = ref([])
const projectId = ref('')
const catalog = ref({ types: {}, categories: [], models: [] })
const tasks = ref([])
const materials = ref([])
const audits = ref([])
const active = ref(null)
const artifacts = ref([])
const templateId = ref('')
const selectedModule = ref('0')
const editor = ref('')
const assignee = ref('')
const search = ref('')
const kindFilter = ref('')
const model = ref('')
const aiNote = ref('')
const weatherLocation = ref('')
const weatherNote = ref('')
const isWeatherModule = computed(() => ['天气信息', '天气与水文'].includes(module.value?.name))
const sources = ref([])
const selectedMaterials = ref([])
const error = ref('')
const busy = ref(false)
let runningOperations = 0
let projectRequest = 0
let taskRequest = 0
const modal = ref('')
const form = ref({})
const materialPreview = ref(null)
const {
  state: speechState,
  active: speechActive,
  partial: speechPartial,
  error: speechError,
  start: startSpeech,
  stop: stopSpeech,
  cancel: cancelSpeech
} = useChangweiTranscription((text, session) => {
  if (active.value?.id !== session.taskId || selectedModule.value !== session.moduleId) return
  editor.value = [editor.value, text].filter(Boolean).join('\n')
})
watch(
  () => [
    active.value?.id,
    selectedModule.value,
    projectId.value,
    router.currentRoute.value.fullPath
  ],
  () => cancelSpeech(),
  { flush: 'sync' }
)
const uid = computed(() => String(user.uid || ''))
const project = computed(() => projects.value.find((p) => p.id === projectId.value))
const isManager = computed(() => project.value?.owner_uid === uid.value)
const members = computed(() =>
  project.value ? [project.value.owner_uid, ...Object.keys(project.value.members)] : []
)
const module = computed(() =>
  active.value?.content.modules.find((m) => m.id === selectedModule.value)
)
const canEdit = computed(() => isManager.value || module.value?.assignee === uid.value)
const filtered = computed(() =>
  tasks.value.filter(
    (t) => (!kindFilter.value || t.kind === kindFilter.value) && t.title.includes(search.value)
  )
)
const confirmedCount = computed(
  () => active.value?.content.modules.filter((m) => m.confirmed_by).length || 0
)
const statusText = {
  draft: '待填报 / 待确认',
  confirmed: '已确认 · 可生成',
  generated: '已生成成果',
  ready: '可读取',
  needs_attention: '需补录 / OCR',
  unsupported: '格式待转换'
}

async function run(fn) {
  const path = route.fullPath
  runningOperations += 1
  busy.value = true
  error.value = ''
  try {
    await fn()
  } catch (e) {
    if (route.fullPath === path) error.value = e.message || '操作失败，请重试'
  } finally {
    runningOperations -= 1
    busy.value = runningOperations > 0
  }
}
function captureEditorContext() {
  const path = route.fullPath
  const project = projectId.value
  const task = active.value?.id
  const selected = selectedModule.value
  return () =>
    route.fullPath === path &&
    projectId.value === project &&
    active.value?.id === task &&
    selectedModule.value === selected
}
async function refreshProject() {
  const request = ++projectRequest
  if (!projectId.value) return
  const requestedProject = projectId.value
  tasks.value = []
  materials.value = []
  audits.value = []
  const [t, m, a] = await Promise.all([
    cw.get(`/projects/${projectId.value}/tasks`),
    cw.get(`/projects/${projectId.value}/materials`),
    cw.get(`/projects/${projectId.value}/audit`)
  ])
  if (projectId.value !== requestedProject || request !== projectRequest) return
  tasks.value = t
  materials.value = m
  audits.value = a
}
async function boot() {
  catalog.value = await cw.get('/catalog')
  model.value = catalog.value.models[0]?.spec || ''
  projects.value = await cw.get('/projects')
  projectId.value = projects.value.some((p) => p.id === route.query.project)
    ? route.query.project
    : projects.value[0]?.id || ''
  await refreshProject()
  initialized.value = true
  await applyRouteSelection()
}
async function applyRouteSelection() {
  if (!initialized.value || route.path !== '/changwei') return
  const requestedPath = route.fullPath
  const requestedProject = route.query.project
  if (requestedProject && !projects.value.some((p) => p.id === requestedProject)) {
    throw new Error('此工程不存在或你没有访问权限')
  }
  if (requestedProject && requestedProject !== projectId.value) {
    projectId.value = requestedProject
    active.value = null
    await refreshProject()
  }
  if (route.fullPath !== requestedPath) return
  section.value = ['materials', 'platform', 'audit'].includes(route.query.view)
    ? route.query.view
    : 'tasks'
  kindFilter.value = Object.hasOwn(catalog.value.types, route.query.kind || '')
    ? route.query.kind
    : ''
  active.value = null
  if (route.query.task) {
    if (!tasks.value.some((t) => t.id === route.query.task)) {
      throw new Error('当前工程中找不到此任务，请返回工程总览刷新')
    }
    await openTask(route.query.task)
  }
}
watch(
  () => route.fullPath,
  () => {
    if (initialized.value && route.path === '/changwei') run(applyRouteSelection)
  }
)
function changeProject() {
  templateId.value = ''
  active.value = null
  run(refreshProject)
}
function openMembers() {
  form.value = { uid: '' }
  modal.value = 'member'
}
function startProject() {
  form.value = { name: '安徽新安江流域防洪治理工程', lot: '歙县段三标段' }
  modal.value = 'project'
}
function startTask(kind = 'supervision_log') {
  form.value = {
    kind,
    title: catalog.value.types[kind].name,
    period: new Date().toLocaleDateString('sv-SE')
  }
  modal.value = 'task'
}
async function submit() {
  await run(async () => {
    if (modal.value === 'project') {
      const p = await cw.post('/projects', form.value)
      projects.value.unshift(p)
      projectId.value = p.id
      active.value = null
      await refreshProject()
    } else if (modal.value === 'member') {
      const p = await cw.post(`/projects/${projectId.value}/members`, form.value)
      projects.value = projects.value.map((x) => (x.id === p.id ? p : x))
    } else {
      const t = await cw.post(`/projects/${projectId.value}/tasks`, form.value)
      await openTask(t.id)
      await refreshProject()
    }
    modal.value = ''
  })
}
function pickModule(id) {
  selectedModule.value = id
  editor.value = module.value?.text || ''
  assignee.value = module.value?.assignee || ''
  sources.value = module.value?.sources || []
  aiNote.value = ''
  weatherNote.value = ''
}
async function openTask(id) {
  const request = ++taskRequest
  templateId.value = ''
  const requestedProject = projectId.value
  const requestedPath = route.fullPath
  const data = await cw.get(`/tasks/${id}`)
  if (
    projectId.value !== requestedProject ||
    route.fullPath !== requestedPath ||
    request !== taskRequest
  )
    return
  if (data.task.project_id !== requestedProject) throw new Error('任务不属于当前工程，请刷新后重试')
  active.value = data.task
  artifacts.value = data.artifacts
  section.value = 'tasks'
  selectedMaterials.value = [...(active.value.content.material_ids || [])]
  pickModule('0')
}
async function save(confirm) {
  const stillCurrent = captureEditorContext()
  await run(async () => {
    const updated = await cw.put(`/tasks/${active.value.id}/modules/${module.value.id}`, {
      revision: active.value.revision,
      text: editor.value,
      confirm,
      ...(isManager.value ? { assignee: assignee.value } : {})
    })
    if (!stillCurrent()) return
    active.value = updated
    pickModule(selectedModule.value)
    await refreshProject()
  })
}
async function draft() {
  const taskId = active.value.id
  const moduleId = module.value.id
  const stillCurrent = captureEditorContext()
  await run(async () => {
    // 先保存当前口述记录，避免模型读取上次保存的旧正文。
    const saved = await cw.put(`/tasks/${taskId}/modules/${moduleId}`, {
      revision: active.value.revision,
      text: editor.value,
      confirm: false
    })
    if (!stillCurrent()) return
    active.value = saved
    const result = await cw.post(`/tasks/${taskId}/modules/${moduleId}/draft`, {
      model_spec: model.value
    })
    if (!stillCurrent()) return
    active.value = result.task
    editor.value = result.text
    sources.value = result.sources
    aiNote.value = result.notice
  })
}
async function fetchWeather() {
  const taskId = active.value.id
  const moduleId = selectedModule.value
  const stillCurrent = captureEditorContext()
  await run(async () => {
    const result = await cw.post(`/tasks/${taskId}/weather`, { location: weatherLocation.value })
    if (!stillCurrent() || selectedModule.value !== moduleId) return
    editor.value = [editor.value, result.text].filter(Boolean).join('\n\n')
    weatherNote.value = '已追加实况，尚未保存。' + result.warning
  })
}
async function generate() {
  const stillCurrent = captureEditorContext()
  const taskId = active.value.id
  await run(async () => {
    await cw.post(`/tasks/${taskId}/generate`, {
      revision: active.value.revision,
      template_id: templateId.value || null
    })
    const data = await cw.get(`/tasks/${taskId}`)
    if (!stillCurrent()) return
    active.value = data.task
    artifacts.value = data.artifacts
    await refreshProject()
  })
}
async function upload(event) {
  const files = Array.from(event.target.files || [])
  const requestedProject = projectId.value
  await run(async () => {
    for (const file of files) await cw.upload(requestedProject, file)
    if (requestedProject === projectId.value) await refreshProject()
  })
  event.target.value = ''
}
async function saveMaterials() {
  const stillCurrent = captureEditorContext()
  await run(async () => {
    const updated = await cw.put(`/tasks/${active.value.id}/materials`, {
      revision: active.value.revision,
      material_ids: [...selectedMaterials.value]
    })
    if (stillCurrent()) active.value = updated
  })
}
async function confirmMaterial(item) {
  await run(async () => {
    await cw.put(`/materials/${item.id}`, { category: item.category })
    await refreshProject()
  })
}
function dictation() {
  if (speechActive.value) {
    stopSpeech()
    return
  }
  startSpeech({ taskId: active.value.id, moduleId: selectedModule.value, token: user.token })
}

function navigate(s) {
  if (busy.value) return
  section.value = s
  active.value = null
  error.value = ''
  router.replace({
    path: '/changwei',
    query: { project: projectId.value || undefined, view: s === 'tasks' ? undefined : s }
  })
}
onMounted(() => run(boot))
</script>

<template>
  <main class="cw-page">
    <header class="cw-header">
      <div class="cw-brand">
        <span class="cw-brand-icon"><Layers :size="23" /></span>
        <div>
          <h1>江擎 · 工程工作台</h1>
          <p>水利工程智能协作</p>
        </div>
      </div>
      <div class="cw-header-actions">
        <select v-model="projectId" aria-label="选择工程" :disabled="busy" @change="changeProject">
          <option value="" disabled>请选择工程</option>
          <option v-for="p in projects" :key="p.id" :value="p.id">
            {{ p.name }} / {{ p.lot }}
          </option></select
        ><button :disabled="busy" @click="startProject"><Plus :size="16" /> 新建工程</button>
      </div>
    </header>
    <nav class="cw-nav" aria-label="业务导航">
      <button :class="{ selected: section === 'tasks' }" @click="navigate('tasks')">
        <ClipboardList :size="18" />业务工作台
      </button>
      <button :class="{ selected: section === 'materials' }" @click="navigate('materials')">
        <FolderOpen :size="18" />资料中心
      </button>
      <button :class="{ selected: section === 'platform' }" @click="navigate('platform')">
        <Layers :size="18" />AI 中台
      </button>
      <button :class="{ selected: section === 'audit' }" @click="navigate('audit')">
        <Clock :size="18" />操作记录
      </button>
      <button v-if="project && isManager" class="cw-member" @click="openMembers">
        <Users :size="16" />工程成员 · {{ members.length }}
      </button>
    </nav>
    <div v-if="error" class="cw-alert error" role="alert">
      {{ error }} <button @click="error = ''">关闭</button>
    </div>
    <div v-if="busy" class="cw-progress" role="status">正在处理，请稍候…</div>

    <section v-if="section === 'platform'" class="cw-content">
      <div class="cw-section-heading">
        <div>
          <h2>AI 能力中台</h2>
          <p>管理工程应用使用的模型、知识资料和扩展服务。</p>
        </div>
        <span class="cw-tag">工程 AI 服务</span>
      </div>
      <div class="cw-capabilities">
        <article
          v-for="c in [
            {
              title: '模型服务',
              desc: '对话模型、Embedding 与重排模型统一维护。',
              route: '/agent-manage?tab=providers'
            },
            {
              title: '知识库与规范资料',
              desc: '文档入库、解析、检索以及规范与项目依据管理。',
              route: '/extensions'
            },
            {
              title: '工程应用',
              desc: '监理与项管日志、月报编制和施工方案审核。',
              route: '/changwei'
            },
            {
              title: '辅助问答',
              desc: '围绕工程资料提问、整理内容和查询知识库。',
              route: '/agent'
            },
            {
              title: '工程总览',
              desc: '查看五类应用的任务进度、待确认项和成果数量。',
              route: '/dashboard'
            },
            {
              title: '个人文件空间',
              desc: '通用智能体处理的文件、预览与下载。',
              route: '/workspace'
            }
          ]"
          :key="c.title"
        >
          <Layers :size="22" />
          <h3>{{ c.title }}</h3>
          <p>{{ c.desc }}</p>
          <button @click="router.push(c.route)">进入管理 →</button>
        </article>
      </div>
      <div class="cw-panel">
        <h3>业务 AI 模型</h3>
        <p>
          当前可用对话模型：{{ catalog.models.length }}
          个。工程草稿使用这里选择的模型，原始资料会发送至该模型供应商。
        </p>
        <select v-model="model" aria-label="业务模型">
          <option value="" disabled>请先在中台配置模型</option>
          <option v-for="m in catalog.models" :key="m.spec" :value="m.spec">{{ m.spec }}</option>
        </select>
        <p class="cw-muted">
          业务资料采用可追溯的文本片段选择；完整知识库向量检索可在 Yuxi
          通用智能体内使用。OCR、第三方报送和专用语音服务需单独配置。
        </p>
      </div>
    </section>

    <section v-else-if="!project" class="cw-empty">
      <FolderOpen :size="44" />
      <h2>建立第一个工程工作空间</h2>
      <p>统一管理标段资料、五类业务任务、模块确认和成果版本。</p>
      <button class="primary" @click="startProject">新建工程</button>
    </section>

    <section v-else-if="section === 'materials'" class="cw-content">
      <div class="cw-section-heading">
        <div>
          <h2>项目资料中心</h2>
          <p>上传 → 检查提取内容 → 确认分类 → 用于业务草稿</p>
        </div>
        <label class="cw-upload" :class="{ disabled: busy }"
          ><Upload :size="16" />上传资料<input
            type="file"
            multiple
            :disabled="busy"
            accept=".docx,.xlsx,.pdf,.txt,.md,.csv,.zip"
            @change="upload"
        /></label>
      </div>
      <p class="cw-muted">
        支持 DOCX、XLSX、PDF、文本及 ZIP，单文件最多 30 MB。扫描 PDF 会标记待
        OCR，金额和公式需人工核对。
      </p>
      <div v-if="!materials.length" class="cw-empty">
        <FolderOpen :size="36" />
        <h3>还没有资料</h3>
        <p>可以先上传一份日志样本、施工方案或月报台账。</p>
      </div>
      <div v-else class="cw-table-wrap">
        <table>
          <thead>
            <tr>
              <th>文件名称</th>
              <th>资料类别</th>
              <th>读取状态</th>
              <th>人工确认</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="m in materials" :key="m.id">
              <td><FileText :size="15" /> {{ m.filename }}</td>
              <td>
                <select v-model="m.category" :disabled="busy">
                  <option v-for="c in catalog.categories" :key="c">{{ c }}</option>
                </select>
              </td>
              <td>
                <span class="cw-tag" :class="{ warning: m.parse_status !== 'ready' }">{{
                  statusText[m.parse_status]
                }}</span>
              </td>
              <td>{{ m.confirmed ? '已确认' : '待确认' }}</td>
              <td class="cw-row-actions">
                <button @click="materialPreview = m">查看内容</button
                ><button
                  v-if="m.content.warnings.some((w) => w.includes('需要 OCR'))"
                  :disabled="busy"
                  @click="
                    run(async () => {
                      await cw.post(`/materials/${m.id}/ocr`, {})
                      await refreshProject()
                    })
                  "
                >
                  OCR 下 5 页</button
                ><button :disabled="busy" @click="confirmMaterial(m)">确认分类</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section v-else-if="section === 'audit'" class="cw-content">
      <div class="cw-section-heading">
        <div>
          <h2>工程操作记录</h2>
          <p>上传、填写、确认、生成与下载均保留操作人和时间。</p>
        </div>
        <button @click="run(refreshProject)"><RefreshCw :size="16" />刷新</button>
      </div>
      <div class="cw-table-wrap">
        <table>
          <thead>
            <tr>
              <th>操作</th>
              <th>操作账号</th>
              <th>时间</th>
              <th>对象</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="a in audits" :key="a.id">
              <td>{{ a.action }}</td>
              <td>{{ a.uid }}</td>
              <td>{{ a.created_at?.replace('T', ' ').slice(0, 19) }}</td>
              <td>
                {{
                  a.detail.module ||
                  (a.detail.revision && `版本 ${a.detail.revision}`) ||
                  '工程资料'
                }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section v-else-if="active" class="cw-content">
      <div class="cw-section-heading">
        <div>
          <button class="cw-back" :disabled="busy" @click="active = null">
            <ArrowLeft :size="16" />返回任务列表
          </button>
          <h2>{{ active.title }}</h2>
          <p>
            {{ catalog.types[active.kind]?.name }} · {{ active.period }} · 已确认
            {{ confirmedCount }}/{{ active.content.modules.length }} · 版本 {{ active.revision }}
          </p>
        </div>
        <button
          class="primary"
          :disabled="busy || !isManager || confirmedCount !== active.content.modules.length"
          @click="generate"
        >
          <FileText :size="17" />生成 Word 成果
        </button>
      </div>
      <div class="cw-steps">
        <span class="done">1 基础信息</span><span class="done">2 资料与填报</span
        ><span :class="{ done: confirmedCount > 0 }">3 人工确认</span
        ><span :class="{ done: artifacts.length }">4 成果归档</span>
      </div>
      <details class="cw-panel cw-task-sources">
        <summary>本次任务资料范围（{{ active.content.material_ids?.length || 0 }} 份）</summary>
        <p class="cw-muted">仅勾选本报告期或本次审查适用的资料。调整来源后各模块需要重新确认。</p>
        <label v-for="m in materials" :key="m.id" class="cw-material-option"
          ><input v-model="selectedMaterials" type="checkbox" :value="m.id" :disabled="busy" />{{
            m.filename
          }}
          · {{ m.confirmed ? '分类已确认' : '分类待确认' }} ·
          {{ statusText[m.parse_status] }}</label
        >
        <p v-if="!materials.length">请先到资料中心上传文件。</p>
        <button :disabled="busy" @click="saveMaterials">保存资料范围</button>
      </details>
      <div class="cw-editor-layout">
        <aside class="cw-modules">
          <button
            v-for="m in active.content.modules"
            :key="m.id"
            :class="{ selected: selectedModule === m.id }"
            :disabled="busy"
            @click="pickModule(m.id)"
          >
            <span>{{ m.name }}</span
            ><Check v-if="m.confirmed_by" :size="17" /><span v-else class="cw-dot" />
          </button>
        </aside>
        <article class="cw-panel cw-editor">
          <div class="cw-section-heading">
            <h3>{{ module?.name }}</h3>
            <span class="cw-tag">{{ module?.confirmed_by ? '已确认' : '待填写 / 待确认' }}</span>
          </div>
          <div class="cw-editor-meta">
            <label
              >负责账号
              <select v-model="assignee" :disabled="busy || !isManager">
                <option v-for="m in members" :key="m">{{ m }}</option>
              </select></label
            ><button class="cw-desktop-voice" :disabled="!canEdit || busy" @click="dictation">
              <Mic :size="15" />{{
                speechState === 'finishing'
                  ? '正在收尾…'
                  : speechActive
                    ? '停止录音'
                    : '实时语音输入'
              }}
            </button>
          </div>
          <div v-if="speechActive || speechError" class="cw-alert" role="status" aria-live="polite">
            <p v-if="speechActive">
              {{
                speechState === 'connecting'
                  ? '正在连接语音服务并启用麦克风…'
                  : speechState === 'finishing'
                    ? '麦克风已关闭，等待最后一句…'
                    : '正在聆听，识别文字会自动追加；最多录制 5 分钟。'
              }}
            </p>
            <p v-if="speechPartial">正在识别：{{ speechPartial }}</p>
            <p v-if="speechError">{{ speechError }}</p>
            <p>语音文字尚未保存，请核对后保存或确认。</p>
          </div>
          <p class="cw-muted">
            按现场事实填写。无事项请填写“无”，编辑后需重新确认。切换模块前请先保存。
          </p>
          <div v-if="isWeatherModule" class="cw-weather-controls">
            <label
              >天气查询位置
              <input
                v-model="weatherLocation"
                :disabled="busy || !canEdit"
                aria-label="天气查询位置"
                placeholder="城市 ID 或经度,纬度，例如 118.42,29.87"
              />
            </label>
            <button :disabled="busy || !canEdit || !weatherLocation.trim()" @click="fetchWeather">
              获取当前天气
            </button>
            <p class="cw-muted">
              仅用于北京时间当天日志。请填写工程实际位置；实况仅代表观测时点，不代表全天。
            </p>
            <p v-if="weatherNote" class="cw-alert" role="status">{{ weatherNote }}</p>
          </div>
          <textarea
            v-model="editor"
            :disabled="busy || !canEdit"
            :aria-label="module?.name"
            placeholder="填写记录，或先输入口述文字，再让 AI 整理。"
            rows="13"
          />
          <div class="cw-ai-controls">
            <select v-model="model" aria-label="选择 AI 模型">
              <option value="">请选择模型</option>
              <option v-for="m in catalog.models" :key="m.spec" :value="m.spec">
                {{ m.spec }}
              </option></select
            ><button :disabled="busy || speechActive || !model || !canEdit" @click="draft">
              <Sparkles :size="16" />AI 辅助整理
            </button>
          </div>
          <div v-if="aiNote" class="cw-alert">{{ aiNote }}</div>
          <details v-if="sources.length">
            <summary>本次参考资料（{{ sources.length }}）</summary>
            <ul>
              <li v-for="s in sources" :key="s">{{ s }}</li>
            </ul>
          </details>
          <div class="cw-editor-actions cw-save-actions">
            <button
              class="cw-mobile-voice"
              :class="{ recording: speechActive }"
              :disabled="busy || !canEdit"
              @click="dictation"
            >
              <Mic :size="18" />{{ speechActive ? '停止' : '实时语音' }}
            </button>
            <button :disabled="busy || speechActive || !canEdit" @click="save(false)">
              保存草稿</button
            ><button
              class="primary"
              :disabled="busy || speechActive || !canEdit || !editor.trim()"
              @click="save(true)"
            >
              <Check :size="16" />确认本模块
            </button>
          </div>
        </article>
      </div>
      <div class="cw-panel cw-artifacts">
        <h3>成果版本</h3>
        <label v-if="active.kind === 'supervision_log'"
          >导出模板
          <select v-model="templateId" :disabled="busy">
            <option value="">基础版式</option>
            <option
              v-for="m in materials.filter((x) => x.filename.toLowerCase().endsWith('.docx'))"
              :key="m.id"
              :value="m.id"
            >
              {{ m.filename }}
            </option>
          </select></label
        >
        <p v-if="!artifacts.length" class="cw-muted">
          全部模块确认后，由工程负责人生成。监理日志可选择已上传的原版表格；其他业务当前采用基础版式。
        </p>
        <div v-for="a in artifacts" :key="a.id" class="cw-artifact">
          <FileText :size="20" /><span
            >{{ a.filename }}
            <small>{{ a.created_at?.slice(0, 19).replace('T', ' ') }}</small></span
          ><button :disabled="busy" @click="run(() => cw.download(a))">
            <Download :size="16" />下载
          </button>
        </div>
      </div>
    </section>

    <section v-else class="cw-content">
      <div class="cw-section-heading">
        <div>
          <h2>工程业务工作台</h2>
          <p>让现场记录、项目资料与审查依据进入同一条可追溯的工作流程。</p>
        </div>
        <button class="primary" :disabled="busy" @click="startTask()">
          <Plus :size="18" />新建任务
        </button>
      </div>
      <div class="cw-apps">
        <button
          v-for="(t, key) in catalog.types"
          :key="key"
          :disabled="busy"
          @click="startTask(key)"
        >
          <span class="cw-app-icon"><FileText :size="23" /></span><strong>{{ t.name }}</strong
          ><span>{{
            key.includes('log')
              ? '现场填报 · 分模块确认'
              : key.includes('report')
                ? '资料归集 · 月度成果'
                : '依据核对 · 意见复核'
          }}</span
          ><span class="cw-app-arrow">↗</span>
        </button>
      </div>
      <div class="cw-stats">
        <div>
          <span>全部任务</span><strong>{{ tasks.length }}</strong>
        </div>
        <div>
          <span>待填报与确认</span
          ><strong>{{ tasks.filter((t) => t.status === 'draft').length }}</strong>
        </div>
        <div>
          <span>已生成成果的任务</span
          ><strong>{{ tasks.filter((t) => t.status === 'generated').length }}</strong>
        </div>
        <div>
          <span>已上传资料</span><strong>{{ materials.length }}</strong>
        </div>
      </div>
      <div class="cw-toolbar">
        <input v-model="search" aria-label="搜索任务" placeholder="搜索任务名称…" /><select
          v-model="kindFilter"
          aria-label="筛选业务"
        >
          <option value="">全部业务类型</option>
          <option v-for="(t, key) in catalog.types" :key="key" :value="key">
            {{ t.name }}
          </option></select
        ><button :disabled="busy" @click="run(refreshProject)"><RefreshCw :size="16" />刷新</button>
      </div>
      <div v-if="!filtered.length" class="cw-empty">
        <ClipboardList :size="38" />
        <h3>{{ tasks.length ? '没有匹配的任务' : '从一份真实记录开始' }}</h3>
        <p>
          {{ tasks.length ? '请调整搜索条件。' : '选择上方业务应用，创建任务并填写或上传资料。' }}
        </p>
      </div>
      <div v-else class="cw-table-wrap cw-task-table">
        <table>
          <thead>
            <tr>
              <th>任务名称</th>
              <th>业务类型</th>
              <th>日期 / 报告期</th>
              <th>进度</th>
              <th>状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="t in filtered" :key="t.id">
              <td class="cw-task-name">{{ t.title }}</td>
              <td data-label="业务">{{ catalog.types[t.kind]?.name }}</td>
              <td data-label="日期 / 报告期">{{ t.period }}</td>
              <td data-label="确认进度">
                {{ t.content.modules.filter((m) => m.confirmed_by).length }}/{{
                  t.content.modules.length
                }}
                已确认
              </td>
              <td data-label="状态">
                <span class="cw-tag" :class="{ success: t.status === 'generated' }">{{
                  statusText[t.status]
                }}</span>
              </td>
              <td>
                <button :disabled="busy" @click="run(() => openTask(t.id))">打开任务 →</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <div v-if="modal" class="cw-overlay" @click.self="modal = ''">
      <form class="cw-dialog" @submit.prevent="submit">
        <h2>
          {{
            modal === 'project' ? '新建工程' : modal === 'member' ? '添加工程成员' : '新建业务任务'
          }}
        </h2>
        <template v-if="modal === 'project'"
          ><label>工程名称<input v-model="form.name" required maxlength="255" /></label
          ><label>标段<input v-model="form.lot" required maxlength="100" /></label></template
        ><template v-else-if="modal === 'member'"
          ><p>输入 Yuxi 已有账号的 UID。添加后可查看工程资料，并由负责人分派填报模块。</p>
          <label>用户 UID<input v-model="form.uid" required /></label></template
        ><template v-else
          ><label
            >业务类型<select v-model="form.kind">
              <option v-for="(t, key) in catalog.types" :key="key" :value="key">
                {{ t.name }}
              </option>
            </select></label
          ><label>任务名称<input v-model="form.title" required maxlength="255" /></label
          ><label
            >日期或报告期间<input
              v-model="form.period"
              required
              maxlength="40"
              placeholder="如 2026-04-26 至 2026-05-25" /></label
        ></template>
        <p v-if="error" class="cw-alert error">{{ error }}</p>
        <div class="cw-editor-actions">
          <button type="button" @click="modal = ''">取消</button
          ><button type="submit" class="primary" :disabled="busy">
            {{ busy ? '处理中…' : '确认创建' }}
          </button>
        </div>
      </form>
    </div>
    <div v-if="materialPreview" class="cw-overlay" @click.self="materialPreview = null">
      <div class="cw-dialog cw-preview">
        <div class="cw-section-heading">
          <h2>{{ materialPreview.filename }}</h2>
          <button @click="materialPreview = null">关闭</button>
        </div>
        <p v-for="w in materialPreview.content.warnings" :key="w" class="cw-alert">{{ w }}</p>
        <div v-for="(s, i) in materialPreview.content.segments" :key="i" class="cw-source">
          <strong>{{ s.location }}</strong>
          <pre>{{ s.text }}</pre>
        </div>
        <p v-if="!materialPreview.content.segments.length">尚未提取到可读取内容。</p>
      </div>
    </div>
  </main>
</template>

<style scoped>
.cw-mobile-voice {
  display: none;
}
.cw-weather-controls {
  margin: 12px 0;
}
.cw-weather-controls input {
  min-width: 250px;
  margin: 0 8px;
}

.cw-page {
  height: 100%;
  overflow: auto;
  background: var(--gray-25);
  color: var(--color-text);
  font-size: 14px;
}
.cw-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 26px 32px;
  background: var(--gray-0);
  border-bottom: 1px solid var(--gray-150);
}
.cw-brand {
  display: flex;
  gap: 14px;
  align-items: center;
}
.cw-brand-icon,
.cw-app-icon {
  display: grid;
  place-items: center;
  background: var(--main-50);
  color: var(--main-color);
  border-radius: 12px;
  width: 48px;
  height: 48px;
}
.cw-brand h1 {
  font-size: 21px;
  letter-spacing: 0.3px;
  margin: 0;
}
.cw-brand p {
  margin: 5px 0 0;
  color: var(--gray-500);
  font-size: 12px;
}
.cw-header-actions {
  display: flex;
  gap: 10px;
}
.cw-header-actions select {
  max-width: 290px;
}
.cw-nav {
  display: flex;
  gap: 12px;
  padding: 0 32px;
  border-bottom: 1px solid var(--gray-150);
  background: var(--gray-0);
}
button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border: 1px solid var(--gray-200);
  background: var(--gray-0);
  color: var(--color-text);
  padding: 9px 14px;
  border-radius: 7px;
  cursor: pointer;
  font: inherit;
  white-space: nowrap;
}
button:hover {
  border-color: var(--main-color);
  color: var(--main-color);
}
button:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.primary,
.cw-upload {
  background: var(--main-color);
  color: var(--gray-0);
  border-color: var(--main-color);
}
.primary:hover {
  color: var(--gray-0);
  filter: brightness(0.95);
}
.cw-nav button {
  border: 0;
  border-bottom: 3px solid transparent;
  border-radius: 0;
  padding: 17px 12px;
  background: transparent;
}
.cw-nav button.selected {
  color: var(--main-color);
  border-bottom-color: var(--main-color);
}
.cw-member {
  margin-left: auto;
}
.cw-content {
  padding: 30px 32px;
  max-width: 1600px;
  margin: auto;
}
.cw-section-heading {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
  margin-bottom: 24px;
}
h2 {
  font-size: 23px;
  margin: 0 0 8px;
}
h3 {
  font-size: 16px;
  margin: 0 0 12px;
}
.cw-section-heading p,
.cw-muted {
  color: var(--gray-500);
  line-height: 1.7;
  margin: 4px 0;
}
.cw-apps {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 14px;
}
.cw-apps > button {
  position: relative;
  align-items: flex-start;
  flex-direction: column;
  gap: 13px;
  padding: 20px;
  text-align: left;
  white-space: normal;
}
.cw-apps strong {
  font-size: 16px;
}
.cw-apps button > span:not(.cw-app-icon):not(.cw-app-arrow) {
  color: var(--gray-500);
  font-size: 12px;
}
.cw-app-arrow {
  position: absolute;
  right: 16px;
  top: 19px;
  color: var(--gray-400);
}
.cw-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  padding: 24px 0;
  gap: 16px;
}
.cw-stats > div {
  background: var(--gray-0);
  border: 1px solid var(--gray-150);
  border-radius: 8px;
  padding: 17px 22px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.cw-stats span {
  color: var(--gray-500);
}
.cw-stats strong {
  font-size: 28px;
  font-weight: 600;
}
.cw-toolbar {
  display: flex;
  gap: 12px;
  margin: 3px 0 18px;
}
.cw-toolbar input {
  flex: 1;
}
input,
select,
textarea {
  padding: 10px 12px;
  border: 1px solid var(--gray-200);
  border-radius: 6px;
  background: var(--gray-0);
  color: var(--color-text);
  font: inherit;
  min-width: 0;
}
input:focus,
textarea:focus,
select:focus {
  outline: 2px solid var(--main-100);
  border-color: var(--main-color);
}
.cw-table-wrap {
  overflow: auto;
  border: 1px solid var(--gray-150);
  border-radius: 9px;
  background: var(--gray-0);
}
table {
  border-collapse: collapse;
  width: 100%;
  text-align: left;
}
th {
  background: var(--gray-50);
  color: var(--gray-600);
  font-size: 12px;
  font-weight: 600;
  padding: 15px 18px;
  white-space: nowrap;
}
td {
  padding: 18px;
  border-top: 1px solid var(--gray-100);
  vertical-align: middle;
}
td svg {
  vertical-align: middle;
}
.cw-task-name {
  font-weight: 600;
}
.cw-tag {
  display: inline-block;
  padding: 5px 9px;
  border-radius: 5px;
  font-size: 12px;
  background: var(--main-50);
  color: var(--main-color);
  white-space: nowrap;
}
.cw-tag.success {
  background: var(--color-success-50);
  color: var(--color-success-700);
}
.cw-tag.warning {
  background: var(--color-warning-50);
  color: var(--color-warning-700);
}
.cw-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 14px;
  padding: 70px 24px;
  background: var(--gray-0);
  border: 1px dashed var(--gray-200);
  border-radius: 10px;
  color: var(--gray-500);
}
.cw-empty h2,
.cw-empty h3 {
  color: var(--color-text);
  margin: 0;
}
.cw-empty p {
  margin: 0;
  line-height: 1.8;
}
.cw-alert {
  padding: 13px 18px;
  border: 1px solid var(--color-warning-200);
  background: var(--color-warning-50);
  color: var(--color-warning-700);
  border-radius: 7px;
  line-height: 1.7;
  margin: 12px 0;
}
.cw-alert.error {
  background: var(--color-error-50);
  color: var(--color-error-700);
  border-color: var(--color-error-200);
}
.cw-page > .cw-alert {
  margin: 14px 32px;
}
.cw-progress {
  height: 28px;
  text-align: center;
  padding: 5px;
  background: var(--main-50);
  color: var(--main-color);
  font-size: 12px;
}
.cw-panel {
  border: 1px solid var(--gray-150);
  border-radius: 9px;
  background: var(--gray-0);
  padding: 24px;
}
.cw-capabilities {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 18px;
  margin-bottom: 24px;
}
.cw-capabilities article {
  background: var(--gray-0);
  border: 1px solid var(--gray-150);
  border-radius: 9px;
  padding: 24px;
}
.cw-capabilities article > svg {
  color: var(--main-color);
  margin-bottom: 20px;
}
.cw-capabilities p {
  color: var(--gray-500);
  line-height: 1.8;
  min-height: 50px;
}
.cw-steps {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  margin-bottom: 22px;
}
.cw-steps span {
  padding: 13px;
  text-align: center;
  background: var(--gray-100);
  color: var(--gray-500);
  border-radius: 5px;
}
.cw-steps span.done {
  background: var(--main-50);
  color: var(--main-color);
}
.cw-editor-layout {
  display: grid;
  grid-template-columns: 220px 1fr;
  gap: 20px;
}
.cw-modules {
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.cw-modules button {
  justify-content: space-between;
  text-align: left;
  white-space: normal;
  padding: 15px;
}
.cw-modules button.selected {
  background: var(--main-50);
  border-color: var(--main-color);
  color: var(--main-color);
}
.cw-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--gray-300);
  flex-shrink: 0;
}
.cw-editor textarea {
  width: 100%;
  resize: vertical;
  line-height: 1.9;
  margin: 12px 0;
  box-sizing: border-box;
}
.cw-editor-meta,
.cw-ai-controls,
.cw-editor-actions {
  display: flex;
  gap: 12px;
  justify-content: space-between;
  align-items: center;
}
.cw-editor-actions {
  justify-content: flex-end;
  margin-top: 22px;
}
.cw-ai-controls select {
  max-width: 60%;
}
.cw-artifacts {
  margin-top: 24px;
}
.cw-task-sources {
  margin-bottom: 20px;
}
.cw-material-option {
  display: flex;
  gap: 8px;
  align-items: center;
  margin: 12px 0;
}
.cw-artifact {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 15px 0;
  border-top: 1px solid var(--gray-100);
}
.cw-artifact button {
  margin-left: auto;
}
.cw-artifact small {
  display: block;
  color: var(--gray-500);
  margin-top: 5px;
}
.cw-back {
  border: 0;
  padding: 0;
  margin-bottom: 14px;
  color: var(--gray-500);
  background: transparent;
}
.cw-upload {
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 11px 18px;
  border-radius: 7px;
}
.cw-upload.disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.cw-upload input {
  display: none;
}
.cw-row-actions {
  display: flex;
  gap: 7px;
}
.cw-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: rgb(0 0 0 / 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}
.cw-dialog {
  background: var(--gray-0);
  border: 1px solid var(--gray-200);
  border-radius: 12px;
  padding: 30px;
  width: 480px;
  max-height: 85vh;
  overflow: auto;
}
.cw-dialog label {
  display: flex;
  flex-direction: column;
  gap: 9px;
  margin-top: 20px;
}
.cw-dialog h2 {
  font-size: 21px;
}
.cw-preview {
  width: 900px;
}
.cw-source {
  padding: 18px 0;
  border-top: 1px solid var(--gray-150);
}
.cw-source strong {
  color: var(--main-color);
}
pre {
  white-space: pre-wrap;
  word-break: break-word;
  font: inherit;
  line-height: 1.8;
}
details {
  margin-top: 15px;
  color: var(--gray-500);
}
li {
  line-height: 1.9;
}
summary {
  cursor: pointer;
}
@media (max-width: 1100px) {
  .cw-apps {
    grid-template-columns: repeat(3, 1fr);
  }
  .cw-header {
    align-items: flex-start;
    flex-direction: column;
  }
  .cw-capabilities {
    grid-template-columns: repeat(2, 1fr);
  }
  .cw-stats {
    grid-template-columns: repeat(2, 1fr);
  }
}
@media (max-width: 700px) {
  .cw-content {
    padding-bottom: calc(100px + env(safe-area-inset-bottom));
  }
  input,
  select,
  textarea {
    font-size: 16px;
  }
  button {
    min-height: 44px;
  }
  .cw-header {
    gap: 12px;
  }
  .cw-brand p {
    display: none;
  }
  .cw-apps > button {
    min-height: 88px;
    padding: 12px;
  }
  .cw-apps > button > span:not(.cw-app-icon):not(.cw-app-arrow) {
    display: none;
  }
  .cw-app-icon {
    width: 32px;
    height: 32px;
    margin-bottom: 6px;
  }
  .cw-task-table {
    border: 0;
    background: transparent;
    overflow: visible;
  }
  .cw-task-table table,
  .cw-task-table tbody {
    display: block;
    min-width: 0;
  }
  .cw-task-table thead {
    display: none;
  }
  .cw-task-table tr {
    display: block;
    margin-bottom: 12px;
    padding: 16px;
    background: var(--gray-0);
    border: 1px solid var(--gray-100);
    border-radius: 12px;
  }
  .cw-task-table td {
    display: block;
    border: 0;
    padding: 5px 0;
    white-space: normal;
    overflow-wrap: anywhere;
  }
  .cw-task-table td[data-label] {
    display: grid;
    grid-template-columns: 95px 1fr;
    gap: 8px;
    align-items: center;
  }
  .cw-task-table td[data-label]::before {
    content: attr(data-label);
    color: var(--gray-500);
    font-size: 13px;
  }
  .cw-task-table .cw-task-name {
    font-size: 16px;
    font-weight: 600;
    padding-bottom: 10px;
  }
  .cw-task-table td:last-child button {
    width: 100%;
    margin-top: 10px;
    color: var(--main-color);
    background: var(--main-5);
    justify-content: center;
  }
  .cw-save-actions {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    z-index: 35;
    display: grid;
    grid-template-columns: 1fr 1fr 1.2fr;
    gap: 8px;
    padding: 10px 12px calc(10px + env(safe-area-inset-bottom));
    background: var(--gray-0);
    border-top: 1px solid var(--gray-100);
    box-shadow: 0 -4px 18px #00000008;
    margin: 0;
  }
  .cw-save-actions button {
    justify-content: center;
    min-width: 0;
    padding: 10px 4px;
    font-size: 14px;
  }
  .cw-mobile-voice {
    display: inline-flex;
  }
  .cw-mobile-voice.recording {
    color: #b42318;
    background: #fff0ed;
    border-color: #fda29b;
  }
  .cw-desktop-voice {
    display: none;
  }
  .cw-ai-controls {
    flex-wrap: wrap;
  }
  .cw-ai-controls select {
    min-width: 0;
    width: 100%;
  }
  .cw-modules {
    gap: 8px;
    padding: 4px 0 12px;
  }
  .cw-modules button {
    border-radius: 22px;
    padding: 9px 14px;
    font-size: 13px;
    white-space: nowrap;
  }
  .cw-header,
  .cw-content {
    padding: 20px 15px;
  }
  .cw-brand h1 {
    font-size: 18px;
  }
  .cw-nav {
    padding: 0 8px;
    overflow: auto;
    gap: 2px;
  }
  .cw-nav button {
    font-size: 12px;
    padding: 13px 9px;
  }
  .cw-member {
    display: none;
  }
  .cw-header-actions {
    width: 100%;
  }
  .cw-header-actions select {
    flex: 1;
    width: 140px;
  }
  .cw-apps,
  .cw-capabilities {
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }
  .cw-apps > button {
    padding: 14px;
  }
  .cw-apps strong {
    font-size: 14px;
  }
  .cw-stats {
    gap: 10px;
  }
  .cw-stats > div {
    padding: 12px;
  }
  .cw-stats strong {
    font-size: 23px;
  }
  .cw-stats span {
    font-size: 12px;
  }
  .cw-section-heading {
    align-items: flex-start;
    flex-wrap: wrap;
  }
  .cw-section-heading h2 {
    font-size: 20px;
  }
  .cw-toolbar {
    flex-wrap: wrap;
  }
  .cw-editor-layout {
    grid-template-columns: 1fr;
  }
  .cw-modules {
    flex-direction: row;
    overflow: auto;
  }
  .cw-modules button {
    flex-shrink: 0;
    max-width: none;
  }
  .cw-editor {
    padding: 16px;
  }
  .cw-steps span {
    font-size: 11px;
    padding: 10px 3px;
  }
  .cw-editor-meta {
    flex-wrap: wrap;
  }
  .cw-dialog {
    padding: 22px;
    width: 100%;
  }
  .cw-capabilities article {
    padding: 16px;
  }
  .cw-panel {
    padding: 18px;
  }
  .cw-content {
    padding-bottom: calc(100px + env(safe-area-inset-bottom));
  }
}
</style>
