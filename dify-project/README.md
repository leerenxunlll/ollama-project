# AI Murder Mystery

AI Murder Mystery 是一个基于 Web、FastAPI 与 Dify 的多智能体剧本杀项目。项目按阶段建设；当前 **Phase 3：Game Engine、游戏状态机与确定性搜证规则** 已完成。当前没有 Dify 或 LLM 调用。

## 当前 Phase 3

- 在角色选择完成后由 Game Engine 校验并开始游戏，按固定顺序手动推进剧情阶段。
- 仅在 `investigation_1` / `investigation_2` 阶段允许搜证，分别匹配 `act_1` / `act_2` 线索。
- 搜证按 importance 降序、Clue ID 升序稳定选择；线索只授予实际搜证的 GameCharacter。
- Context Builder 只读 `GameCharacterClue`，下次构造角色 Context 时自动包含已获得线索。
- 新增 public/private 消息写入 API；system 消息由后端在开始、推进和结束时记录。
- 前端 Development / Debug 页面可以选择角色、开始游戏、推进阶段、搜证并查看 Context JSON。
- 当前没有 AI、Dify、WebSocket、登录、投票或正式游戏界面。

Phase 3 增加 `finished` 生命周期状态，并将旧的 `introduction` 初始阶段迁移为 `intro`。升级已有数据库前先执行 Alembic migration；迁移保留旧 `completed` 状态及其他业务记录。`create_all` 仍只创建缺失表，不会升级旧表。

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
│   │   ├── game/               # 确定性规则与角色分配
│   │   ├── models/             # SQLAlchemy 持久化模型
│   │   ├── schemas/            # API 与角色 Context 结构
│   │   ├── services/           # Context Builder 与开发 seed
│   │   ├── main.py             # FastAPI 应用入口
│   │   └── seed.py             # 开发数据命令入口
│   ├── migrations/             # Alembic 数据库迁移
│   ├── alembic.ini             # Alembic 配置
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

### 数据库迁移

首次启动或升级 Phase 1 数据库前，在项目根目录执行：

```bash
alembic -c backend/alembic.ini upgrade head
```

迁移连接使用 `.env` 中的 `DATABASE_URL`。如果 Alembic 尚未安装，重新执行 `cd backend && pip install -r requirements.txt`。

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

打开 Vite 输出的本地地址，默认是 <http://localhost:5173>。首页“载入剧本”进入 Phase 2 Development / Debug 页面。

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
| GET | `/api/games` | 列出 GameSession，供开发页选择 |
| GET | `/api/games/{game_id}` | 读取游戏基本状态和四个运行角色 |
| GET | `/api/games/{game_id}/state` | 读取安全的生命周期、当前阶段、下一阶段与搜证资格 |
| GET | `/api/games/{game_id}/characters/selectable` | 读取可选角色的公开资料 |
| POST | `/api/games/{game_id}/select-character` | 选择真人角色并锁定角色分配 |
| GET | `/api/games/{game_id}/me/character` | 读取本局唯一 human 的公开与本人私密角色卡 |
| GET | `/api/games/{game_id}/characters/{game_character_id}/context` | Development 专用 Context 调试 |
| POST | `/api/games/{game_id}/start` | 校验角色分配并开始游戏 |
| POST | `/api/games/{game_id}/advance-phase` | 按固定顺序推进一个剧情阶段 |
| GET | `/api/games/{game_id}/investigation/locations` | 读取当前调查阶段的线索地点 |
| POST | `/api/games/{game_id}/investigation/search` | 为本局角色确定性地授予一条新线索 |
| POST | `/api/games/{game_id}/messages` | 创建 public/private 消息；system 消息仅由后端产生 |

当前没有登录认证；`/me/character` 依据 GameSession 中唯一的 `human` 角色返回角色卡，因此不能替代真实用户身份校验。Context 调试 API 只在 `APP_ENV=development` 时可用。Development 页面中的游戏推进由开发者手动触发，没有 Director 自动推进。

### 测试与构建

在项目根目录执行后端测试：

```bash
cd backend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest
ruff check app tests migrations
ruff format --check app tests migrations
```

在另一个终端执行前端类型检查与构建：

```bash
cd frontend
npm run build
```

### Phase 3 Development 流程

1. 先按“加载开发样例”创建固定测试剧本。
2. 在 Development 页创建游戏并选择一个真人角色。
3. 点击 **Start Game**，再用 **Advance Phase** 推进到 `investigation_1`。
4. 选择搜证地点并搜索；新线索只加入当前真人角色的已知线索。
5. 点击“查看授权 Context”或在搜证后查看 JSON，确认 `known_clues` 更新。

客户端按钮只是开发辅助；开始、阶段推进和搜证权限由后端 Game Engine 再次校验。
