# AI Murder Mystery

AI Murder Mystery 是一个基于 Web、FastAPI 与 Dify 的多智能体剧本杀项目。项目按阶段建设；当前 **Phase 1：核心游戏数据模型与信息边界** 已完成。当前没有 Dify 或 LLM 调用。

## 当前 Phase 1

- 建立 Script、Character、Clue、GameSession、GameCharacter 与 Message 数据模型。
- 提供创建/读取 Script，以及从 ready Script 启动和读取 GameSession 的 API。
- 提供手动、幂等的开发样例 seed，包含四个角色和三条线索。
- 前端开发验证页可以查看 ready Script、创建游戏并查看四个运行角色。
- SQLite 表在 FastAPI 启动时创建；数据库迁移暂未引入。

本阶段暂不引入 Alembic：当前是单人本地开发，数据库表刚建立，没有需要保留并升级的旧业务数据。开始需要在保留用户数据的前提下变更表结构，或进入多人协作/部署前，应加入 Alembic migration；`create_all` 只负责创建缺失表，不会升级已有表。

## 技术栈

| 部分 | 技术 |
| --- | --- |
| 前端 | React、TypeScript、Vite、原生 CSS |
| 后端 | Python、FastAPI、Pydantic、SQLAlchemy 2.x |
| 数据库 | SQLite |
| AI 平台 | Dify 配置占位；当前不发起 API 请求 |

## 目录结构

```text
.
├── backend/
│   ├── app/
│   │   ├── agents/             # 后续 AI 编排与 Dify 集成
│   │   ├── api/                # FastAPI 路由
│   │   ├── core/               # 应用配置
│   │   ├── db/                 # Engine、Session、Base、建表
│   │   ├── game/               # 后续确定性游戏规则
│   │   ├── models/             # SQLAlchemy 持久化模型
│   │   ├── schemas/            # API 请求与响应结构
│   │   ├── services/           # 应用服务与开发 seed
│   │   ├── main.py             # FastAPI 应用入口
│   │   └── seed.py             # 开发数据命令入口
│   ├── tests/                  # 后端 API 与数据模型测试
│   ├── pyproject.toml          # 后端依赖、pytest 与 Ruff 配置
│   └── requirements.txt        # 兼容入口，依赖版本以 pyproject.toml 为准
├── docs/
│   └── architecture.md         # 系统边界与信息隔离
├── frontend/
│   ├── src/                    # React 页面、API 客户端与样式
│   ├── package.json
│   └── vite.config.ts          # /api 开发代理
├── .env.example
├── .gitignore
├── README.md
└── TODO.md
```

## Ubuntu 22.04 开发环境

以下命令从 `dify-project` 根目录运行。需要 Python 3.10 或更新版本、Node.js 20.19+ 或 22.12+，以及 npm。项目不自动创建 Python 环境；如需隔离依赖，可手动创建并激活：

```bash
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
cd backend
pip install -r requirements.txt
cd ..
```

后端依赖版本集中维护在 `backend/pyproject.toml`：运行依赖列在 `[project].dependencies`，测试与格式工具列在 `[project.optional-dependencies].dev`。`backend/requirements.txt` 只是便于 pip 安装的兼容入口，不再单独维护版本号。

### 启动后端

```bash
uvicorn app.main:app --app-dir backend --reload
```

SQLite 表会在后端启动时创建。接口文档地址：<http://127.0.0.1:8000/docs>。

### 加载开发样例

另开终端，在项目根目录运行（保持与后端相同的工作目录，使默认 SQLite 文件一致）：

```bash
PYTHONPATH=backend python -m app.seed
```

该命令可重复运行；若固定样例已存在，不会重复创建。它不会在每次应用启动时执行。

### 启动前端

另开终端，在项目根目录运行：

```bash
cd frontend
npm install
npm run dev
```

打开 Vite 输出的本地地址，默认是 <http://localhost:5173>。首页“载入剧本”进入 Phase 1 开发验证页。

### 配置与本地通信

将 `.env.example` 复制为项目根目录的 `.env`。后端通过 Pydantic Settings 读取 `APP_NAME`、`APP_ENV`、`DATABASE_URL`、`DIFY_API_URL` 和 `DIFY_API_KEY`。当前不需要真实 Dify 密钥；真实 `.env` 已在 `.gitignore` 中排除。

前端默认请求相对路径 `/api/...`。`frontend/vite.config.ts` 将开发环境的 `/api` 请求代理到 `VITE_API_PROXY_TARGET`（默认 `http://127.0.0.1:8000`），因此本地开发不需要额外 CORS 配置。需要指定 API origin 时，可设置 `VITE_API_BASE_URL`；不要把生产地址写进代码。

## API

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/health` | 检查后端连通性 |
| POST | `/api/scripts` | 创建 draft Script |
| GET | `/api/scripts` | 列出 Script 元数据 |
| GET | `/api/scripts/{script_id}` | 读取 Script 元数据 |
| POST | `/api/games` | 基于 ready Script 创建一局游戏 |
| GET | `/api/games/{game_id}` | 读取游戏基本状态和四个运行角色 |

### 测试与构建

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
