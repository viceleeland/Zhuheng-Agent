import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'
import { ref, computed } from 'vue'

const source = fs
  .readFileSync(new URL('../../src/views/ChangweiView.vue', import.meta.url), 'utf8')
  .split('<script setup>')[1]
  .split('</script>')[0]
  .replace(/^import[\s\S]*?from\s+['"][^'"]+['"]\s*$/gm, '')

function deferred() {
  let resolve, reject
  const promise = new Promise((yes, no) => {
    resolve = yes
    reject = no
  })
  return { promise, resolve, reject }
}

function task(id, project = 'A', text = id, kind = 'supervision_log') {
  return { id, project_id: project, revision: 1, kind, content: { modules: [{ id: '0', text }] } }
}

function setup(api = {}, browserNavigator = { geolocation: null }) {
  const route = { path: '/changwei', fullPath: '/changwei', query: {} }
  const context = {
    ref,
    computed,
    watch: () => {},
    onMounted: () => {},
    useRoute: () => route,
    useRouter: () => ({ currentRoute: { value: route } }),
    useUserStore: () => ({ uid: 'owner' }),
    navigator: browserNavigator,
    useChangweiTranscription: () => ({
      state: ref('idle'),
      active: ref(false),
      partial: ref(''),
      error: ref(''),
      cancel: () => {}
    }),
    cw: { get: async () => [], ...api }
  }
  vm.createContext(context)
  vm.runInContext(
    source +
      '\nglobalThis.state = { projectId, projects, tasks, materials, audits, active, artifacts, section, editor, selectedModule, busy, error, run, boot, refreshProject, openTask, save, draft, generate, upload, templateId, supervisionTemplates, generatedOutputPath, generatedOutputWarning, weatherLocation, weatherResolvedLocation, weatherNote, fetchWeather, locateWeather };',
    context
  )
  return { s: context.state, route }
}

test('failed selected-project load clears every previous-project list', async () => {
  const { s } = setup({
    get: async () => {
      throw new Error('offline')
    }
  })
  s.projectId.value = 'B'
  s.tasks.value = [task('old')]
  s.materials.value = [{ id: 'old-material' }]
  s.audits.value = [{ id: 'old-audit' }]
  await s.run(s.refreshProject)
  assert.equal(s.tasks.value.length, 0)
  assert.equal(s.materials.value.length, 0)
  assert.equal(s.audits.value.length, 0)
  assert.equal(s.error.value, 'offline')
})

test('earlier same-project refresh cannot replace the newer result', async () => {
  const requests = []
  const { s } = setup({
    get: () => {
      const d = deferred()
      requests.push(d)
      return d.promise
    }
  })
  s.projectId.value = 'A'
  const old = s.refreshProject()
  const fresh = s.refreshProject()
  requests.slice(3).forEach((d, i) => d.resolve([{ id: `new-${i}` }]))
  await fresh
  requests.slice(0, 3).forEach((d, i) => d.resolve([{ id: `old-${i}` }]))
  await old
  assert.equal(s.tasks.value[0].id, 'new-0')
  assert.equal(s.materials.value[0].id, 'new-1')
  assert.equal(s.audits.value[0].id, 'new-2')
})

test('late task response cannot change navigation, active task or editor', async () => {
  const pending = deferred()
  const { s, route } = setup({ get: () => pending.promise })
  s.projectId.value = 'A'
  const opening = s.openTask('old')
  s.projectId.value = 'B'
  route.fullPath = '/changwei?project=B&view=platform'
  s.section.value = 'platform'
  s.editor.value = 'preserve'
  pending.resolve({ task: task('old'), artifacts: [] })
  await opening
  assert.equal(s.active.value, null)
  assert.equal(s.section.value, 'platform')
  assert.equal(s.editor.value, 'preserve')
})

test('opening a task from a different project fails without publishing it', async () => {
  const { s } = setup({ get: async () => ({ task: task('foreign', 'B'), artifacts: [] }) })
  s.projectId.value = 'A'
  await assert.rejects(s.openTask('foreign'), /任务不属于当前工程/)
  assert.equal(s.active.value, null)
})

test('old operation completion keeps the newer operation busy and suppresses old-route errors', async () => {
  const { s, route } = setup()
  const first = deferred(),
    second = deferred()
  const old = s.run(() => first.promise)
  route.fullPath = '/changwei?view=materials'
  const fresh = s.run(() => second.promise)
  first.reject(new Error('old route failure'))
  await old
  assert.equal(s.busy.value, true)
  assert.equal(s.error.value, '')
  second.resolve()
  await fresh
  assert.equal(s.busy.value, false)
})

test('late save cannot replace a newly selected task or its editor', async () => {
  const pending = deferred()
  const { s } = setup({ put: () => pending.promise })
  s.projectId.value = 'A'
  s.active.value = task('old')
  s.editor.value = 'old edits'
  const saving = s.save(false)
  s.active.value = task('new')
  s.editor.value = 'new edits'
  pending.resolve(task('old', 'A', 'saved old edits'))
  await saving
  assert.equal(s.active.value.id, 'new')
  assert.equal(s.editor.value, 'new edits')
})

test('late AI response cannot replace the current module text or task', async () => {
  const pending = deferred(),
    started = deferred()
  const { s } = setup({
    put: async () => task('old'),
    post: () => {
      started.resolve()
      return pending.promise
    }
  })
  s.projectId.value = 'A'
  s.active.value = task('old')
  const drafting = s.draft()
  await started.promise
  s.active.value = task('new')
  s.editor.value = 'new text'
  pending.resolve({ task: task('old'), text: 'old AI text', sources: [], notice: 'old notice' })
  await drafting
  assert.equal(s.active.value.id, 'new')
  assert.equal(s.editor.value, 'new text')
})

test('multi-file upload keeps the original project after navigation', async () => {
  const pending = deferred(),
    targets = []
  const { s } = setup({
    upload: (project) => {
      targets.push(project)
      return targets.length === 1 ? pending.promise : Promise.resolve()
    }
  })
  s.projectId.value = 'A'
  const uploading = s.upload({
    target: { files: [{ name: 'one' }, { name: 'two' }], value: 'selected' }
  })
  s.projectId.value = 'B'
  pending.resolve()
  await uploading
  assert.deepEqual(targets, ['A', 'A'])
})

test('initial project-load failure remains visible after boot selects the project', async () => {
  const { s } = setup({
    get: async (path) => {
      if (path === '/catalog') return { types: {}, categories: [], models: [] }
      if (path === '/projects') return [{ id: 'A' }]
      throw new Error('project service offline')
    }
  })
  await s.run(s.boot)
  assert.equal(s.projectId.value, 'A')
  assert.equal(s.error.value, 'project service offline')
  assert.equal(s.busy.value, false)
})

test('opening a supervision log selects the newest compatible original template', async () => {
  const selectedTask = task('log')
  const { s } = setup({ get: async () => ({ task: selectedTask, artifacts: [] }) })
  s.projectId.value = 'A'
  s.materials.value = [
    { id: 'tech', filename: '智能化系统技术方案.docx', created_at: '2026-09-19T12:00:00' },
    { id: 'old', filename: '2026-05-12三标段监理日志.docx', created_at: '2026-09-18T12:00:00' },
    { id: 'new', filename: '2026-05-29三标段监理日志.docx', created_at: '2026-09-19T11:00:00' }
  ]
  await s.openTask('log')
  assert.deepEqual(Array.from(s.supervisionTemplates.value, (item) => item.id), ['new', 'old'])
  assert.equal(s.templateId.value, 'new')
})

test('automatic weather location falls back to a human place-name instruction', async () => {
  const { s } = setup()
  await s.locateWeather()
  assert.match(s.weatherNote.value, /手动填写县、市或区名/)
})

test('manual weather lookup sends the typed place name instead of the button click event', async () => {
  const calls = []
  const { s } = setup({
    post: async (path, body) => {
      calls.push({ path, body })
      return { location: '武汉 / 武汉市 / 湖北省', text: '天气：晴', warning: '请核对。' }
    }
  })
  s.active.value = task('log')
  s.weatherLocation.value = ' 武汉市 '
  await s.fetchWeather({ type: 'click' })
  assert.equal(calls[0].body.location, '武汉市')
  assert.equal(s.weatherResolvedLocation.value, '武汉 / 武汉市 / 湖北省')
})

test('late automatic location cannot query or alter a newly selected task', async () => {
  let resolveLocation
  const calls = []
  const browserNavigator = {
    geolocation: {
      getCurrentPosition(resolve) {
        resolveLocation = resolve
      }
    }
  }
  const { s } = setup({ post: async (...args) => calls.push(args) }, browserNavigator)
  s.projectId.value = 'A'
  s.active.value = task('old')
  const locating = s.locateWeather()
  s.active.value = task('new')
  s.editor.value = 'new task text'
  resolveLocation({ coords: { longitude: 118.42, latitude: 29.87 } })
  await locating
  assert.deepEqual(calls, [])
  assert.equal(s.editor.value, 'new task text')
  assert.equal(s.weatherLocation.value, '')
})

test('automatic location keeps coordinates internal and reports the resolved place', async () => {
  const calls = []
  const browserNavigator = {
    geolocation: {
      getCurrentPosition(resolve) {
        resolve({ coords: { longitude: 118.424, latitude: 29.874 } })
      }
    }
  }
  const { s } = setup({
    post: async (path, body) => {
      calls.push({ path, body })
      return { location: '歙县 / 黄山市 / 安徽省', text: '天气：晴', warning: '请核对。' }
    }
  }, browserNavigator)
  s.projectId.value = 'A'
  s.active.value = task('log')
  s.editor.value = ''
  await s.locateWeather()
  assert.equal(calls[0].body.location, '118.42,29.87')
  assert.equal(s.weatherLocation.value, '')
  assert.equal(s.weatherResolvedLocation.value, '歙县 / 黄山市 / 安徽省')
  assert.match(s.weatherNote.value, /已识别：歙县/)
})
