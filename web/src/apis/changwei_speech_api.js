export function speechSocketUrl(taskId, moduleId) {
  const url = new URL(
    `/api/changwei/tasks/${encodeURIComponent(taskId)}/modules/${encodeURIComponent(moduleId)}/transcribe`,
    window.location.href
  )
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  return url
}

export function chatSpeechSocketUrl() {
  const url = new URL('/api/changwei/transcribe/chat', window.location.href)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  return url
}
