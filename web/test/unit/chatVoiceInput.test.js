import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { compileScript, parse } from 'vue/compiler-sfc'
import { computed, effectScope, nextTick, reactive, ref, watch } from 'vue'

const source = readFileSync(new URL('../../src/components/AgentInputArea.vue', import.meta.url), 'utf8')
const parent = readFileSync(new URL('../../src/components/AgentChatComponent.vue', import.meta.url), 'utf8')

function setupInput() {
  const { descriptor } = parse(source)
  const compiled = compileScript(descriptor, { id: 'chat-voice-regression' }).content
    .replace(/^import .*$/gm, '')
    .replace('export default', 'return')
  const state = ref('idle')
  let deliver
  const speech = {
    state,
    active: computed(() => state.value !== 'idle'),
    partial: ref(''),
    error: ref(''),
    start: (options) => {
      assert.deepEqual(options, { chat: true, token: 'login-token' })
      state.value = 'listening'
    },
    stop: () => { state.value = 'finishing' },
    cancel: () => { state.value = 'idle' }
  }
  const dependencies = {
    computed, ref, watch,
    MessageInputComponent: {}, ImagePreviewComponent: {}, AttachmentOptionsComponent: {},
    X: {}, Mic: {}, Square: {}, FileTypeIcon: {},
    normalizeAttachmentPreviews: () => [], uploadMultimodalImage: () => {},
    useUserStore: () => ({ token: 'login-token' }),
    useChangweiTranscription: (onFinal) => { deliver = onFinal; return speech }
  }
  const component = new Function(...Object.keys(dependencies), compiled)(...Object.values(dependencies))
  const props = reactive({ modelValue: '原有草稿', threadId: 'first', disabled: false, isLoading: false })
  const events = []
  const scope = effectScope()
  const input = scope.run(() => component.setup(props, {
    expose() {},
    emit(type, value) {
      events.push({ type, value })
      if (type === 'update:modelValue') props.modelValue = value
    }
  }))
  return { input, props, events, state, scope, deliver }
}

test('语音追加原草稿且录音和收尾期间不发送，完成后可编辑并手动发送', () => {
  const env = setupInput()
  try {
    env.input.toggleSpeech()
    assert.deepEqual(env.events[0], { type: 'speech-active', value: true })
    env.deliver('第一句')
    env.deliver('第二句')
    assert.equal(env.props.modelValue, '原有草稿 第一句 第二句')
    env.input.handleSend()
    env.input.handleKeyDown({ key: 'Enter', preventDefault() {} })
    assert.equal(env.events.filter((event) => event.type === 'send').length, 0)
    env.input.toggleSpeech()
    assert.equal(env.state.value, 'finishing')
    env.deliver('最后一句')
    env.input.handleSend()
    assert.equal(env.events.filter((event) => event.type === 'send').length, 0)
    env.state.value = 'idle'
    assert.deepEqual(env.events.at(-1), { type: 'speech-active', value: false })
    env.input.updateValue('人工核对后的文字')
    assert.equal(env.props.modelValue, '人工核对后的文字')
    assert.equal(env.events.filter((event) => event.type === 'send').length, 0)
    env.input.handleSend()
    assert.equal(env.events.filter((event) => event.type === 'send').length, 1)
  } finally { env.scope.stop() }
})

test('切换会话取消录音并把非活动状态通知父级', async () => {
  const env = setupInput()
  try {
    env.input.toggleSpeech()
    env.props.threadId = 'second'
    await nextTick()
    assert.equal(env.state.value, 'idle')
    assert.deepEqual(env.events.at(-1), { type: 'speech-active', value: false })
  } finally { env.scope.stop() }
})

test('父级引导入口在录音时不可提交，结束后恢复', async () => {
  const computedSource = parent.match(/const canSubmitSteer = computed\([\s\S]*?\n\)/)?.[0]
  const actionSource = parent.match(/const handleDirectSteer = async \(\) => \{[\s\S]*?\n\}/)?.[0]
  assert.ok(computedSource && actionSource)
  const chatSpeechActive = ref(true)
  const sent = []
  const guard = new Function('computed', 'chatSpeechActive', 'isStreaming', 'currentThreadState',
    'userInput', 'hasPendingSteer', 'sendCooldownActive', 'isWaitingForUserAction', 'handleSendMessage',
    `${computedSource}\n${actionSource}\nreturn { canSubmitSteer, handleDirectSteer }`)(
    computed, chatSpeechActive, ref(true), ref({ activeRunSteerable: true }), ref('待核对语音'),
    ref(false), ref(false), ref(false), async (payload) => sent.push(payload))
  assert.equal(guard.canSubmitSteer.value, false)
  await guard.handleDirectSteer()
  assert.deepEqual(sent, [])
  chatSpeechActive.value = false
  assert.equal(guard.canSubmitSteer.value, true)
  await guard.handleDirectSteer()
  assert.deepEqual(sent, [{ queuePolicy: 'steer' }])
  assert.match(parent, /@speech-active="chatSpeechActive = \$event"/)
})

test('父级普通发送入口在录音时也拒绝调用，收尾后允许发送', async () => {
  const actionSource = parent.match(/const handleSendOrStop = async \(payload\) => \{[\s\S]*?\n\}/)?.[0]
  assert.ok(actionSource)
  const chatSpeechActive = ref(true)
  const sent = []
  const send = new Function('chatSpeechActive', 'sendCooldownActive', 'currentChatId',
    'getThreadState', 'userInput', 'canStopActiveRun', 'handleSendMessage',
    `${actionSource}\nreturn handleSendOrStop`)(
    chatSpeechActive, ref(false), ref('thread'), () => ({}), ref('语音草稿'), ref(false),
    async (payload) => sent.push(payload))
  await send({ image: null })
  assert.deepEqual(sent, [])
  chatSpeechActive.value = false
  await send({ image: null })
  assert.deepEqual(sent, [{ image: null }])
})
