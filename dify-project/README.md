# AI Murder Mystery

AI Murder Mystery 是一个基于 Web、FastAPI 与 Dify 的多智能体剧本杀项目。当前工作进入 **Phase 7：Game Flow Manager、投票与 Director AI**。Phase 7 在原有确定性 Game Engine 和 Phase 6 Speaker Scheduler 之上增加阶段计时、流程资格与确定性计票，并用独立 Director Workflow 生成受后端校验的建议。

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

## Phase 6：多角色对话编排

Backend 通过确定性的 Speaker Scheduler 按顺序选择公开发言角色；一次公开玩家发言最多触发两个 AI 公开回复。玩家点名多个角色时按名字首次出现顺序选择；未点名时先按 round-robin 选择一名，再可根据其公开发言提及的未回复角色选择第二名。Development only 的主动发言 API 每次只触发一个 AI 角色。所有角色复用同一个 Dify Character Chatflow，后端提供经过权限过滤的 `character_context` 与 `interaction_context`；后者以 `private_reply`、`public_reply` 或 `proactive_public` 指明本次交互模式。Dify 仍返回 Phase 5 的相同结构化输出。

既有 `POST /api/games/{game_id}/ai-chat` 保持单角色私聊的 atomic 语义：只有 AI 回复通过校验后才一起保存玩家与角色消息及角色状态。新增公开回合采用顺序、best-effort 持久化：已成功的公开消息会保留，后续角色调用失败不会回滚前面的成功消息；响应以 `completed` 或 `partial` 及 `failures` 说明结果。主动发言一次只保存并返回一条 `ai_message`。后端的 synthetic trigger 只是调用上下文，不是玩家消息，也不会作为 `Message` 写入数据库。

Phase 6 只负责公开发言角色调度。它与剧情阶段、计时和投票规则分开；这些流程规则由 Phase 7 Game Flow Manager 管理。Phase 7 新增 Director AI，但 Writer AI 仍未实现。

## Phase 7：游戏流程、投票与 Director

Phase 7 将相关职责分开：Game Engine 持有权威游戏事实；`state_machine.py` 定义合法阶段转换图；Game Flow Manager 判定当前动作资格、阶段计时和投票结果；`backend/app/game/speaker_scheduler.py` 中的 Speaker Scheduler 决定对话中的下一位 AI 发言者；Character Agent 推理单个角色；Director 只读取独立构造的 DirectorContext 并给出结构化建议。

V0.1 的阶段最短时长集中定义为 timing policy，按服务端的 `phase_started_at` 计算经过时间和剩余时间。它是可调整的开发默认值，不是生产游戏节奏承诺；服务端计算并验证阶段资格，前端倒计时仅用于显示。每次开始/推进都由后端校验，未到最短时间或投票条件不满足时拒绝推进。没有后台计时任务。

当前 V0.1 默认值为：`intro`、`act_1`、`investigation_1`、`discussion_1`、`act_2`、`investigation_2`、`discussion_2`、`final_discussion` 和 `vote` 均为 10 秒；`ending` 为 0 秒。该表集中在 `backend/app/game/flow_manager.py`，只用于开发连通与规则验证，后续可调。

Director participation 的“长时间未参与”是从最近公开发言时间起达到 120 秒，由后端确定性计算。Director Context 最多包含最近 50 条 public/system 消息，不会用角色 Memory 补足历史。

投票仅在 `in_progress` 且当前 phase 为 `vote` 时接受；每个本局角色最多提交一票，不可投自己。Game Flow Manager 以确定性规则统计票数：唯一最高票者胜出，最高票并列时 `winner_game_character_id` 为 `null` 且 `is_tie` 为 `true`；全体四个角色投票后 `voting_complete` 为真。Phase 7 不自动替 AI 投票。投票 API 为开发调试用途；完整实时票型不应暴露给正式玩家。

Director 通过独立 Dify Workflow 接收序列化后的 `director_context` JSON string，并使用 blocking `/workflows/run` 请求；输出必须符合 `DirectorRecommendation` 枚举与字段契约。Director Context 包含剧本事实、秘密、公开局势、客观线索进度与流程状态；绝不包含 Thought、inner_os、Memory、私聊或角色运行时内部认知。建议经过后端 Action Validator；Director 不能改权威状态、投票或剧本。`no_action`、合法的单角色公开发言请求和阶段推进建议可由后端规则处理；线索提示及公开事实引用先作为 advisory，不自动广播。Director 仅由 Development 调试按钮手动运行，没有自动循环。Writer Phase 尚未实现。配置与输入输出契约见 [Dify Director Workflow 配置](docs/dify-director-workflow.md)。

Phase 7 Finalization 的公开发言资格由 Game Flow Manager 的 `can_public_speak` 统一决定：`intro`、`act_1`、`investigation_1`、`discussion_1`、`act_2`、`investigation_2`、`discussion_2`、`final_discussion` 允许；`vote`、`ending` 不允许。该资格同时用于 `public-turn`、Development `ai-step`、Director 的 AI 发言动作，以及玩家公开消息写入；private chat 继续使用原有规则。

Director recommendation apply 使用条件更新将 `pending` 原子认领为 `applying`，完成后写入 `applied`、`rejected` 或 `advisory`。同一推荐的并发或重复 apply 返回 HTTP `409`，不会再次执行发言或推进阶段。新增 migration `20261007_phase7_atomic_apply` 扩展状态约束；升级现有数据库时，在项目根目录执行 `alembic -c backend/alembic.ini upgrade head`，不要依赖应用启动时的 `create_all` 更新旧表。

## 技术栈

| 部分 | 技术 |
| --- | --- |
| 前端 | React、TypeScript、Vite、原生 CSS |
| 后端 | Python、FastAPI、Pydantic、SQLAlchemy 2.x |
| 数据库 | SQLite |
| AI 平台 | Dify Character Chatflow；另有独立 Director Workflow |

## 目录结构

```text
.
├── backend/
│   ├── app/
│   │   ├── agents/             # Character Agent 与 Dify HTTP client
│   │   ├── api/                # FastAPI 路由
│   │   ├── core/               # 应用配置
│   │   ├── db/                 # Engine、Session、Base、建表
│   │   ├── game/               # 状态转换、流程管理、speaker scheduling 与角色分配
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
│   ├── architecture.md         # 系统边界与信息隔离
│   ├── dify-character-chatflow.md
│   └── dify-director-workflow.md # Director Workflow 输入输出契约
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

请在项目根目录 `dify-project/` 执行。首次创建数据库或升级包含数据库变更的版本时，先按上一节执行 Alembic 迁移；FastAPI 启动时的 `create_all()` 只创建缺失表，不会更新已有表结构。迁移与后端应从同一目录启动，以使用同一个相对路径 SQLite 数据库。

启动时移除不兼容的全局代理变量 `ALL_PROXY` / `all_proxy`，保留已有的 `HTTP_PROXY` / `HTTPS_PROXY`：

```bash
env -u ALL_PROXY -u all_proxy uvicorn app.main:app --app-dir backend --reload
```

接口文档地址：<http://127.0.0.1:8000/docs>。

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

将 `.env.example` 复制为项目根目录的 `.env`。后端通过 Pydantic Settings 读取 `APP_NAME`、`APP_ENV`、`DATABASE_URL`、`DIFY_API_URL`、`DIFY_CHARACTER_API_KEY` 和 `DIFY_DIRECTOR_API_KEY`。Character Chatflow 与 Director Workflow 使用不同的 Dify App Key；Writer 尚未实现，也没有配置项。当前设置兼容读取旧名 `DIFY_API_KEY`；新配置请统一使用 `DIFY_CHARACTER_API_KEY`。迁移旧 `.env` 时，将旧变量改名并删除旧名，避免配置重复。真实密钥只放在本地 `.env`，不要写入代码、文档或 `.env.example`；真实 `.env` 已在 `.gitignore` 中排除。

### Real Dify smoke test

在 Dify 中按 [Chatflow 配置说明](docs/dify-character-chatflow.md)启用 Structured Output 并重新发布后，再使用真实密钥验证。启动 FastAPI 并准备一个状态为 `in_progress` 的游戏和一个 AI 角色，然后运行：

```bash
curl http://127.0.0.1:8000/api/ai/status
curl -X POST http://127.0.0.1:8000/api/games/123/ai-chat -H 'Content-Type: application/json' -d '{"target_game_character_id": 456, "content": "你昨晚在哪里？"}'
```

将示例中的 `123` 和 `456` 替换为正在进行的游戏 ID 与该局 AI 角色 ID。成功时普通响应只有玩家消息和角色 speech；在 Development 页面刷新 **DEBUG ONLY** Inspector，确认 emotion、inner_os、intent 与 memory 已保存，随后再次发送消息并检查角色 Context 中有其自己的记忆。自动测试使用 Mock Dify，不要求真实 API Key。不要把密钥复制到命令历史、终端输出或前端代码中。

Phase 6 真实多角色测试前，先按 [Chatflow 配置说明](docs/dify-character-chatflow.md)为现有 Character Chatflow 增加 `interaction_context` 输入并重新发布。然后选一局 `in_progress` 游戏，使用实际角色姓名点名一位 AI：

```bash
curl -X POST http://127.0.0.1:8000/api/games/123/public-turn -H 'Content-Type: application/json' -d '{"content": "许雁，你昨晚在哪里？"}'
curl -X POST http://127.0.0.1:8000/api/games/123/ai-step
```

检查 `public-turn` 返回中的 `human_message`、最多两条 `ai_responses`、`status` 和 `failures`。玩家直接点名两名 AI 时，两者按出现顺序响应；若只点名一位或没有点名，第一位 AI 的公开发言也可以提及另一位 AI 来触发第二响应。达到上限后停止。模型调用或结构化输出失败会收到脱敏的 `partial` 结果，已成功保存的消息保留；Context 构造或数据库保存失败可能返回 HTTP 500。`ai-step` 仅在 `APP_ENV=development` 开放，每次只产生一条主动公开消息。分别在 Thought / Memory Inspector 中检查发言角色自己的状态，并确认 Bob 的 Context 包含 Alice 已保存的公开发言。真实 smoke test 需要 Chatflow 已发布且其模型供应商有可用配额；自动测试使用 Mock，不会请求真实 Dify。

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
| GET | `/api/games/{game_id}/flow` | 读取阶段计时、动作资格、是否允许推进及安全投票进度 |
| GET | `/api/games/{game_id}/characters/selectable` | 读取可选角色的公开资料 |
| POST | `/api/games/{game_id}/select-character` | 选择真人角色并锁定角色分配 |
| GET | `/api/games/{game_id}/me/character` | 读取本局唯一 human 的公开与本人私密角色卡 |
| GET | `/api/games/{game_id}/characters/{game_character_id}/context` | Development 专用 Context 调试 |
| GET | `/api/games/{game_id}/characters/{game_character_id}/thoughts` | Development 专用 Thought、emotion 与 Memory 调试 |
| GET | `/api/games/{game_id}/public-messages` | 读取公共频道记录，不返回私聊 |
| GET | `/api/ai/status` | 检查 Character Dify 配置是否可用，不返回密钥 |
| GET | `/api/director/status` | Development only：检查独立 Director Workflow 是否配置，不返回密钥 |
| POST | `/api/games/{game_id}/ai-chat` | 真人向本局一个 AI 角色发送私聊并保存完整消息轮次 |
| POST | `/api/games/{game_id}/public-turn` | 提交一条公开玩家消息，顺序请求最多两个 AI 公开回复 |
| POST | `/api/games/{game_id}/ai-step` | Development only：触发一个 AI 角色主动公开发言 |
| POST | `/api/games/{game_id}/start` | 校验角色分配并开始游戏 |
| POST | `/api/games/{game_id}/advance-phase` | 按固定顺序推进一个剧情阶段 |
| POST | `/api/games/{game_id}/votes` | Development only：模拟提交一张正式选票（V0.1 不支持改票） |
| GET | `/api/games/{game_id}/votes/result` | Development 调试用确定性计票结果 |
| POST | `/api/games/{game_id}/director/analyze` | Development only：基于隔离后的 DirectorContext 分析并保存建议 |
| POST | `/api/games/{game_id}/director/recommendations/{recommendation_id}/apply` | Development only：验证并申请执行、拒绝或标记为 advisory |
| GET | `/api/games/{game_id}/investigation/locations` | 读取当前调查阶段的线索地点 |
| POST | `/api/games/{game_id}/investigation/search` | 为本局角色确定性地授予一条新线索 |
| POST | `/api/games/{game_id}/messages` | 创建 public/private 消息；system 消息仅由后端产生 |

当前没有登录认证；`/me/character` 依据 GameSession 中唯一的 `human` 角色返回角色卡，因此不能替代真实用户身份校验。Context、Thought、完整投票结果和 Director 调试 API 仅供开发环境使用。Director Analyze 由开发者手动触发，不会自动推进流程。

#### Phase 6 对话 API 契约

`POST /api/games/{game_id}/public-turn` 请求体为 `{"content": "玩家的公开发言"}`。响应包含玩家公开消息 `human_message`、零到两条成功的 AI 公开消息 `ai_responses`、`status`（`completed` 或 `partial`）和只包含角色 ID / 异常类型的脱敏 `failures`。`partial` 覆盖 CharacterAgent/Dify 调用与 structured-output 校验失败，以及角色回复原子保存失败；Context 构造等未捕获服务错误仍可能返回 HTTP 500。`POST /api/games/{game_id}/ai-step` 仅在 `APP_ENV=development` 可用，响应包含一条主动公开消息 `ai_message`。私聊保持整轮 atomic；公开回合按角色顺序处理并 best-effort 保存成功结果。

#### Phase 7 Flow、Vote 与 Director

`GET /api/games/{game_id}/flow` 返回 `GameFlowState`，包括 `phase_started_at`、服务端计算的 elapsed / remaining 时间、`minimum_time_satisfied`、`can_investigate`、`can_discuss`、`can_vote`、`can_advance`、`is_finished` 与玩家安全的投票进度。V0.1 timing policy 集中维护在后端，属于开发默认值；没有后台计时器。`POST /api/games/{game_id}/advance-phase` 由 Game Flow Manager 检查流程条件，再让 `state_machine.py` 验证唯一合法的下一阶段，客户端不能传任意目标阶段。

`POST /api/games/{game_id}/votes` 请求包含 `voter_game_character_id` 和 `target_game_character_id`。后端校验 vote 阶段、游戏状态、投票双方属于本局、不能自投且每名角色最多一票。`GET /api/games/{game_id}/votes/result` 提供 Development 调试 tally：唯一最高票给出 winner，平票返回 `winner_game_character_id: null` 和 `is_tie: true`。全体四名角色投票后 `voting_complete` 为 true；当前不会自动生成 AI 选票。

Director API 在 `APP_ENV=development` 下可手动使用。Analyze 根据服务端构造的 DirectorContext 调用独立 Dify Workflow 并保存 recommendation；Apply 读取持久化建议，经过 Action Validator，再委托 Speaker Scheduler / Game Flow Manager 或标记为 `advisory`。响应不包含完整 DirectorContext。Director Recommendation 不是命令：Director 无权写入 Vote、修改阶段、凶手、线索或历史消息。请参阅 [Director Workflow 契约和开发流程](docs/dify-director-workflow.md)。

### 测试与构建

在项目根目录执行后端测试：

```bash
cd backend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest
ruff check app tests migrations
ruff format --check app tests migrations
cd ..
alembic -c backend/alembic.ini check
```

在另一个终端执行前端类型检查与构建：

```bash
cd frontend
npm run build
npm run format:check
```

浏览器开发流程使用 Playwright CLI。先启动后端和 Vite，按“加载开发样例”创建一次固定 ready Script，然后在 `frontend/` 运行。Playwright 通过 API 创建测试游戏；这些记录会留在当前配置的本地数据库。Development 页面检查与公共房间的 AI 响应使用 mock，不会调用真实 Dify：

```bash
npm run test:e2e
```

现有 E2E 覆盖 Development 页的 Thought/Memory Inspector、公共房间调试流程，以及 Phase 7 的阶段资格、投票和 Director recommendation/apply 显示；相关 API 由 Playwright mock。后端的实际回合编排和 Director 规则由 pytest 覆盖。Director Workflow 自动测试使用 mock；仓库文档不将其描述为真实 Dify smoke test 成功。只有按 [Director Workflow 配置说明](docs/dify-director-workflow.md)在目标 Dify 环境实际完成请求并通过后端校验，才能确认真实调用。

### Development 流程

1. 先按“加载开发样例”创建固定测试剧本。
2. 在 Development 页创建游戏并选择一个真人角色。
3. 点击 **Start Game**，再用 **Advance Phase** 推进到 `investigation_1`。
4. 选择搜证地点并搜索；新线索只加入当前真人角色的已知线索。
5. 点击“查看授权 Context”或在搜证后查看 JSON，确认 `known_clues` 与当前角色 `memories` 更新。
6. 在 AI Character Chat Debug 中与一个 AI 角色私聊；Inspector 仅供开发调试，普通对话只显示 speech。
7. 在 Multi-Agent Public Room Debug 中选择进行中的游戏，提交 Public Message 并点击 **Send Public Turn**；查看 Human 与 AI 的公共消息以及是否有 partial failure。
8. 点击 **AI Proactive Step** 触发单个角色公开发言；在 Thought / Memory Inspector 选择对应 AI 角色，检查它自己的内心状态与记忆。
9. 在 Game Flow Debug 检查阶段计时与资格；推进到 `vote` 后从 Development Vote Debug 提交并核对确定性 tally。
10. 在 Director Debug 点击 **Analyze Situation** 检查结构化 recommendation，再点击 **Apply Recommendation** 查看 validator 的 applied、rejected 或 advisory 结果。Director Context 中的凶手与秘密不显示给普通玩家区域。

客户端按钮只是开发辅助；开始、阶段推进和搜证权限由后端 Game Engine 再次校验。
