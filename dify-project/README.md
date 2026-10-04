# AI Murder Mystery

AI Murder Mystery 是一个基于 Web、FastAPI 与 Dify 的多智能体剧本杀项目。当前只完成 **Phase 0：工程骨架与基础连通性**，用于确认前端能访问后端健康接口；游戏功能尚未开始实现。

## 技术栈

| 部分 | 技术 |
| --- | --- |
| 前端 | React、TypeScript、Vite、原生 CSS |
| 后端 | Python、FastAPI、Pydantic Settings、SQLAlchemy |
| 数据库 | SQLite（仅连接配置，无业务表） |
| AI 平台 | Dify 配置占位，当前不发起 API 请求 |

## 目录结构

```text
.
├── backend/
│   ├── app/
│   │   ├── agents/
│   │   ├── api/
│   │   ├── core/
│   │   ├── db/
│   │   ├── game/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   └── main.py
│   ├── tests/
│   ├── pyproject.toml
│   └── requirements.txt
├── docs/
│   └── architecture.md
├── frontend/
│   ├── src/
│   ├── package.json
│   └── vite.config.ts
├── .env.example
├── .gitignore
├── README.md
└── TODO.md
```

`backend/app/agents`、`game`、`models`、`schemas` 和 `services` 目前只有职责说明，未包含业务实现或正式数据模型。

## Ubuntu 22.04 开发环境

以下命令均从 `dify-project` 项目根目录运行。需要 Python 3.10 或更新版本、Node.js 20.19+ 或 22.12+，以及 npm。项目不自动创建 Python 环境；如需隔离依赖，可手动创建并激活虚拟环境：

```bash
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

### 启动后端

从项目根目录执行：

```bash
uvicorn app.main:app --app-dir backend --reload
```

健康接口：<http://127.0.0.1:8000/api/health>

API 文档：<http://127.0.0.1:8000/docs>

### 启动前端

在另一个终端，从项目根目录执行：

```bash
cd frontend
npm install
npm run dev
```

打开 Vite 输出的本地地址，默认是 <http://localhost:5173>。

### 配置与本地通信

复制 `.env.example` 为项目根目录的 `.env`。后端通过 Pydantic Settings 读取 `APP_NAME`、`APP_ENV`、`DATABASE_URL`、`DIFY_API_URL` 和 `DIFY_API_KEY`。不要把真实密钥写入 `.env.example`。

前端默认请求相对路径 `/api/health`。`frontend/vite.config.ts` 将开发环境的 `/api` 请求代理到 `VITE_API_PROXY_TARGET`（默认 `http://127.0.0.1:8000`），这样本地前后端同源通信，不需要为开发环境额外配置 CORS。需要指定 API origin 时，可设置 `VITE_API_BASE_URL`；生产部署应在构建时提供该值或配置同源反向代理，不要把生产地址写进代码。

### 测试和构建

在项目根目录执行后端测试：

```bash
cd backend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest
```

在另一个终端执行前端类型检查与构建：

```bash
cd frontend
npm run build
```
