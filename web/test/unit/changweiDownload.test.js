import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import vm from 'node:vm'

test('artifact download consumes the Response body before creating a browser Blob URL', async () => {
  const source = await readFile(new URL('../../src/apis/changwei_api.js', import.meta.url), 'utf8')
  let savedBlob
  let clicked = false
  const link = { click() { clicked = true } }
  const bytes = new Uint8Array([80, 75, 3, 4, 10, 20])
  const context = vm.createContext({
    apiRequest: async () => new Response(bytes),
    URL: {
      createObjectURL(blob) {
        assert.ok(blob instanceof Blob, 'apiRequest returns Response; it must be converted to Blob')
        savedBlob = blob
        return 'blob:verified'
      },
      revokeObjectURL() {}
    },
    document: { createElement: () => link },
    setTimeout: (fn) => fn()
  })
  vm.runInContext(source.replace(/^import .*\n/, '').replace('export const cw', 'globalThis.cw'), context)
  await context.cw.download({ id: 'test-artifact', filename: '验收.docx' })
  assert.deepEqual(new Uint8Array(await savedBlob.arrayBuffer()), bytes)
  assert.equal(link.download, '验收.docx')
  assert.equal(clicked, true)
})
