# Bug Shoot

[English](README.md) | [简体中文](README.zh-CN.md)

Bug Shoot 是一个面向个人和小团队的自托管 API 调试、接口测试与可视化链路测试平台。它结合了类似 Postman 的接口调试、轻量链路测试，以及可以根据自然语言生成 API 链路草稿的 Agent。

> 当前状态：早期开源版本，适合本地或小团队自托管使用。生产部署前请先阅读安全说明。

## 功能亮点

- 支持 HTTP、WebSocket、RPC 风格请求调试
- 接口管理：分组、环境、cURL 导入、Postman Collection 导入
- 环境变量：支持 `{{env.key}}` 运行时替换
- JSONPath 断言和脚本断言
- 可视化链路测试：接口节点、脚本节点、等待节点、条件节点
- 链路执行历史和节点级响应详情
- Agent 根据自然语言目标生成链路草稿
- 模型驱动的步骤规划、接口匹配、响应采样和参数依赖规划
- 项目空间和基础团队成员协作
- Docker Compose 一键部署

## 截图

截图暂未提交。建议后续补充：

- `docs/images/api-debug.png`
- `docs/images/chain-test.png`
- `docs/images/agent-planner.png`
- `docs/images/run-report.png`

## 技术栈

| 层级 | 技术 |
| --- | --- |
| 前端 | Vue 3、Vite、Pinia、Vue Router、Ant Design Vue、Vue Flow |
| 后端 | Django、Django REST Framework、SimpleJWT、Gunicorn |
| 数据库 | PostgreSQL |
| Agent 模型 | OpenAI-Compatible API 或本地 Ollama |
| 部署 | Docker Compose、Nginx |

## 快速启动

需要安装：

- Docker
- Docker Compose v2

启动：

```bash
git clone <your-repo-url> bug-shoot
cd bug-shoot
cp .env.example .env
docker compose up --build -d
```

访问：

- 前端：http://localhost
- 后端 API：http://localhost:8000/api/

本地默认账号：

| 用户名 | 密码 |
| --- | --- |
| `admin` | `admin123` |

首次启动会自动执行数据库迁移，并初始化演示数据：默认项目、本地环境、示例接口和示例链路。

## 启动自检

服务启动后运行：

```bash
sh scripts/self_check.sh
```

自检脚本会检查前端访问、后端登录和项目列表接口。

## Agent 配置

Bug Shoot 支持两种 Agent 模型提供方式：

1. OpenAI 或 OpenAI-Compatible API
2. Docker Compose 内置的 Ollama 兜底服务

如果你要使用 OpenAI 或其他 OpenAI-Compatible 模型，只需要修改项目根目录下的 `.env` 文件，不需要修改 `Dockerfile`、`docker-compose.yml` 或后端代码。

```bash
cp .env.example .env
```

然后在 `.env` 中配置：

```env
AGENT_OPENAI_BASE_URL=https://api.openai.com/v1
AGENT_OPENAI_API_KEY=sk-your-key
AGENT_OPENAI_MODEL=gpt-4.1-mini
```

如果使用其他兼容 OpenAI API 格式的模型服务，也使用这三个变量，只需要替换 base URL 和模型名。

配置生效：

```bash
docker compose up -d backend
```

当下面三个配置都存在时，系统会优先使用 OpenAI-Compatible 模式：

```env
AGENT_OPENAI_BASE_URL=https://your-provider.example/v1
AGENT_OPENAI_API_KEY=your-key
AGENT_OPENAI_MODEL=your-model
```

如果这三个值为空，Docker Compose 会启动 Ollama，并自动拉取：

```env
AGENT_OLLAMA_MODEL=qwen2.5:7b
```

也就是说，本地体验时不需要提前安装 Ollama；模型会保存在 Docker volume `ollama_data` 中。

Agent 编排流程：

```text
自然语言目标
→ 步骤规划
→ 接口候选召回
→ 接口匹配
→ 响应采样
→ 参数依赖规划
→ 生成链路草稿
```

Agent 页面会展示每个模型阶段的状态、模型来源、规划摘要和 JSON 明细，方便排查和人工确认。

## 常用命令

```bash
# 查看服务状态
docker compose ps

# 查看日志
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f ollama

# 重建单个服务
docker compose up --build -d backend
docker compose up --build -d frontend

# 停止服务
docker compose down

# 清空本地数据并重置
docker compose down -v
```

## 配置说明

复制 `.env.example` 为 `.env` 后即可调整配置。

| 变量 | 说明 | 本地默认值 |
| --- | --- | --- |
| `FRONTEND_PORT` | 前端暴露端口 | `80` |
| `BACKEND_PORT` | 后端 API 暴露端口 | `8000` |
| `DB_NAME` | PostgreSQL 数据库名 | `bugshoot` |
| `DB_USER` | PostgreSQL 用户名 | `postgres` |
| `DB_PASSWORD` | PostgreSQL 密码 | `postgres` |
| `SECRET_KEY` | Django 密钥 | 本地演示值 |
| `DEBUG` | Django 调试模式 | `True` |
| `ALLOWED_HOSTS` | Django 允许访问的 Host | `*` |
| `CORS_ALLOW_ALL_ORIGINS` | 是否允许所有跨域来源 | `True` |
| `DJANGO_SUPERUSER_USERNAME` | 初始化管理员用户名 | `admin` |
| `DJANGO_SUPERUSER_PASSWORD` | 初始化管理员密码 | `admin123` |
| `LOAD_SAMPLE_DATA` | 是否初始化演示数据 | `True` |
| `AGENT_OPENAI_BASE_URL` | OpenAI-Compatible Base URL | 空 |
| `AGENT_OPENAI_API_KEY` | OpenAI-Compatible API Key | 空 |
| `AGENT_OPENAI_MODEL` | OpenAI-Compatible 模型名 | 空 |
| `AGENT_OLLAMA_MODEL` | Ollama 兜底模型 | `qwen2.5:7b` |

## 常见问题

Agent 不可用：

- 查看 Ollama 日志：`docker compose logs -f ollama`
- 首次启动 Ollama 需要拉模型，可能较慢
- 如果使用 OpenAI-Compatible 模式，检查 `AGENT_OPENAI_BASE_URL`、`AGENT_OPENAI_API_KEY`、`AGENT_OPENAI_MODEL`

后端启动失败：

- 查看后端日志：`docker compose logs -f backend`
- 确认数据库健康：`docker compose ps db`
- 如果本地数据可以丢弃，可执行 `docker compose down -v` 后重新启动

端口冲突：

- 修改 `.env` 中的 `FRONTEND_PORT`、`BACKEND_PORT`、`DB_PORT` 或 `OLLAMA_PORT`

默认账号登录失败：

- 确认 `LOAD_SAMPLE_DATA=True`
- 查看后端日志中是否成功初始化管理员账号
- 如果首次启动后又修改了 `.env`，旧数据库数据不会自动重置，需要执行 `docker compose down -v`

## 安全说明

默认配置只适合本地演示，不适合生产环境。暴露到团队或公网前至少需要：

- 修改 `SECRET_KEY`、`DB_PASSWORD`、`DJANGO_SUPERUSER_PASSWORD`
- 设置 `DEBUG=False`
- 配置明确的 `ALLOWED_HOSTS`
- 设置 `CORS_ALLOW_ALL_ORIGINS=False`
- 使用 HTTPS
- 不要公开暴露 PostgreSQL 或 Ollama 端口
- 定期备份 PostgreSQL volume

更多安全建议见 [SECURITY.md](SECURITY.md)。

认证 token、密码字段，以及 key 中包含 `token`、`secret`、`password`、`api_key`、`authorization`、`cookie`、`session` 等敏感含义的环境变量，会在 API 响应中脱敏展示。即便如此，也不建议在不可信环境中导入生产密钥。

## 本地开发

后端：

```bash
cd backend
pip install -r requirements.txt
python manage.py migrate
python scripts/init_data.py
python manage.py runserver 0.0.0.0:8000
```

前端：

```bash
cd frontend
npm install
npm run dev
```

前端开发服务默认访问：http://localhost:3000

## 测试

```bash
# 后端测试
docker compose exec backend python manage.py test

# 前端测试 / 构建
docker compose exec frontend npm test
docker compose exec frontend npm run build
```

## Roadmap

近期计划：

- OpenAPI / Swagger 导入
- Agent 结果确认编辑
- 可导出的链路执行报告
- 电商、ERP、金融、CRM、工单等更多演示模板
- 后端测试和前端构建 CI

后续计划：

- Mock Server
- 定时链路运行和通知
- CI CLI Runner
- 审计日志
- 版本历史和回滚
- 更细粒度的项目权限

## 贡献

欢迎提交 Issue 和 Pull Request。请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。

提交 PR 时建议包含：

- 改了什么
- 为什么改
- 如何验证
- UI 变更截图

## License

MIT License，见 [LICENSE](LICENSE)。
