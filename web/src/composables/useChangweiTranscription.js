import { computed, onScopeDispose, ref } from 'vue'
import { speechSocketUrl } from '../apis/changwei_speech_api.js'

// All transcript text remains an unsaved draft owned by the caller.
export function useChangweiTranscription(onFinal) {
  const state = ref('idle')
  const partial = ref('')
  const error = ref('')
  const active = computed(() => state.value !== 'idle')
  let current = null

  function releaseAudio(session) {
    session.stream?.getTracks().forEach((track) => track.stop())
    session.stream = null
    session.node?.disconnect()
    session.source?.disconnect()
    if (session.context && session.context.state !== 'closed') {
      void session.context.close().catch(() => {})
    }
    session.context = null
    session.node = null
  }

  function finish(session) {
    if (current !== session) return
    current = null
    clearTimeout(session.timer)
    clearTimeout(session.flushTimer)
    clearTimeout(session.finalTimer)
    releaseAudio(session)
    session.socket.onclose = null
    session.socket.onerror = null
    session.socket.onmessage = null
    session.socket.onopen = null
    session.socket.close()
    partial.value = ''
    state.value = 'idle'
  }

  function fail(session, message) {
    if (current !== session) return
    error.value = message
    finish(session)
  }

  function sendStop(session) {
    if (current !== session || session.stopSent) return
    session.stopSent = true
    clearTimeout(session.flushTimer)
    releaseAudio(session)
    if (session.socket.readyState === WebSocket.OPEN) {
      session.socket.send(JSON.stringify({ type: 'stop' }))
      session.finalTimer = setTimeout(() => {
        fail(session, '收尾等待超时，已识别文字保留；请核对最后一句。')
      }, 10000)
    } else {
      fail(session, '语音连接已断开，已识别文字保留。')
    }
  }

  function stop() {
    const session = current
    if (!session || state.value === 'finishing') return
    if (state.value === 'connecting') {
      cancel()
      return
    }
    state.value = 'finishing'
    clearTimeout(session.timer)
    session.stream?.getTracks().forEach((track) => track.stop())
    session.stream = null
    session.node?.port.postMessage({ type: 'flush' })
    session.flushTimer = setTimeout(() => sendStop(session), 500)
  }

  function cancel() {
    const session = current
    if (!session) return
    if (session.socket.readyState === WebSocket.OPEN) {
      session.socket.send(JSON.stringify({ type: 'cancel' }))
    }
    finish(session)
  }

  async function capture(session) {
    if (session.ready || current !== session) return
    session.ready = true
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true }
      })
      if (current !== session) {
        stream.getTracks().forEach((track) => track.stop())
        return
      }
      session.stream = stream
      const context = new AudioContext()
      session.context = context
      await context.audioWorklet.addModule(new URL('../worklets/changwei-pcm.js', import.meta.url))
      if (current !== session) return
      session.source = context.createMediaStreamSource(stream)
      session.node = new AudioWorkletNode(context, 'changwei-pcm')
      session.node.port.onmessage = ({ data }) => {
        if (current !== session) return
        if (data.type === 'flushed') {
          sendStop(session)
        } else if (data.type === 'audio' && !session.stopSent) {
          if (session.socket.bufferedAmount > 64000) {
            error.value = '网络发送过慢，已停止录音；请核对已有文字后重试。'
            stop()
            return
          }
          if (session.socket.readyState === WebSocket.OPEN) session.socket.send(data.buffer)
        }
      }
      session.source.connect(session.node)
      // The worklet emits silence to the destination, preventing microphone feedback.
      session.node.connect(context.destination)
      await context.resume()
      if (current !== session) return
      clearTimeout(session.timer)
      state.value = 'listening'
      session.timer = setTimeout(
        () => {
          error.value = '本次录音已达 5 分钟，正在收尾；可以稍后继续补充。'
          stop()
        },
        5 * 60 * 1000
      )
    } catch {
      fail(session, '无法启用麦克风，请检查浏览器权限、HTTPS 和音频设备。')
    }
  }

  function start({ taskId, moduleId, token }) {
    cancel()
    partial.value = ''
    error.value = ''
    if (
      !window.isSecureContext ||
      !navigator.mediaDevices?.getUserMedia ||
      !window.AudioWorkletNode
    ) {
      error.value = '实时语音需要 HTTPS（本机 localhost 也可）及支持麦克风的浏览器。'
      return
    }
    const url = speechSocketUrl(taskId, moduleId)
    let socket
    try {
      socket = new WebSocket(url)
    } catch {
      error.value = '无法建立语音连接，请检查浏览器网络设置。'
      return
    }
    const session = { socket, finals: new Set(), taskId, moduleId, ready: false, stopSent: false }
    current = session
    state.value = 'connecting'
    session.timer = setTimeout(() => fail(session, '语音连接或麦克风启动超时，请重试。'), 15000)
    socket.onopen = () => {
      if (current === session)
        socket.send(
          JSON.stringify({
            type: 'start',
            token,
            audio: { encoding: 'pcm_s16le', sample_rate: 16000, channels: 1 }
          })
        )
    }
    socket.onmessage = ({ data }) => {
      if (current !== session) return
      let message
      try {
        message = JSON.parse(data)
      } catch {
        fail(session, '语音服务返回格式异常。')
        return
      }
      if (!message || typeof message !== 'object') {
        fail(session, '语音服务返回格式异常。')
        return
      }
      if (message.type === 'ready') void capture(session)
      else if (message.type === 'partial' && typeof message.text === 'string')
        partial.value = message.text
      else if (message.type === 'final' && typeof message.text === 'string') {
        if (message.segment_id == null) {
          fail(session, '语音服务缺少分段标识。')
          return
        }
        const id = String(message.segment_id)
        if (!session.finals.has(id)) {
          session.finals.add(id)
          if (message.text.trim()) onFinal(message.text, { taskId, moduleId })
        }
        partial.value = ''
      } else if (message.type === 'done') {
        if (partial.value.trim()) error.value = '识别结束，但末句未确认；请核对并手动补充。'
        finish(session)
      } else if (message.type === 'error')
        fail(session, message.message || '语音识别失败，已识别文字保留。')
    }
    socket.onerror = () => fail(session, '无法连接语音服务，已识别文字保留。')
    socket.onclose = () => fail(session, '语音连接意外断开，已识别文字保留；请核对最后一句。')
  }

  onScopeDispose(cancel)
  return { state, active, partial, error, start, stop, cancel }
}
