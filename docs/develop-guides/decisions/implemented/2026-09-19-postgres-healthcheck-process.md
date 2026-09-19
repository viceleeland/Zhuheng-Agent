# PostgreSQL 健康检查直接执行探针

状态：implemented
类型：bug-fix
Owner：docker-compose.yml

## 问题

开发 PostgreSQL 容器由 postmaster 充当 PID 1，健康检查通过 `CMD-SHELL` 运行 `pg_isready … || exit 1`。Docker 超时终止 shell 后，尚未退出的 `pg_isready` 会成为 postmaster 的子进程。探针因连接超时返回 2 时，PostgreSQL 16 的子进程回收逻辑会将它视为异常服务进程，终止其余连接并执行崩溃恢复。一次健康检查超时因此会中断正常业务连接。

## 决策

[开发 Compose](../../../../docker-compose.yml) 的健康检查使用 `CMD` 直接执行 `pg_isready`，保留用户和数据库的 Compose 变量替换。探针内部超时明确为 3 秒，Docker 超时为 5 秒，给探针自行退出留出时间。其他服务、数据库目录和数据内容保持现有配置。

## 替代方案

单独增加 Docker 超时能减少竞争窗口，但 shell 仍可能在调度或 I/O 长时间阻塞时留下孤儿进程。`init: true` 可以负责回收孤儿进程，但会增加该服务的进程层级；直接执行探针已能消除当前 shell 子进程来源。

## 后果

应用健康检查配置需要重建 PostgreSQL 容器，会短暂断开现有连接。重建保留同一镜像与数据目录。连接超过探针期限时，Docker 仍能报告健康检查失败，数据库不再因该 shell 孤儿进程触发全库恢复。慢响应本身的资源或 I/O 原因不属于这项修复的已验证结论。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 慢连接导致探针超时，不触发数据库恢复 | shell 退出后孤儿探针返回 2 | PostgreSQL 16 与 Docker 健康检查进程 | 无业务数据且无网络的临时 PostgreSQL，设置 `pre_auth_delay=5`，Docker 超时 1 秒 | `CMD-SHELL` 下进程追踪显示 `child_comm=pg_isready`、`child_status=2` 后发生全库恢复 | Passed：旧配置 16 次退出码 2、16 次全库恢复；`CMD` 配置连续 12 次刻意超时、0 次全库恢复 |
| 开发配置实际使用直接执行 | 配置只改文件、运行容器仍用旧命令 | 开发 Compose | `docker compose config` 与容器 `Config.Healthcheck` 回读 | 原配置包含 shell 和 `|| exit 1` | Passed：运行容器为 `CMD`、探针 3 秒、Docker 5 秒 |
| 数据库与现有服务连接在更新后可用 | 容器更新改变挂载或服务连接未恢复 | 容器挂载、真实 SQL、API readiness | 挂载回读、SQL、`/api/system/ready` | 原故障导致活动连接中断和恢复期请求失败 | Passed：同镜像和挂载、相同数据库系统标识与数据库 OID、公开 schema 的 44 张表保留；PostgreSQL、Redis、worker readiness 均为 ok |

真实库未设置连接延迟；诊断用连接日志和错误详细度已恢复默认。临时慢连接测试库恢复正常延迟后健康检查返回 healthy。完整业务操作与持续负载稳定性需由相应验收链路证明，不能由 readiness 替代。
