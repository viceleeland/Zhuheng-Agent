import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import vm from 'node:vm'
import { effectScope } from 'vue'
import { useChangweiTranscription } from '../../src/composables/useChangweiTranscription.js'

const tick = async () => {
  for (let i = 0; i < 8; i++) await Promise.resolve()
}
function setup() {
  const sockets = [],
    tracks = [],
    nodes = []
  class Socket {
    static OPEN = 1
    constructor(url) {
      this.url = String(url)
      this.readyState = 1
      this.bufferedAmount = 0
      this.sent = []
      sockets.push(this)
    }
    send(value) {
      this.sent.push(value)
    }
    close() {
      this.readyState = 3
    }
    message(value) {
      this.onmessage?.({ data: JSON.stringify(value) })
    }
  }
  class Worklet {
    constructor() {
      nodes.push(this)
      this.port = {
        postMessage: () =>
          queueMicrotask(() => this.port.onmessage?.({ data: { type: 'flushed' } }))
      }
    }
    connect() {}
    disconnect() {}
  }
  class Context {
    state = 'running'
    destination = {}
    audioWorklet = { addModule: async () => {} }
    createMediaStreamSource() {
      return { connect() {}, disconnect() {} }
    }
    async resume() {}
    async close() {
      this.state = 'closed'
    }
  }
  globalThis.WebSocket = Socket
  globalThis.AudioContext = Context
  globalThis.AudioWorkletNode = Worklet
  globalThis.window = {
    isSecureContext: true,
    location: { href: 'https://cw.example/changwei' },
    AudioWorkletNode: Worklet
  }
  Object.defineProperty(globalThis, 'navigator', {
    configurable: true,
    value: {
      mediaDevices: {
        getUserMedia: async () => {
          const track = {
            stopped: false,
            stop() {
              this.stopped = true
            }
          }
          tracks.push(track)
          return { getTracks: () => [track] }
        }
      }
    }
  })
  const finalized = []
  const scope = effectScope()
  const speech = scope.run(() =>
    useChangweiTranscription((text, session) => finalized.push({ text, session }))
  )
  const start = async () => {
    speech.start({ taskId: 'task', moduleId: '0', token: 'test-token' })
    const socket = sockets.at(-1)
    socket.onopen()
    socket.message({ type: 'ready' })
    await tick()
    return socket
  }
  return { speech, scope, finalized, sockets, tracks, nodes, start }
}

test('JWT only sent in start frame; interim stays separate and final segment deduplicates', async () => {
  const env = setup()
  try {
    const socket = await env.start()
    assert.match(socket.url, /^wss:/)
    assert.ok(!socket.url.includes('test-token'))
    assert.equal(JSON.parse(socket.sent[0]).token, 'test-token')
    socket.message({ type: 'partial', segment_id: 's1', text: '正在说' })
    assert.equal(env.speech.partial.value, '正在说')
    assert.equal(env.finalized.length, 0)
    socket.message({ type: 'final', segment_id: 's1', text: '现场十人。' })
    socket.message({ type: 'final', segment_id: 's1', text: '现场十人。' })
    assert.deepEqual(
      env.finalized.map((x) => x.text),
      ['现场十人。']
    )
    assert.equal(env.speech.partial.value, '')
  } finally {
    env.scope.stop()
  }
})

test('stop immediately releases microphone then sends stop and accepts final until done', async () => {
  const env = setup()
  try {
    const socket = await env.start()
    env.speech.stop()
    assert.ok(env.tracks[0].stopped)
    assert.equal(env.speech.state.value, 'finishing')
    await tick()
    assert.equal(JSON.parse(socket.sent.at(-1)).type, 'stop')
    socket.message({ type: 'final', segment_id: 'last', text: '最后一句。' })
    socket.message({ type: 'done' })
    assert.equal(env.speech.state.value, 'idle')
    assert.equal(env.finalized[0].text, '最后一句。')
  } finally {
    env.scope.stop()
  }
})

test('cancel prevents late transcript and cleans pending permission stream', async () => {
  const env = setup()
  try {
    const socket = await env.start()
    const lateHandler = socket.onmessage
    env.speech.cancel()
    lateHandler({ data: JSON.stringify({ type: 'final', segment_id: 'late', text: '不可串入' }) })
    assert.equal(env.finalized.length, 0)
    assert.ok(env.tracks[0].stopped)
    let resolve
    navigator.mediaDevices.getUserMedia = () =>
      new Promise((r) => {
        resolve = r
      })
    env.speech.start({ taskId: 'another', moduleId: '0', token: 'test-token' })
    env.sockets.at(-1).message({ type: 'ready' })
    env.speech.cancel()
    const lateTrack = {
      stopped: false,
      stop() {
        this.stopped = true
      }
    }
    resolve({ getTracks: () => [lateTrack] })
    await tick()
    assert.ok(lateTrack.stopped)
  } finally {
    env.scope.stop()
  }
})

test('backpressure stops recording without adding another audio packet', async () => {
  const env = setup()
  try {
    const socket = await env.start()
    socket.bufferedAmount = 64001
    env.nodes[0].port.onmessage({ data: { type: 'audio', buffer: new ArrayBuffer(3200) } })
    await tick()
    assert.ok(env.tracks[0].stopped)
    assert.ok(socket.sent.every((frame) => typeof frame === 'string'))
    assert.match(env.speech.error.value, /网络发送过慢/)
  } finally {
    env.scope.stop()
  }
})

test('insecure origin does not open socket or request microphone', () => {
  const env = setup()
  try {
    window.isSecureContext = false
    env.speech.start({ taskId: 'task', moduleId: '0', token: 'test-token' })
    assert.equal(env.sockets.length, 0)
    assert.equal(env.tracks.length, 0)
    assert.match(env.speech.error.value, /HTTPS/)
  } finally {
    env.scope.stop()
  }
})

test('five minute limit stops capture and ten second finalization timeout closes socket', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const env = setup()
  try {
    const socket = await env.start()
    t.mock.timers.tick(5 * 60 * 1000)
    assert.equal(env.speech.state.value, 'finishing')
    assert.ok(env.tracks[0].stopped)
    await tick()
    t.mock.timers.tick(10000)
    assert.equal(env.speech.state.value, 'idle')
    assert.equal(socket.readyState, 3)
    assert.match(env.speech.error.value, /超时/)
  } finally {
    env.scope.stop()
    t.mock.timers.reset()
  }
})

for (const rate of [48000, 44100, 16000]) {
  test(`actual AudioWorklet converts ${rate} Hz to 100ms PCM16LE and flushes tail`, async () => {
    let Processor
    const messages = []
    const source = await readFile(
      new URL('../../src/worklets/changwei-pcm.js', import.meta.url),
      'utf8'
    )
    const context = {
      sampleRate: rate,
      AudioWorkletProcessor: class {
        constructor() {
          this.port = { postMessage: (m) => messages.push(m) }
        }
      },
      registerProcessor: (_, cls) => {
        Processor = cls
      }
    }
    vm.runInNewContext(source, context)
    const processor = new Processor()
    const samples = new Float32Array(rate / 10).fill(0.5)
    for (let i = 0; i < samples.length; i += 128)
      processor.process([[samples.subarray(i, i + 128)]])
    assert.equal(messages.length, 1)
    assert.equal(messages[0].buffer.byteLength, 3200)
    const view = new DataView(messages[0].buffer)
    // Non-integer hardware ratios can round one quantization step either way.
    for (let i = 0; i < 1600; i++) assert.ok(Math.abs(view.getInt16(i * 2, true) - 16384) <= 1)
    processor.process([[new Float32Array(Math.ceil(rate / 1000)).fill(-1)]])
    processor.port.onmessage({ data: { type: 'flush' } })
    assert.equal(messages.at(-1).type, 'flushed')
    assert.ok(messages.at(-2).buffer.byteLength > 0)
    assert.equal(new DataView(messages.at(-2).buffer).getInt16(0, true), -32768)
    assert.equal(processor.process([]), false)
  })
}
