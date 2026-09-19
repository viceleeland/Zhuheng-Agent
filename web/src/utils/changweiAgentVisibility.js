// 原平台的演示角色不进入工程产品的助手列表；保留持久数据和历史对话。
const DEMO_SLUGS = new Set([
  'deep-research',
  'research-explorer',
  'fact-verifier',
  'web-search',
  'general-purpose'
])

export function isEngineeringAssistant(agent) {
  return !DEMO_SLUGS.has(agent.slug || agent.agent_id || agent.id)
}
