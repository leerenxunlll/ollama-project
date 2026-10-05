# AI Murder Mystery

AI Murder Mystery 是一个基于 Web、FastAPI 与 Dify 的多智能体剧本杀项目。项目按阶段建设；当前处于 **Phase 5：结构化角色回复、内心状态与最小长期记忆**。本阶段仍只支持真人与单个 AI 角色私聊，不启用多 Agent 协作或 AI 主动发言。

## Phase 3 已完成

- 在角色选择完成后由 Game Engine 校验并开始游戏，按固定顺序手动推进剧情阶段。
- 仅在 `investigation_1` / `investigation_2` 阶段允许搜证，分别匹配 `act_1` / `act_2` 线索。
- 搜证按 importance 降序、Clue ID 升序稳定选择；线索只授予实际搜证的 GameCharacter。
- Context Builder 只读 `GameCharacterClue`，下次构造角色 Context 时自动包含已获得线索。
- 新增 public/private 消息写入 API；system 消息由后端在开始、推进和结束时记录。
- 前端 Development / Debug 页面可以选择角色、开始游戏、推进阶段、搜证并查看 Context JSON。
- Phase 3 本身不包含 AI、Dify 或 WebSocket。

Phase 3 增加 `finished` 生命周期状态，并将旧的 `introduction` 初始阶段迁移为 `intro`。升级已有数据库前先执行 Alembic migration；迁移保留旧 `completed` 状态及其他业务记录。`create_all` 仍只创建缺失表，不会升级旧表。

## Phase 4 已完成

Phase 4 建立的 AI 调用链为：

```text
Human Player → FastAPI Game Service → CharacterContextBuilder → CharacterAgent → DifyClient → Dify Chatflow
```

仅开放 `GET /api/ai/status` 配置检查和 `POST /api/games/{game_id}/ai-chat` 单角色私聊。请求只允许真人向同一局中指定的 AI 角色发送 private message。Character Agent 接收经过 Context Builder 权限过滤的 `CharacterContext` 与本轮玩家消息，不接触数据库 Session 或 ORM。

Dify 只生成角色台词，不持有权威游戏状态或长期对话记忆。每轮调用以数据库中的授权消息和角色 Context 为依据；后端只在 Dify 返回有效台词后将玩家消息与 AI 回复作为一轮一起持久化。Dify 调用失败时不会留下半轮消息。未配置 Dify 时后端仍可启动，只有 AI 请求不可用。Chatflow 输入和 System Instruction 见 [Dify Character Chatflow 配置](docs/dify-character-chatflow.md)。

Development / Debug 页面提供 AI Character Chat Debug，可查看配置状态、选择进行中的游戏和 AI 角色、发送一条私聊并查看玩家消息与角色回复。接口使用 `404` 表示游戏或目标不存在，`409` 表示游戏状态/角色不符合调用条件，`503` 表示 Dify 未配置，`504` 表示 Dify 超时，`502` 表示 Dify 连接、代理配置、认证、上游请求、响应或结构化输出校验错误。

## Phase 5 范围

Character Chatflow 现在需要返回经过校验的结构化输出：`speech`、`inner_os`、有限枚举 `emotion`、描述性 `intent` 和最多两条 `memory_updates`。后端只把 `speech` 返回给普通聊天界面；其余数据分别保存到 `CharacterThought` 和 `CharacterMemory`，并在同一数据库事务里保存 Human Message、AI Message 和 `GameCharacter.current_emotion`。`current_goal` 不由模型修改。

```text
Human Player → FastAPI → CharacterContextBuilder → CharacterAgent → Dify
                    └─ validate → one database transaction → Message / Thought / Memory / emotion
```

每个 AI Character Context 只包含自己的 Memory，最多 20 条，按 importance、时间和 ID 倒序取值。历史消息分别限制为最近 20 条 public/system 与最近 20 条该角色相关 private 消息，并按时间正序提供。历史 Thought 不自动进入 Context。Memory 是角色主观认知，不是案件事实；AI 输出不能改游戏阶段、凶手身份、剧本真相或正式线索。

新增的 `GET /api/games/{game_id}/characters/{game_character_id}/thoughts` 仅在 `APP_ENV=development` 开放，用于开发页的 **DEBUG ONLY** Inspector。普通消息、游戏状态和 AI Chat 响应不包含 `inner_os` 或 `memory_updates`。Chatflow JSON 契约及 System Instruction 见 [Dify Character Chatflow 配置](docs/dify-character-chatflow.md)。

Phase 5 增加 Alembic migration `20261005_phase5`。升级现有数据库前先执行 `alembic -c backend/alembic.ini upgrade head`；不能依赖启动时的 `create_all` 更新旧表。

## 技术栈

| 部分 | 技术 |
| --- | --- |
| 前端 | React、TypeScript、Vite、原生 CSS |
| 后端 | Python、FastAPI、Pydantic、SQLAlchemy 2.x |
| 数据库 | SQLite |
| AI 平台 | Dify Chatflow；当前用于真人与单 AI 角色私聊 |

## 目录结构

```text
.
├── backend/
│   ├── app/
│   │   ├── agents/             # Character Agent 与 Dify HTTP client
│   │   ├── api/                # FastAPI 路由
│   │   ├── core/               # 应用配置
│   │   ├── db/                 # Engine、Session、Base、建表
│   │   ├── game/               # 确定性规则与角色分配
│   │   ├── models/             # SQLAlchemy 持久化模型
│   │   ├── schemas/            # API 与角色 Context 结构
│   │   ├── services/           # Character Context / chat service 与开发 seed
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

首次启动或升级已有数据库时，在项目根目录执行：

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

将 `.env.example` 复制为项目根目录的 `.env`。后端通过 Pydantic Settings 读取 `APP_NAME`、`APP_ENV`、`DATABASE_URL`、`DIFY_API_URL` 和 `DIFY_CHARACTER_API_KEY`。本阶段只使用 Character Dify App 的 Key；未来 Character、Director、Writer 应各自使用不同的 API Key。当前设置兼容读取旧名 `DIFY_API_KEY`；新配置请统一使用 `DIFY_CHARACTER_API_KEY`。迁移旧 `.env` 时，将旧变量改名并删除旧名，避免配置重复。真实密钥只放在本地 `.env`，不要写入代码、文档或 `.env.example`；真实 `.env` 已在 `.gitignore` 中排除。

### Real Dify smoke test

在 Dify 中按 [Chatflow 配置说明](docs/dify-character-chatflow.md)启用 Structured Output 并重新发布后，再使用真实密钥验证。启动 FastAPI 并准备一个状态为 `in_progress` 的游戏和一个 AI 角色，然后运行：

```bash
curl http://127.0.0.1:8000/api/ai/status
curl -X POST http://127.0.0.1:8000/api/games/123/ai-chat -H 'Content-Type: application/json' -d '{"target_game_character_id": 456, "content": "你昨晚在哪里？"}'
```

将示例中的 `123` 和 `456` 替换为正在进行的游戏 ID 与该局 AI 角色 ID。成功时普通响应只有玩家消息和角色 speech；在 Development 页面刷新 **DEBUG ONLY** Inspector，确认 emotion、inner_os、intent 与 memory 已保存，随后再次发送消息并检查角色 Context 中有其自己的记忆。自动测试使用 Mock Dify，不要求真实 API Key。不要把密钥复制到命令历史、终端输出或前端代码中。

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
| GET | `/api/games/{game_id}/characters/{game_character_id}/thoughts` | Development 专用 Thought、emotion 与 Memory 调试 |
| GET | `/api/ai/status` | 检查 Character Dify 配置是否可用，不返回密钥 |
| POST | `/api/games/{game_id}/ai-chat` | 真人向本局一个 AI 角色发送私聊并保存完整消息轮次 |
| POST | `/api/games/{game_id}/start` | 校验角色分配并开始游戏 |
| POST | `/api/games/{game_id}/advance-phase` | 按固定顺序推进一个剧情阶段 |
| GET | `/api/games/{game_id}/investigation/locations` | 读取当前调查阶段的线索地点 |
| POST | `/api/games/{game_id}/investigation/search` | 为本局角色确定性地授予一条新线索 |
| POST | `/api/games/{game_id}/messages` | 创建 public/private 消息；system 消息仅由后端产生 |

当前没有登录认证；`/me/character` 依据 GameSession 中唯一的 `human` 角色返回角色卡，因此不能替代真实用户身份校验。Context 和 Thought 调试 API 只在 `APP_ENV=development` 时可用。Development 页面中的游戏推进由开发者手动触发，没有 Director 自动推进。

### 测试与构建

在项目根目录执行后端测试：

```bash
cd backend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest
ruff check app tests migrations
ruff format --check app tests migrations
alembic -c alembic.ini check
```

在另一个终端执行前端类型检查与构建：

```bash
cd frontend
npm run build
npm run format:check
```

浏览器开发流程使用 Playwright CLI。先启动后端和 Vite，按“加载开发样例”创建一次固定 ready Script，然后在 `frontend/` 运行：

```bash
npm run test:e2e
```

测试会通过 API 创建临时游戏，再用浏览器打开 Development 页并读取空的 AI Character Inspector；它不会调用真实 Dify。

### Development 流程

1. 先按“加载开发样例”创建固定测试剧本。
2. 在 Development 页创建游戏并选择一个真人角色。
3. 点击 **Start Game**，再用 **Advance Phase** 推进到 `investigation_1`。
4. 选择搜证地点并搜索；新线索只加入当前真人角色的已知线索。
5. 点击“查看授权 Context”或在搜证后查看 JSON，确认 `known_clues` 与当前角色 `memories` 更新。
6. 在 AI Character Chat Debug 中与一个 AI 角色交谈；Inspector 仅供开发调试，普通对话只显示 speech。

客户端按钮只是开发辅助；开始、阶段推进和搜证权限由后端 Game Engine 再次校验。
