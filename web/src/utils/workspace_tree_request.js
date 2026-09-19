export function resolveWorkspaceRoutePath(path) {
  return typeof path === 'string' && path.startsWith('/') ? path : '/'
}

export function createWorkspaceTreeRequest(fetchTree, { commit, setLoading, reportError }) {
  let generation = 0

  return async function loadWorkspaceTree(path = '/') {
    const request = ++generation
    setLoading(true)
    try {
      const response = await fetchTree(path)
      if (request !== generation) return false
      commit(path, response)
      return true
    } catch (error) {
      if (request === generation) reportError(error)
      return false
    } finally {
      if (request === generation) setLoading(false)
    }
  }
}
