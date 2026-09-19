import { apiRequest } from './base'
const root = '/api/changwei'
export const cw = {
  get: (path) => apiRequest(root + path),
  post: (path, body) => apiRequest(root + path, { method: 'POST', body: JSON.stringify(body) }),
  put: (path, body) => apiRequest(root + path, { method: 'PUT', body: JSON.stringify(body) }),
  upload: (project, file) => {
    const form = new FormData()
    form.append('file', file)
    return apiRequest(`${root}/projects/${project}/materials`, { method: 'POST', body: form })
  },
  download: async (artifact) => {
    const response = await apiRequest(`${root}/artifacts/${artifact.id}/download`, {}, true, 'blob')
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = artifact.filename
    link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
}
