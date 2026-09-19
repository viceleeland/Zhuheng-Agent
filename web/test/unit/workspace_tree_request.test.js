import assert from 'node:assert/strict'
import test from 'node:test'
import {
  createWorkspaceTreeRequest,
  resolveWorkspaceRoutePath
} from '../../src/utils/workspace_tree_request.js'

function deferred() {
  let resolve
  const promise = new Promise((done) => {
    resolve = done
  })
  return { promise, resolve }
}

test('workspace route without a path returns to the personal-space root', () => {
  assert.equal(resolveWorkspaceRoutePath(undefined), '/')
  assert.equal(resolveWorkspaceRoutePath('relative/path'), '/')
  assert.equal(resolveWorkspaceRoutePath('/outputs/江擎'), '/outputs/江擎')
})

test('late previous-directory response cannot replace the requested engineering outputs', async () => {
  const root = deferred()
  const outputs = deferred()
  const commits = []
  const loading = []
  const load = createWorkspaceTreeRequest(
    (path) => (path === '/' ? root.promise : outputs.promise),
    {
      commit: (path, response) => commits.push({ path, response }),
      setLoading: (value) => loading.push(value),
      reportError: (error) => assert.fail(error)
    }
  )

  const oldRequest = load('/')
  const currentRequest = load('/outputs/江擎')
  outputs.resolve({ entries: ['工程成果'] })
  assert.equal(await currentRequest, true)
  root.resolve({ entries: ['旧目录'] })
  assert.equal(await oldRequest, false)
  assert.deepEqual(commits, [
    { path: '/outputs/江擎', response: { entries: ['工程成果'] } }
  ])
  assert.deepEqual(loading, [true, true, false])
})
