import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'
import { ref, computed } from 'vue'
const source = fs.readFileSync(new URL('../../src/views/ChangweiDashboardView.vue', import.meta.url), 'utf8').split('<script setup>')[1].split('</script>')[0].replace(/^import .*$/gm, '')
function setup(get) {
  const context = { ref, computed, onMounted: () => {}, useRouter: () => ({ push: () => {} }), cw: { get } }
  vm.createContext(context)
  vm.runInContext(source + '\nglobalThis.state = { projectId, tasks, materials, loading, error, pendingTasks, pendingCount, generatedCount, breakdown, loadProject, refresh };', context)
  return context.state
}
test('overview counts confirmation per module and current generated task state', () => {
  const s = setup(() => {})
  s.tasks.value = [
    { kind: 'supervision_log', status: 'draft', content: { modules: [{ confirmed_by: 1 }, { confirmed_by: null }] } },
    { kind: 'supervision_log', status: 'generated', content: { modules: [{ confirmed_by: 2 }] } },
    { kind: 'scheme_review', status: 'draft', content: { modules: [{}, {}] } }
  ]
  assert.equal(s.pendingTasks.value, 2)
  assert.equal(s.pendingCount.value, 3)
  assert.equal(s.generatedCount.value, 1)
  assert.equal(s.breakdown.value.length, 5)
  assert.equal(s.breakdown.value[0].total, 2)
})
test('late previous-project responses cannot replace selected project statistics', async () => {
  const pending = new Map()
  const s = setup((path) => new Promise((resolve) => pending.set(path, resolve)))
  s.projectId.value = 'old'
  const old = s.loadProject()
  s.projectId.value = 'new'
  const fresh = s.loadProject()
  pending.get('/projects/new/tasks')([{ id: 'new-task' }])
  pending.get('/projects/new/materials')([])
  await fresh
  pending.get('/projects/old/tasks')([{ id: 'old-task' }])
  pending.get('/projects/old/materials')([{ id: 'old-material' }])
  await old
  assert.equal(s.tasks.value[0].id, 'new-task')
  assert.equal(s.materials.value.length, 0)
  assert.equal(s.loading.value, false)
})
test('failed project load exposes retry state without stale statistics', async () => {
  const s = setup(async () => { throw new Error('unavailable') })
  s.projectId.value = 'project'
  s.tasks.value = [{ id: 'stale' }]
  await s.loadProject()
  assert.equal(s.tasks.value.length, 0)
  assert.equal(s.error.value, 'unavailable')
  assert.equal(s.loading.value, false)
})
