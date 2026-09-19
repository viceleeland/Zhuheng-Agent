<template>
  <div class="login-view" :class="{ 'has-alert': serverStatus === 'error' }">
    <!-- 服务状态提示 -->
    <div v-if="serverStatus === 'error'" class="server-status-alert">
      <div class="alert-content">
        <exclamation-circle-icon class="alert-icon" size="20" />
        <div class="alert-text">
          <div class="alert-title">服务端连接失败</div>
          <div class="alert-message">{{ serverError }}</div>
        </div>
        <a-button type="link" size="small" @click="checkServerHealth" :loading="healthChecking">
          重试
        </a-button>
      </div>
    </div>

    <!-- 顶部导航：品牌名称 & 操作按钮 -->
    <nav class="login-navbar">
      <div class="navbar-content">
        <button class="brand-container" @click="goHome" aria-label="返回江擎首页">
          <img v-if="brandLogo" :src="brandLogo" alt="" class="brand-logo" />
          <h1 class="brand-text">
            <span v-if="brandOrgName" class="brand-org">{{ brandOrgName }}</span>
            <span v-if="brandOrgName && brandName !== brandOrgName" class="brand-separator"></span>
            <span v-if="brandName !== brandOrgName" class="brand-main">{{ brandName }}</span>
          </h1>
        </button>
      </div>
    </nav>

    <!-- 主要内容区：居中卡片 -->
    <main class="login-main">
      <div class="login-card">
        <div class="card-side is-brand" aria-label="水利工程智能协作">
          <img v-if="brandLogo" :src="brandLogo" alt="" class="panel-logo" />
          <div>
            <p class="panel-name">{{ brandName }}</p>
            <p class="panel-subtitle">水利工程智能协作</p>
          </div>
          <p class="panel-caption">工程资料 · 现场填报 · 成果交付</p>
        </div>

        <!-- 右侧表单 -->
        <div class="card-side is-form">
          <div class="form-wrapper">
            <header class="form-header">
              <!-- 如果是在初始化，显示特定标题 -->
              <h2 v-if="isFirstRun" class="init-title">系统初始化，请创建超级管理员</h2>
              <template v-else>
                <h2 class="welcome-text">登录工程工作台</h2>
                <p class="form-subtitle">使用工程账号，继续项目协作。</p>
              </template>
            </header>

            <div class="login-content" :class="{ 'is-initializing': isFirstRun }">
              <!-- 初始化管理员表单 -->
              <div v-if="isFirstRun" class="login-form login-form--init">
                <a-form :model="adminForm" @finish="handleInitialize" layout="vertical">
                  <a-form-item
                    label="UID"
                    name="uid"
                    :rules="[
                      { required: true, message: '请输入UID' },
                      {
                        pattern: /^[a-zA-Z0-9_]+$/,
                        message: 'UID只能包含字母、数字和下划线'
                      },
                      {
                        min: 3,
                        max: 20,
                        message: 'UID长度必须在3-20个字符之间'
                      }
                    ]"
                  >
                    <a-input
                      v-model:value="adminForm.uid"
                      placeholder="请输入UID（3-20个字符）"
                      :maxlength="20"
                    />
                  </a-form-item>

                  <a-form-item
                    label="手机号（可选）"
                    name="phone_number"
                    :rules="[
                      {
                        validator: async (rule, value) => {
                          if (!value || value.trim() === '') {
                            return // 空值允许
                          }
                          const phoneRegex = /^1[3-9]\d{9}$/
                          if (!phoneRegex.test(value)) {
                            throw new Error('请输入正确的手机号格式')
                          }
                        }
                      }
                    ]"
                  >
                    <a-input
                      v-model:value="adminForm.phone_number"
                      placeholder="可用于登录，可不填写"
                      :max-length="11"
                    />
                  </a-form-item>

                  <a-form-item
                    label="密码"
                    name="password"
                    :rules="[
                      { required: true, message: '请输入密码' },
                      {
                        min: MIN_PASSWORD_LENGTH,
                        message: `密码至少需要 ${MIN_PASSWORD_LENGTH} 个字符`
                      }
                    ]"
                  >
                    <a-input-password
                      v-model:value="adminForm.password"
                      prefix-icon="lock"
                      :minlength="MIN_PASSWORD_LENGTH"
                    />
                  </a-form-item>

                  <a-form-item
                    label="确认密码"
                    name="confirmPassword"
                    :rules="[
                      { required: true, message: '请确认密码' },
                      { validator: validateConfirmPassword }
                    ]"
                  >
                    <a-input-password
                      v-model:value="adminForm.confirmPassword"
                      prefix-icon="lock"
                    />
                  </a-form-item>

                  <a-form-item v-if="showAgreementConsent" class="agreement-form-item">
                    <div class="agreement-row">
                      <a-checkbox v-model:checked="agreementAccepted">
                        登录即代表同意
                        <a
                          class="agreement-link"
                          :href="userAgreementUrl"
                          target="_blank"
                          rel="noopener noreferrer"
                          @click.stop
                          >《用户协议》</a
                        >
                        <a
                          class="agreement-link"
                          :href="privacyPolicyUrl"
                          target="_blank"
                          rel="noopener noreferrer"
                          @click.stop
                          >《隐私协议》</a
                        >
                      </a-checkbox>
                    </div>
                  </a-form-item>

                  <a-form-item>
                    <a-button type="primary" html-type="submit" :loading="loading" block
                      >创建管理员账户</a-button
                    >
                  </a-form-item>
                </a-form>
              </div>

              <!-- 登录表单 -->
              <div v-else class="login-form">
                <a-form :model="loginForm" @finish="handleLogin" layout="vertical">
                  <a-form-item
                    label="登录账号"
                    name="loginId"
                    :rules="[{ required: true, message: '请输入UID或手机号' }]"
                  >
                    <a-input v-model:value="loginForm.loginId" placeholder="UID或手机号">
                      <template #prefix>
                        <user-icon size="18" />
                      </template>
                    </a-input>
                  </a-form-item>

                  <a-form-item
                    label="密码"
                    name="password"
                    :rules="[{ required: true, message: '请输入密码' }]"
                  >
                    <a-input-password v-model:value="loginForm.password">
                      <template #prefix>
                        <lock-icon size="18" />
                      </template>
                    </a-input-password>
                  </a-form-item>

                  <a-form-item v-if="showAgreementConsent" class="agreement-form-item">
                    <div class="agreement-row">
                      <a-checkbox v-model:checked="agreementAccepted">
                        登录即代表同意
                        <a
                          class="agreement-link"
                          :href="userAgreementUrl"
                          target="_blank"
                          rel="noopener noreferrer"
                          @click.stop
                          >《用户协议》</a
                        >
                        <a
                          class="agreement-link"
                          :href="privacyPolicyUrl"
                          target="_blank"
                          rel="noopener noreferrer"
                          @click.stop
                          >《隐私协议》</a
                        >
                      </a-checkbox>
                    </div>
                  </a-form-item>

                  <a-form-item>
                    <a-button
                      type="primary"
                      html-type="submit"
                      :loading="loading"
                      :disabled="isLocked"
                      block
                      size="large"
                    >
                      <span v-if="isLocked">账户已锁定 {{ formatTime(lockRemainingTime) }}</span>
                      <span v-else>登录</span>
                    </a-button>
                  </a-form-item>
                </a-form>

                <!-- OIDC 登录选项  -->
                <div v-if="oidcChecking || oidcEnabled" class="third-party-login">
                  <div class="divider">
                    <span>或使用以下方式登录</span>
                  </div>
                  <div class="login-icons">
                    <!-- 检查中显示骨架屏 -->
                    <div v-if="oidcChecking" class="login-skeleton">
                      <a-skeleton-button block size="large" :active="true" />
                    </div>
                    <!-- 检查完成后显示按钮 -->
                    <a-button
                      v-else
                      type="default"
                      size="large"
                      block
                      :loading="oidcLoading"
                      @click="handleOIDCLogin"
                    >
                      <template #icon>
                        <key-icon size="18" />
                      </template>
                      {{ oidcButtonText }}
                    </a-button>
                  </div>
                </div>
              </div>

              <!-- 错误提示 -->
              <div v-if="errorMessage" class="error-message">
                {{ errorMessage }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>

    <!-- 页面底部：版权信息等 -->
    <footer class="page-footer">
      <div class="copyright">
        {{ infoStore.footer.copyright }}
      </div>
    </footer>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { useInfoStore } from '@/stores/info'
import { useAgentStore } from '@/stores/agent'
import { message } from 'ant-design-vue'
import { healthApi } from '@/apis/system_api'
import { authApi } from '@/apis/auth_api'
import {
  User as UserIcon,
  Lock as LockIcon,
  Key as KeyIcon,
  AlertCircle as ExclamationCircleIcon
} from '@lucide/vue'
import { tryAutoStartOIDC, sanitizeRedirect } from '@/utils/oidcAutoStart'
import { MIN_PASSWORD_LENGTH } from '@/utils/passwordValidation'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const infoStore = useInfoStore()
const agentStore = useAgentStore()

// 品牌展示数据
const brandLogo = computed(() => {
  return infoStore.organization?.logo || ''
})
const brandOrgName = computed(() => {
  return infoStore.organization?.name?.trim() || ''
})
const brandName = computed(() => {
  const orgName = brandOrgName.value
  const brandNameRaw = infoStore.branding?.name?.trim() || '江擎'

  if (orgName && brandNameRaw && orgName !== brandNameRaw) {
    return brandNameRaw
  }

  return orgName || brandNameRaw
})
const userAgreementUrl = computed(() => {
  return infoStore.footer?.user_agreement_url?.trim() || ''
})
const privacyPolicyUrl = computed(() => {
  return infoStore.footer?.privacy_policy_url?.trim() || ''
})
const showAgreementConsent = computed(() => {
  return Boolean(userAgreementUrl.value && privacyPolicyUrl.value)
})

// 状态
const isFirstRun = ref(false)
const loading = ref(false)
const errorMessage = ref('')
const agreementAccepted = ref(false)
const serverStatus = ref('loading')
const serverError = ref('')
const healthChecking = ref(false)

// OIDC 相关状态
const oidcEnabled = ref(false)
const oidcLoading = ref(false)
const oidcChecking = ref(true)
const oidcButtonText = ref('OIDC 登录')

// 登录锁定相关状态
const isLocked = ref(false)
const lockRemainingTime = ref(0)
const lockCountdown = ref(null)

// 登录表单
const loginForm = reactive({
  loginId: '', // 支持uid或phone_number登录
  password: ''
})

// 管理员初始化表单
const adminForm = reactive({
  uid: '', // 改为直接输入uid
  password: '',
  confirmPassword: '',
  phone_number: '' // 手机号字段（可选）
})

const goHome = () => {
  router.push('/')
}

// 清理倒计时器
const clearLockCountdown = () => {
  if (lockCountdown.value) {
    clearInterval(lockCountdown.value)
    lockCountdown.value = null
  }
}

// 启动锁定倒计时
const startLockCountdown = (remainingSeconds) => {
  clearLockCountdown()
  isLocked.value = true
  lockRemainingTime.value = remainingSeconds

  lockCountdown.value = setInterval(() => {
    lockRemainingTime.value--
    if (lockRemainingTime.value <= 0) {
      clearLockCountdown()
      isLocked.value = false
      errorMessage.value = ''
    }
  }, 1000)
}

// 格式化时间显示
const formatTime = (seconds) => {
  if (seconds < 60) {
    return `${seconds}秒`
  } else if (seconds < 3600) {
    const minutes = Math.floor(seconds / 60)
    const remainingSeconds = seconds % 60
    return `${minutes}分${remainingSeconds}秒`
  } else if (seconds < 86400) {
    const hours = Math.floor(seconds / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)
    return `${hours}小时${minutes}分钟`
  } else {
    const days = Math.floor(seconds / 86400)
    const hours = Math.floor((seconds % 86400) / 3600)
    return `${days}天${hours}小时`
  }
}

// 密码确认验证
const validateConfirmPassword = async (rule, value) => {
  if (value === '') {
    throw new Error('请确认密码')
  }
  if (value !== adminForm.password) {
    throw new Error('两次输入的密码不一致')
  }
}

const ensureAgreementAccepted = () => {
  if (!showAgreementConsent.value || agreementAccepted.value) {
    return true
  }

  const warningMessage = '请先阅读并同意《用户协议》《隐私协议》'
  message.warning(warningMessage)
  return false
}

// 处理登录
const handleLogin = async () => {
  // 如果当前被锁定，不允许登录
  if (isLocked.value) {
    message.warning(`账户被锁定，请等待 ${formatTime(lockRemainingTime.value)}`)
    return
  }

  if (!ensureAgreementAccepted()) {
    return
  }

  try {
    loading.value = true
    errorMessage.value = ''
    clearLockCountdown()

    await userStore.login({
      loginId: loginForm.loginId,
      password: loginForm.password
    })

    message.success('登录成功')

    // 获取重定向路径
    const redirectPath = sessionStorage.getItem('redirect') || '/'
    sessionStorage.removeItem('redirect') // 清除重定向信息

    // 根据用户角色决定重定向目标
    if (redirectPath === '/') {
      // 统一跳转到聊天页面（管理员与普通用户共享同一聊天界面）
      try {
        await agentStore.initialize()
        router.push('/changwei')
      } catch (error) {
        console.error('获取智能体信息失败:', error)
        router.push('/changwei')
      }
    } else {
      // 跳转到其他预设的路径
      router.push(redirectPath)
    }
  } catch (error) {
    console.error('登录失败:', error)

    // 检查是否是锁定错误（HTTP 423）
    if (error.status === 423) {
      // 尝试从响应头中获取剩余时间
      let remainingTime = 0
      if (error.headers && error.headers.get) {
        const lockRemainingHeader = error.headers.get('X-Lock-Remaining')
        if (lockRemainingHeader) {
          remainingTime = parseInt(lockRemainingHeader)
        }
      }

      // 如果没有从头中获取到，尝试从错误消息中解析
      if (remainingTime === 0) {
        const lockTimeMatch = error.message.match(/(\d+)\s*秒/)
        if (lockTimeMatch) {
          remainingTime = parseInt(lockTimeMatch[1])
        }
      }

      if (remainingTime > 0) {
        startLockCountdown(remainingTime)
        errorMessage.value = `由于多次登录失败，账户已被锁定 ${formatTime(remainingTime)}`
      } else {
        errorMessage.value = error.message || '账户被锁定，请稍后再试'
      }
    } else {
      errorMessage.value = error.message || '登录失败，请检查用户名和密码'
    }
  } finally {
    loading.value = false
  }
}

// 处理 OIDC 登录
const handleOIDCLogin = async () => {
  if (!ensureAgreementAccepted()) {
    return
  }

  try {
    oidcLoading.value = true
    errorMessage.value = ''

    // 获取 OIDC 登录 URL
    const response = await authApi.getOIDCLoginUrl()
    if (response.login_url) {
      // 保存当前路径，以便登录后返回
      const redirectPath =
        sessionStorage.getItem('redirect') || router.currentRoute.value.query.redirect || '/'
      sessionStorage.setItem('oidc_redirect', redirectPath)

      // 跳转到 OIDC Provider
      window.location.href = response.login_url
    } else {
      errorMessage.value = '获取 OIDC 登录地址失败'
    }
  } catch (error) {
    console.error('OIDC 登录失败:', error)
    errorMessage.value = error.message || 'OIDC 登录失败，请重试'
  } finally {
    oidcLoading.value = false
  }
}

// 检查 OIDC 配置
const checkOIDCConfig = async () => {
  oidcChecking.value = true
  try {
    const config = await authApi.getOIDCConfig()
    oidcEnabled.value = config.enabled
    if (config.provider_name) {
      oidcButtonText.value = config.provider_name
    }
    return config
  } catch (error) {
    console.error('检查 OIDC 配置失败:', error)
    oidcEnabled.value = false
    return null
  } finally {
    oidcChecking.value = false
  }
}

// 处理初始化管理员
const handleInitialize = async () => {
  if (!ensureAgreementAccepted()) {
    return
  }

  try {
    loading.value = true
    errorMessage.value = ''

    if (adminForm.password !== adminForm.confirmPassword) {
      errorMessage.value = '两次输入的密码不一致'
      return
    }

    await userStore.initialize({
      uid: adminForm.uid,
      password: adminForm.password,
      phone_number: adminForm.phone_number || null // 空字符串转为null
    })

    message.success('管理员账户创建成功')
    router.push('/')
  } catch (error) {
    console.error('初始化失败:', error)
    errorMessage.value = error.message || '初始化失败，请重试'
  } finally {
    loading.value = false
  }
}

// 检查是否是首次运行
const checkFirstRunStatus = async () => {
  try {
    loading.value = true
    const isFirst = await userStore.checkFirstRun()
    isFirstRun.value = isFirst
  } catch (error) {
    console.error('检查首次运行状态失败:', error)
    errorMessage.value = '系统出错，请稍后重试'
  } finally {
    loading.value = false
  }
}

// 检查服务器健康状态
const checkServerHealth = async () => {
  try {
    healthChecking.value = true
    const response = await healthApi.checkHealth()
    if (response.status === 'ok') {
      serverStatus.value = 'ok'
    } else {
      serverStatus.value = 'error'
      serverError.value = response.message || '服务端状态异常'
    }
  } catch (error) {
    console.error('检查服务器健康状态失败:', error)
    serverStatus.value = 'error'
    serverError.value = error.message || '无法连接到服务端，请检查网络连接'
  } finally {
    healthChecking.value = false
  }
}

// 组件挂载时
onMounted(async () => {
  // 如果已登录，按 redirect 参数跳转（不固定跳首页）
  if (userStore.isLoggedIn) {
    router.push(sanitizeRedirect(route.query.redirect))
    return
  }

  // 显示 OIDC 认证失败的错误信息（由后端重定向携带）
  if (route.query.oidc_error) {
    errorMessage.value = String(route.query.oidc_error)
  }

  // 首先检查服务器健康状态
  await checkServerHealth()

  // 检查是否是首次运行
  await checkFirstRunStatus()

  // 如果处于首次运行状态，不需要 OIDC 自动登录
  if (isFirstRun.value) {
    return
  }

  // 检查 OIDC 配置完成后，尝试自动触发 OIDC 登录（跨系统跳转场景）
  const config = await checkOIDCConfig()
  if (config && config.enabled) {
    const autoStarted = await tryAutoStartOIDC(async () => await authApi.getOIDCLoginUrl(), config)
    // 如果已发起 OIDC 跳转，页面会被重定向，不需要继续
    if (autoStarted) return
  }
})

// 组件卸载时清理定时器
onUnmounted(() => {
  clearLockCountdown()
})
</script>

<style lang="less" scoped>
.login-view {
  min-height: 100vh;
  min-height: 100dvh;
  display: flex;
  flex-direction: column;
  background: var(--app-canvas);
  color: var(--gray-900);
  font-size: 16px;
}
.login-navbar {
  padding: max(28px, env(safe-area-inset-top)) 40px 20px;
}
.navbar-content {
  max-width: 1120px;
  margin: 0 auto;
}
.brand-container {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  min-height: 44px;
  padding: 0;
  border: 0;
  background: none;
  cursor: pointer;
  color: var(--app-navy);
}
.brand-logo {
  width: 40px;
  height: 40px;
  object-fit: contain;
}
.brand-text {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 0;
  font-size: 23px;
  line-height: 1.3;
}
.brand-org,
.brand-main {
  font-weight: 650;
}
.brand-separator {
  width: 1px;
  height: 20px;
  background: var(--gray-300);
}
.login-main {
  display: flex;
  flex: 1;
  align-items: center;
  justify-content: center;
  padding: 28px 32px 48px;
}
.login-card {
  display: grid;
  grid-template-columns: 0.85fr 1.15fr;
  width: min(920px, 100%);
  min-height: 540px;
  border: 1px solid var(--gray-200);
  border-radius: 12px;
  background: var(--gray-0);
  overflow: hidden;
}
.card-side.is-brand {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 32px;
  padding: 56px 40px 40px;
  background: var(--app-navy-solid);
  color: var(--app-on-navy);
}
.panel-logo {
  width: 68px;
  height: 68px;
  object-fit: contain;
}
.panel-name {
  font-size: 36px;
  font-weight: 600;
  line-height: 1.3;
  margin: 0 0 12px;
}
.panel-subtitle {
  font-size: 20px;
  line-height: 1.5;
  margin: 0;
}
.panel-caption {
  margin: auto 0 0;
  padding-top: 40px;
  color: var(--app-on-navy-muted);
  font-size: 14px;
  line-height: 1.8;
}
.card-side.is-form {
  display: flex;
  align-items: center;
  padding: 48px;
}
.form-wrapper {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 32px;
}
.form-header .welcome-text,
.form-header .init-title {
  margin: 0;
  font-size: 26px;
  font-weight: 600;
  color: var(--app-navy);
  line-height: 1.4;
}
.form-subtitle {
  margin: 8px 0 0;
  font-size: 16px;
  color: var(--gray-600);
  line-height: 1.6;
}
.login-form {
  :deep(.ant-form-item-label > label) {
    font-size: 16px;
    color: var(--gray-800);
  }
  :deep(.ant-input),
  :deep(.ant-input-affix-wrapper) {
    font-size: 16px;
  }
  :deep(.ant-input-affix-wrapper) {
    min-height: 48px;
    padding: 3px 14px;
    border-radius: 6px;
    border-color: var(--gray-300);
  }
  :deep(.ant-input-prefix) {
    margin-right: 10px;
    color: var(--gray-600);
  }
  :deep(.ant-input-password-icon) {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 44px;
    min-height: 44px;
  }
  :deep(.ant-btn) {
    min-height: 48px;
    height: auto;
    font-size: 16px;
    font-weight: 600;
    border-radius: 6px;
    box-shadow: none;
  }
  :deep(.ant-btn-primary) {
    background: var(--app-accent);
    border-color: var(--app-accent);
    color: var(--app-on-accent);
  }
  :deep(.ant-btn-primary:hover) {
    background: var(--app-accent-hover);
    border-color: var(--app-accent-hover);
  }
}
.login-form--init :deep(.ant-form-item) {
  margin-bottom: 16px;
}
.agreement-form-item {
  margin-bottom: 20px;
}
.agreement-row {
  color: var(--gray-600);
  line-height: 1.7;
  :deep(.ant-checkbox-wrapper) {
    display: flex;
    align-items: flex-start;
    min-height: 44px;
    font-size: 14px;
    padding: 8px 0;
  }
  :deep(.ant-checkbox) {
    margin-top: 3px;
  }
  :deep(.ant-checkbox + span) {
    padding-inline-start: 10px;
  }
}
.agreement-link {
  color: var(--app-accent);
  text-decoration: underline;
  text-underline-offset: 3px;
}
.agreement-link:visited {
  color: var(--main-800);
}
.third-party-login {
  margin-top: 20px;
  .divider {
    display: flex;
    align-items: center;
    gap: 12px;
    margin: 16px 0;
    color: var(--gray-600);
    font-size: 14px;
  }
  .divider::before,
  .divider::after {
    content: '';
    height: 1px;
    flex: 1;
    background: var(--gray-200);
  }
  .login-icons :deep(.ant-btn) {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
  }
  .login-skeleton :deep(.ant-skeleton-button) {
    width: 100% !important;
    height: 48px;
  }
}
.error-message {
  margin-top: 20px;
  padding: 12px 16px;
  background: var(--color-error-50);
  border: 1px solid var(--color-error-100);
  border-radius: 6px;
  color: var(--color-error-700);
  font-size: 16px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}
.page-footer {
  padding: 0 24px max(24px, env(safe-area-inset-bottom));
  text-align: center;
}
.copyright {
  font-size: 13px;
  color: var(--gray-600);
}
.server-status-alert {
  padding: 16px 24px;
  background: var(--color-error-50);
  color: var(--color-error-700);
  border-bottom: 1px solid var(--color-error-100);
}
.alert-content {
  display: flex;
  gap: 12px;
  align-items: center;
  max-width: 1120px;
  margin: 0 auto;
}
.alert-icon {
  flex-shrink: 0;
}
.alert-text {
  flex: 1;
  min-width: 0;
}
.alert-title {
  font-weight: 600;
  font-size: 16px;
}
.alert-message {
  font-size: 14px;
  overflow-wrap: anywhere;
}
.alert-content :deep(.ant-btn) {
  min-height: 44px;
  min-width: 60px;
  color: var(--color-error-700);
}
:focus-visible,
:deep(.ant-input-affix-wrapper-focused) {
  outline: 3px solid var(--app-focus);
  outline-offset: 3px;
}
@media (max-width: 700px) {
  .login-navbar {
    padding: max(28px, env(safe-area-inset-top)) 24px 20px;
  }
  .login-main {
    align-items: flex-start;
    padding: 32px 24px 40px;
  }
  .login-card {
    display: block;
    border: 0;
    border-radius: 0;
    min-height: auto;
    background: none;
  }
  .card-side.is-brand {
    display: none;
  }
  .card-side.is-form {
    padding: 0;
  }
  .form-wrapper {
    gap: 36px;
  }
  .form-header .welcome-text {
    font-size: 28px;
  }
  .login-form :deep(.ant-input-affix-wrapper) {
    min-height: 52px;
    background: var(--gray-0);
  }
  .login-form :deep(.ant-input-password-icon) {
    min-height: 44px;
    width: 44px;
  }
  .login-form :deep(.ant-btn) {
    min-height: 52px;
  }
  .login-form :deep(.ant-form-item) {
    margin-bottom: 24px;
  }
  .page-footer {
    padding-top: 20px;
  }
}
@media (prefers-reduced-motion: reduce) {
  *,
  :deep(*) {
    transition: none !important;
    animation: none !important;
  }
}
</style>
