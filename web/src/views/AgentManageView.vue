<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import PageHeader from '@/components/shared/PageHeader.vue'
import AgentManagePanel from '@/components/model-management/AgentManagePanel.vue'
import ModelProviderManagePanel from '@/components/model-management/ModelProviderManagePanel.vue'
import { useUserStore } from '@/stores/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const activeTab = ref(userStore.isAdmin ? 'providers' : 'agents')
const agentPanelRef = ref(null)
const providerPanelRef = ref(null)

const modelManageTabs = computed(() => {
  const tabs = []
  if (userStore.isAdmin) tabs.push({ key: 'providers', label: '模型供应商' })
  tabs.push({ key: 'agents', label: '高级助手配置' })
  return tabs
})

const activePanel = computed(() =>
  activeTab.value === 'providers' ? providerPanelRef.value : agentPanelRef.value
)

const activeLoading = computed(() => activePanel.value?.loading || false)
const activeStats = computed(() => activePanel.value?.stats || {})

const normalizeTab = (tab) => {
  if (tab === 'agents') return 'agents'
  if (tab === 'providers' && userStore.isAdmin) return 'providers'
  return userStore.isAdmin ? 'providers' : 'agents'
}

watch(
  () => [route.query.tab, userStore.isAdmin],
  ([tab]) => {
    const nextTab = normalizeTab(tab)
    if (activeTab.value !== nextTab) activeTab.value = nextTab
  },
  { immediate: true }
)

watch(activeTab, (tab) => {
  const nextTab = normalizeTab(tab)
  if (nextTab !== tab) {
    activeTab.value = nextTab
    return
  }
  if (route.query.tab === nextTab) return
  router.replace({ query: { ...route.query, tab: nextTab } })
})
</script>

<template>
  <div class="agent-manage-view">
    <PageHeader
      v-model:active-key="activeTab"
      title="模型与助手配置"
      :tabs="modelManageTabs"
      :loading="activeLoading"
      :show-border="true"
      aria-label="模型与助手配置视图切换"
    >
      <template #info>
        <div v-if="activeTab === 'agents'" class="summary-strip">
          <span>{{ activeStats.total || 0 }} 个助手</span>
          <span>{{ activeStats.global || 0 }} 个全局</span>
          <span v-if="activeStats.builtin">{{ activeStats.builtin }} 个内置</span>
          <span>{{ activeStats.manageable || 0 }} 个可管理</span>
        </div>
        <div v-else class="summary-strip">
          <span>{{ activeStats.total || 0 }} 个供应商</span>
          <span>{{ activeStats.enabled || 0 }} 个启用</span>
          <span v-if="activeStats.warning > 0" class="warning-count">
            {{ activeStats.warning }} 个凭证缺失
          </span>
          <span>{{ activeStats.models || 0 }} 个模型</span>
        </div>
      </template>
    </PageHeader>

    <div class="business-guidance">
      施工日志、方案审查和月报编制请前往
      <router-link to="/changwei">工程工作台</router-link>。
      这里管理模型供应商和高级自定义助手。
    </div>

    <div class="agent-manage-content">
      <div v-show="activeTab === 'agents'" class="tab-panel">
        <AgentManagePanel ref="agentPanelRef" />
      </div>
      <div v-if="userStore.isAdmin && activeTab === 'providers'" class="tab-panel">
        <ModelProviderManagePanel ref="providerPanelRef" />
      </div>
    </div>
  </div>
</template>

<style lang="less" scoped>
.agent-manage-view {
  display: flex;
  flex-direction: column;
  min-height: 100%;
  background: var(--gray-0);
  color: var(--gray-1000);
}

.agent-manage-content {
  flex: 1;
  min-height: 0;
  overflow: hidden;

  .tab-panel {
    height: 100%;
    min-height: 0;
    overflow-y: auto;
  }
}

.business-guidance {
  padding: 12px var(--page-padding);
  color: var(--gray-700);
  font-size: 13px;
  line-height: 1.7;
  background: var(--gray-10);
}

.summary-strip {
  display: flex;
  gap: 8px;

  span {
    padding: 6px 10px;
    border: 1px solid var(--gray-100);
    border-radius: 7px;
    background: var(--gray-10);
    color: var(--gray-700);
    font-size: 12px;
    line-height: 18px;
  }

  .warning-count {
    background: var(--color-warning-50);
    border-color: var(--color-warning-100);
    color: var(--color-warning-700);
  }
}
</style>
