# 架构说明

## 当前系统边界

```mermaid
flowchart LR
    Frontend[前端<br/>React + TypeScript]
    Backend[FastAPI 后端<br/>HTTP API 与配置]
    Engine[游戏引擎<br/>确定性规则]
    Agents[Agent 层<br/>AI 推理与生成]
    Dify[Dify<br/>AI 工作流平台]
    Database[(SQLite<br/>数据持久化)]

    Frontend -->|HTTP| Backend
    Backend --> Engine
    Backend --> Agents
    Engine -->|确定性规则与状态变更| Database
    Backend -->|读写持久化数据| Database
    Agents -->|角色对话推理与生成| Dify
```

Phase 3 建立了固定剧情阶段、确定性游戏开始/推进、角色搜证与 public/private 消息 API。Phase 4 在此基础上增加一个同步的真人到 AI 角色私聊闭环；不改变 Game Engine 的确定性规则和既有信息边界。

## 职责边界

- **Frontend** 展示 Web 界面并调用后端 API，不持有游戏规则或持久化状态。
- **FastAPI Backend** 提供 HTTP 接口，连接前端与服务端各层。
- **Game Engine** 负责确定性游戏规则，是唯一可以校验并应用核心游戏状态变更的层。
- **Game Engine** 负责校验角色选择状态，并锁定一个 human 与三个 ai 的确定性分配。
- **Agent Layer** 负责 AI 推理与生成。Phase 4 的 Character Agent 只生成角色台词；AI 不允许直接修改核心游戏状态。
- **Database** 使用 SQLite 持久化脚本模板与游戏运行数据。SQLAlchemy 模型表达真相；Alembic 负责后续表结构迁移，`create_all` 只创建缺失表。
- **Dify** 由后端 Dify Client 调用，执行 Character Chatflow 并返回生成台词。Dify 不拥有权威游戏状态。

## Deterministic Game Engine

Game Engine owns deterministic game truth. Phase 3 的规则位于 `backend/app/game/state_machine.py`，数据库操作位于 `backend/app/services/gameplay.py`：

```mermaid
flowchart LR
    Client[Development UI / API client] -->|action request| API[FastAPI route]
    API --> Service[Gameplay service]
    Service -->|validate| Engine[Deterministic Game Engine]
    Engine -->|valid action| Service
    Service -->|state and event update| DB[(SQLite)]
    FutureAI[Future AI / Director] -.->|recommend action only| API
```

流程是：Game Engine 校验动作，Gameplay Service 应用通过校验的权威状态变更，并在同一提交中记录公开 system event。API route 只负责 HTTP 请求/响应映射。未来的 AI 或 Director 只能提出动作建议；后端规则通过校验后才可应用，AI 不直接写入核心游戏状态。

Phase 3 使用固定阶段顺序，不接受客户端提交任意目标阶段。搜证资格由后端依据游戏状态和当前阶段判定；线索从当前 Script 的对应 Act 与地点中稳定选取，并只写入执行搜证的 `GameCharacterClue`。`random_seed` 保留在 GameSession 中，但目前不影响状态推进或线索选择。

## Game Lifecycle vs Narrative Phase

`GameSession.status` 表示整局游戏生命周期：

- `waiting_for_character_selection`：等待真人选择角色。
- `ready`：一个 human 与三个 ai 已分配，可以开始。
- `in_progress`：游戏已开始，剧情阶段正在推进。
- `finished`：进入 `ending` 阶段后游戏结束。

旧值 `completed` 与 `abandoned` 暂时保留用于兼容已有数据；Phase 3 新结束流程使用 `finished`。

`GameSession.current_phase` 表示剧情阶段。开始时设为 `intro`，之后仅按以下顺序推进：

```mermaid
stateDiagram-v2
    [*] --> intro
    intro --> act_1
    act_1 --> investigation_1
    investigation_1 --> discussion_1
    discussion_1 --> act_2
    act_2 --> investigation_2
    investigation_2 --> discussion_2
    discussion_2 --> final_discussion
    final_discussion --> vote
    vote --> ending
    ending --> [*]
```

进入 `ending` 的同一次推进会同时把 `status` 设为 `finished` 并记录 `ended_at`。`finished` 游戏不再允许推进或搜证。只有 `investigation_1`（线索 `act_1`）和 `investigation_2`（线索 `act_2`）允许搜证。

阶段开始、阶段推进与游戏结束由后端写入固定文案的 system Message；普通消息 API 只能创建 public/private 消息，system 事件不接受客户端输入。

## Information Boundary

游戏信息按可见范围区分：

| 信息范围 | 当前数据示例 | 预期接收者 |
| --- | --- | --- |
| Public Information | Script 的公开元数据、Character 的 `public_background`、已公开线索、公共消息 | 玩家与所有角色 |
| Private Character Information | Character 的 `private_background`、个人目标、私聊消息及接收对象 | 对应角色或明确获准的接收者 |
| God/Director Information | `is_killer`、完整案件真相及全局裁定事实 | Game Engine 与 Director；普通角色不接收完整内容 |

当前基础 API 的 `GET /api/scripts` 和 `GET /api/scripts/{script_id}` 只返回 Script 元数据；`GET /api/games/{game_id}` 只返回运行状态、角色姓名和控制类型，不返回角色私密背景、凶手标记、角色运行目标或随机种子。数据库模型中存在更完整的数据，不代表这些字段可以默认向浏览器或角色开放。

普通 Character Agent 不应接收到完整 Script 真相。权限隔离由后端过滤并构造 Context 实现，而不是依靠 Prompt 要求模型保密。

本阶段没有定义完整案件真相的数据格式，因此没有额外加入 truth JSON 字段。等剧本真相的稳定结构确定后，再决定是否使用单个 JSON 字段或独立模型。

## AI Integration Boundary

Phase 4 的单角色私聊链路为：

```mermaid
flowchart LR
    Player[Human Player] -->|ai-chat request| API[FastAPI API]
    API --> Service[Character Chat Service]
    Service --> Builder[CharacterContextBuilder]
    Builder -->|validated CharacterContext| Agent[CharacterAgent]
    Agent -->|safe context and current query| Client[DifyClient]
    Client -->|blocking chat-messages request| Dify[Dify Chatflow]
    Dify -->|speech| Client
    Client --> Agent
    Agent --> Service
    Service -->|persist both private messages after success| DB[(SQLite)]
```

`CharacterContextBuilder` 是唯一负责角色信息过滤的组件。CharacterAgent 接收经过 Pydantic 验证的 `CharacterContext` 和本轮玩家输入，不持有数据库 Session，不访问 ORM；DifyClient 只负责 HTTP、认证、超时和响应解析，不包含剧本或游戏规则。Dify 请求使用 `DIFY_API_URL` 与 `DIFY_CHARACTER_API_KEY`，配置状态由 `GET /api/ai/status` 提供；该接口只返回是否已配置，不返回密钥。`POST /api/games/{game_id}/ai-chat` 只支持玩家向同局一个 AI 角色私聊。

对话历史仍以 SQLite 中的 `Message` 为准。每次请求均使用新 Dify conversation（`conversation_id` 为空），不把 Dify conversation 当作游戏记忆或权威对话记录。CharacterContext 只包含该目标角色获准看到的消息与已知线索；当前玩家消息单独作为本轮 query 发送。

消息事务顺序是：校验游戏与目标角色、构造安全 Context、调用 Dify、验证非空台词，最后在同一数据库事务中写入 Human 与 AI 两条 private Message。Dify 失败或返回无效台词时，两条消息都不写入；数据库写入失败时事务回滚，不留下半轮消息。AI 回复仅是消息文本，不会被当成阶段变化、线索授予或其他游戏状态命令。

Chatflow 的 System Instruction 用于维持角色行为，例如语气、目标和是否隐瞒角色已知秘密；它不是信息安全措施。信息安全来自 Context Builder 限制实际发送的数据，不能靠提示词要求模型保密。不得把 API Key、完整角色 Context 或角色秘密写入日志。

## Character Context Pipeline

```mermaid
flowchart LR
    Database[(SQLAlchemy Models / SQLite)] --> Filter[Backend Permission Filtering]
    Filter --> Builder[Character Context Builder]
    Builder --> Context[Character Context Schema]
    Context --> Agent[CharacterAgent]
    Agent --> Dify[Dify Chatflow]
```

- Context Builder 位于 `backend/app/services/character_context.py`，只接收指定 `game_id` 和 `game_character_id`；Phase 4 CharacterAgent 仅使用这一安全 Context 与当前玩家消息生成角色台词。
- Builder 先确认运行角色属于该局，再构造明确的 Pydantic `CharacterContext`；它不会把 ORM 对象交给 Agent。
- 当前角色可获得自己的私密背景、目标和运行状态；其他角色只含姓名、身份与公开背景。
- 公共消息和 system 消息进入公共事件流；private 消息只在当前角色是发送者或接收者，且双方都属于该局时出现。
- system 消息目前没有公开/私有子类型，因此本阶段约定所有 system 消息均为公开旁白。后续 Director 私有消息必须先扩展信息类型后才能保存，不能混入当前 system 流。
- `known_clues` 仅读取 `GameCharacterClue` 中授予当前角色的线索，并校验线索仍属于该局 Script；同一剧本的其他线索不会自动进入上下文。
- 调试路由只在 `APP_ENV=development` 暴露。角色 Context API 不属于普通游戏前端接口；Character Agent 不直接读取 ORM model，也不直接查询数据库。
- `DirectorContext` 只定义未来 Director 可用的结构，不构造、不开放 API。当前没有完整案件真相字段；Context schema 也不虚构完整真相。

`/api/games/{game_id}/me/character` 当前以本局唯一的 `human` GameCharacter 识别玩家。登录认证尚未实现，因此 GameSession ID 不是用户身份凭据。
