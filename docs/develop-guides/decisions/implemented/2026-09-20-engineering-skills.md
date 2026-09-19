# 工程业务与 Skills 组合

状态：implemented
类型：feature
Owner：backend/package/yuxi/services/changwei_service.py

## 问题

五类工程草稿共享硬编码提示词，业务方法难以独立维护，也没有生成时的技能来源记录。

## 决策

为五类任务注册内置 Skills。工作台按任务类型加载随代码发布的技能正文，将事实与资料作为用户输入传入模型；草稿和审计保存 slug、版本及内容 SHA-256。内置技能同时通过已有 Skills 管理与 Agent 配置机制提供。业务工作台固定使用发布包中的技能，不接受个人同名覆盖；聊天选择技能仍遵循既有授权机制。

工程服务继续拥有资料筛选、权限、并发版本、人工确认、Word 模板和归档。技能只生成当前模块的待确认正文，不自主执行工程写入。当前范围不含聊天自动创建工程任务或完整规范库检索。

## 替代方案

保留硬编码提示词最简单，但无法独立迭代五类方法；完整改为自主 Agent 会引入额外任务编排和写入授权，超出本次范围。选择固定业务流程调用技能的组合方式。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 五类生成读取对应技能 | 文件存在但未使用 | changwei_service / changwei_skills | test_changwei_skills.py 捕获实际模型输入 | 缺失技能时不调用模型 | Passed |
| 技能可注册且来源可追溯 | 注册遗漏、摘要不对应 | builtin registry / draft | unit + test_engineering_skills_live.py 经 HTTP 后回读 PostgreSQL | 不支持类型与损坏元数据 | Passed |
| 保留人工确认和并发保护 | 模型覆盖新修改 | changwei_service | unit / 现有回归 | 调用期间 revision 改变拒绝写入，真实 HTTP 拒绝未确认导出 | Passed |

在运行中的 API 容器执行 `python -m pytest test/unit/test_changwei_skills.py test/unit/test_changwei_service.py test/unit/test_changwei_templates.py test/unit/test_changwei_documents.py -q`：58 passed；Skills 服务、中间件和 repository 的 82 项回归通过。显式配置测试用户和模型后，`python -m pytest test/integration/test_engineering_skills_live.py -q` 通过，内部覆盖五类业务，临时工程在 finally 中清理。另经真实数据库授权解析验证五类技能的 runtime preload 正文可读；普通聊天模型主动选择技能的完整对话未运行。

工程契约 verifier 通过；61 项 verifier 单元测试在 Linux 容器通过。Windows 原生执行受符号链接权限与路径分隔符预期限制。`git diff --check` 通过。

完整后端 unit 未通过：运行至 1232 passed、40 skipped、4 failed 后长时间停滞并中断。三个知识库 mock 签名错误和一个请求队列断言失败，在改动前 HEAD 的隔离源码副本中均复现（4 failed、7 passed）；本变更不处理这些已有问题。文档构建和 Ruff 校验因依赖下载持续失败或停滞而中断，未计为通过。

## 后果

技能规则仍需真实业务资料校准；注册不等于默认聊天已选中技能。外部模型生成质量与规则遵守不能由单元测试保证。
