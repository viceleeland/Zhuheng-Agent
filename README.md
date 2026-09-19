# 筑衡Agent

面向水利工程监理与项目管理的智能协作系统。项目以工程、标段和业务任务为主线，把资料整理、施工日志、月报、方案辅助审查、人工确认和 Word 成果归档放在同一套工作台中。

> 当前产品界面名称为“江擎 · 水利工程智能协作”；`Zhuheng-Agent` 是本仓库名称。仓库基于 [Yuxi](https://github.com/xerrors/Yuxi) 二次开发，并保留原项目许可证与必要的架构说明。

## 主要能力

### 工程工作台

- 按工程和标段组织资料、成员、任务与成果。
- 支持监理日志、项管日志、监理月报、项管月报和施工方案审核五类业务。
- 展示待处理、待确认、已确认和已生成等业务状态。
- 负责人和被分派成员按模块填写、保存和确认，避免多人编辑互相覆盖。

### 资料与知识库

- 上传并整理 Word、Excel、PDF、TXT 和 ZIP 资料。
- 支持文档解析、分块、向量检索、知识引用和扫描 PDF 的分批 OCR。
- 业务任务只读取本次明确选择并确认的资料，生成内容仍需人工核对。
- 保留 Yuxi 的知识库、RAG、Agent、Skills、MCP、沙盒和权限基础能力。

### AI 辅助业务

- **施工日志**：根据现场文字或实时语音整理人员、设备、进度、质量、安全和天气信息。
- **月报编制**：按报告期汇总材料和台账，生成可继续修订的初稿。
- **方案辅助审查**：结合送审方案和项目依据输出问题、依据与建议，供专业人员复核。
- **实时语音**：通过后端连接云端实时转录服务，密钥不进入手机或浏览器。
- **天气填报**：支持设备定位，也可直接填写“武汉”“武汉市”等地名查询当日实况。

### 成果生成与归档

- 全部模块确认后生成 Word 成果。
- 监理日志优先沿用上传的原始模板，只填写对应字段并保留原版式。
- 成果文件名自动包含业务日期，历史版本按不可变文件保留。
- 成果同时出现在任务的“成果版本”和个人空间的 `/outputs/江擎/` 目录中。
- 网页主导航提供“成果归档”，可以集中预览和下载生成文件。

### 多端使用

- 响应式网页适配桌面和手机浏览器。
- Windows 客户端使用 WebView2 封装工程工作台。
- Android / 可安装 APK 的鸿蒙手机提供独立安装包、定位和麦克风权限接入。
- 客户端连接统一的工程服务，业务数据和模型密钥保留在服务器端。

## 系统结构

```text
网页 / Windows 客户端 / Android 客户端
                 │
          Vue 3 工程工作台
                 │
       FastAPI 业务与智能体服务
          ├─ 工程、任务与确认流程
          ├─ 文档解析、RAG 与 Agent
          ├─ Word 模板与成果归档
          ├─ 天气与实时语音接口
          └─ 权限、审计与运行状态
                 │
 PostgreSQL · Redis · MinIO · Milvus · Neo4j
```

| 层 | 主要技术 |
| --- | --- |
| 前端 | Vue 3、Vite、Ant Design Vue |
| 后端 | FastAPI、LangGraph、ARQ Worker |
| 数据 | PostgreSQL、Redis、MinIO、Milvus、Neo4j |
| 文档 | MinerU、PaddleX、RapidOCR、python-docx |
| 客户端 | WebView2、Android WebView |
| 部署 | Docker Compose、Nginx |

## 快速启动

### 前置条件

- Windows 11、Linux 或兼容的 x86_64 服务器。
- Docker Engine / Docker Desktop 与 Docker Compose。
- 已配置的聊天模型、向量模型和重排模型。
- 天气与实时语音属于可选能力，需要分别配置服务商密钥。

### Windows 开发环境

```powershell
git clone https://github.com/viceleeland/Zhuheng-Agent.git
cd Zhuheng-Agent
Copy-Item .env.template .env
# 按注释填写 .env，不要提交真实密钥
./scripts/start-jiangqing.ps1
```

服务就绪后访问：

- 工程工作台：`http://127.0.0.1:5174/changwei`
- API 就绪检查：`http://127.0.0.1:5051/api/system/ready`

端口和模型配置以本机 `.env` 与 `docker-compose.yml` 为准。

### 常用检查

```powershell
docker compose ps
curl.exe --fail http://127.0.0.1:5051/api/system/ready
```

知识库、OCR、天气和实时语音都依赖各自的服务状态；网页能够打开不代表这些可选能力已经配置完成。

## 客户端

| 目标 | 目录 | 说明 |
| --- | --- | --- |
| Windows | [`clients/windows`](clients/windows) | WebView2 桌面壳与 Inno Setup 安装脚本 |
| Android | [`clients/android`](clients/android) | APK 构建脚本、定位与实时语音桥接 |

安装包体积较小是因为客户端主要负责界面和设备能力，数据库、文档处理、RAG 与模型调用运行在工程服务器上。

## 客户部署与备份

[`deploy/customer`](deploy/customer) 提供 Linux x86_64 客户服务器的容器化交付样例，包括：

- API、Web 和沙盒 provisioner 镜像构建入口。
- PostgreSQL、Redis、MinIO、Milvus 与 Neo4j 的 Compose 编排。
- 首次安装、管理员初始化、定时备份、归档检查和恢复脚本。
- systemd 定时备份服务示例。

该目录目前是交付方案和安全脚本样例。正式交付前仍需在目标服务器完成镜像、模型、域名、HTTPS、备份恢复和容量压力验证，不能把样例文件视为已经通过生产验收的客户镜像。

## 配置与安全

- 真实 `.env`、模型密钥、天气密钥、语音密钥、用户资料、数据库卷和生成成果不得提交到 Git。
- 浏览器和客户端只调用后端接口，不保存云端 API Key。
- AI 生成的日志、月报和审查意见必须经过有权限的人员确认。
- 规范名称、版本、适用范围和条款引用需要由项目专业人员复核。
- 对公网发布时必须启用 HTTPS、强密码、最小权限、访问日志和定期备份。

## 项目状态

当前版本已经完成工程工作台、五类业务任务、资料选择、模块确认、Word 生成、成果归档、天气地名查询、实时语音接口、响应式手机界面以及 Windows / Android 客户端基础链路。

以下能力仍应按真实项目资料继续验证和迭代：

- 扫描件、复杂表格和超长方案的解析准确率。
- 不同客户 Word 模板的像素级版式适配。
- 月报台账的金额单位、报告期与累计口径。
- 现行规范库的完整性、有效性与工程适用性。
- 客户服务器的离线镜像、灾备恢复和长期运行稳定性。

## 文档入口

- [使用与部署说明](JIANGQING.md)
- [系统架构](ARCHITECTURE.md)
- [工程平台设计决定](docs/develop-guides/decisions/implemented/2026-09-19-changwei-platform.md)
- [手机与公网入口](docs/develop-guides/decisions/implemented/2026-09-19-mobile-release-gateway.md)
- [客户镜像交付方案](docs/develop-guides/decisions/proposed/2026-09-19-customer-image-delivery.md)

## 开源来源与许可证

筑衡Agent 基于 Yuxi 扩展，保留原项目的 Git 历史、版权声明和 MIT License。仓库中的第三方组件、模型及容器镜像分别遵循其各自许可证；商业交付或再分发前应按实际使用版本复核许可证义务。

详见 [LICENSE](LICENSE)。
