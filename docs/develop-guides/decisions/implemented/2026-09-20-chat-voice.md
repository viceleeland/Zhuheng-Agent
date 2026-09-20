# 聊天输入实时语音

状态：implemented
类型：feature
Owner：web/src/components/AgentInputArea.vue

## 问题
聊天输入区缺少实时语音入口，原有语音接口依赖业务任务。

## 决策
输入框发送按钮旁提供麦克风按钮，点击后显示连接、聆听和收尾状态，停止后可编辑并手动发送。确认句子追加原草稿；临时识别单独展示，不自动发消息。录音及收尾期间父级普通发送与引导入口都拒绝提交，切换会话取消采集。

`web/src/composables/useChangweiTranscription.js` 复用 PCM 采集、句子去重、资源释放和五分钟限制。`backend/server/routers/changwei_router.py` 提供聊天端点，首帧认证当前登录用户后才调用既有模型转录服务，不依赖工程任务、不保存音频。原模块端点保留工程权限。

## 替代方案
跳转业务表单会中断聊天；浏览器内置识别不能保证一致的兼容性与模型行为。

## 后果
需要 HTTPS 或 localhost、麦克风权限和可用的转录模型配置。错误时保留已确认的草稿；用户仍负责核对文字。语音输入不改变业务审批与持久化边界。

## 验证
- Passed：后端 unit 1829 passed / 40 skipped；其中聊天认证路由与既有 relay 合计 34 项通过。运行 API 匿名和无效 token 均被拒绝。
- Passed：全量前端 197 项；额外新增聊天输入 4 项、转录 10 项回归，覆盖原草稿保留、最终句去重、取消后结果忽略、收尾阻止发送及父级引导保护。
- Passed：前端 lint、production build、文档构建；工程契约检查和 Linux 下 61 项 verifier unit。
- Passed：公网真实登录 start → 百炼 ready → cancel → 关闭，0.56 秒，发送音频 0 字节。
- Inspected：公网桌面及 390×844 手机视口可见麦克风，输入区无横向溢出。
- Not run：本次未采集用户真实麦克风进行语音准确率验收；浏览器截图不等于真实识别验证。
