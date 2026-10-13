# Phase 9：Game Runtime

## 目标与边界

Runtime Orchestrator 在玩家打开 Development 页面时，按有界 Tick 协调已有 Game Flow、Director、Speaker Scheduler 和 Character 服务。它只负责调度，不拥有最终游戏状态。

```mermaid
flowchart LR
    UI[Development Runtime Panel] -->|POST tick| API[FastAPI Runtime API]
    API --> Claim[SQLite 原子 claim / lease]
    Claim --> Orchestrator[Runtime Orchestrator]
    Orchestrator -->|资格与阶段校验| Flow[Game Flow Manager]
    Orchestrator -->|安全公开局势| Director[现有 Director Agent]
    Director -->|结构化建议| Validator[Director Action Validator]
    Validator -->|至多一个动作| Character[现有 Character Agent]
    Validator -->|单步阶段推进| Engine[Game Engine]
    Character --> Messages[一条公开消息与角色状态]
    Engine --> State[SQLite 权威状态]
    Messages --> State
    Orchestrator --> Audit[安全 Runtime Action Log]
```

Runtime 不创建新 Agent 或 Dify Workflow，不直接改凶手、Script Truth、Canonical Timeline、角色 Memory、Vote tally 或跨角色私人信息。Director 建议仍需通过既有 Validator；阶段推进仍调用 `advance_game_phase`，因此只能走 State Machine 中唯一合法的下一阶段。

## 触发与 Tick 限制

开发页面默认每 10 秒发出一次 Runtime Tick。每个 GameSession 由 SQLite conditional update 原子认领；同一局有另一个有效 claim 时，后续 Tick 返回 `concurrent_tick_conflict`。数据库写事务会在外部 Dify 调用前提交，不会在 HTTP 请求期间持有长事务。

一次 Tick 最多产生一个主要游戏动作：一条 AI 主动公开发言，或一次阶段推进。Tick 调用 Director 后可以处理至多一条经过校验的建议，不会再递归调用 Director 或触发第二名 AI。读取 `GET /runtime` 没有副作用。

Director 分析只由以下候选事件触发：相关阶段首次进入、出现新真人公开消息、当前讨论阶段达到一次真人静默检查。相同阶段水位和 Human Message ID 会去重；private Message、CharacterMemory、CharacterThought 不触发 Director，也不会被放进 DirectorContext。

| 策略 | V0.1 默认值 | 后端位置 |
| --- | ---: | --- |
| Director 分析冷却 | 50 秒 | `backend/app/game/runtime_policy.py` |
| AI 主动发言冷却 | 60 秒 | `backend/app/game/runtime_policy.py` |
| 真人静默阈值 | 60 秒 | `backend/app/game/runtime_policy.py` |
| 前端 Tick 间隔 | 10 秒 | Runtime Control Panel |
| Runtime action lease | 240 秒 | `backend/app/game/runtime_policy.py` |

每个事件的首次处理结果会持久化；Dify 失败不自动重试同一个事件，避免持续请求和重复成本。新的公开消息或阶段事件可以再次触发调度。租约过期后，下一次 Tick 可认领该局并标记旧的 processing 日志为 `lease_expired`；旧 claim token 无法完成新动作。

## 阶段与玩家准备

阶段顺序仍是 `intro → act_1 → investigation_1 → discussion_1 → act_2 → investigation_2 → discussion_2 → final_discussion → vote → ending`。

| 阶段 | Runtime 自动规则 |
| --- | --- |
| `intro`、`act_1`、`act_2` | 先显示当前已解锁的公共与真人私人章节。需要玩家确认已阅读，并满足 Game Flow 最低阶段时长，才推进。Intro 复用 `human_intro_acknowledged_at`；Act 1/2 各有一个幂等确认记录。 |
| `investigation_1`、`investigation_2` | 不会因超时或 Director 建议强制结束。玩家点击“结束搜证并继续”后，满足最低时长才推进。搜证仍由既有规则处理。 |
| `discussion_1`、`discussion_2` | 玩家明确准备结束且满足最低时长时推进；否则只有 Director 建议推进、阶段最低时长满足、真人至少 60 秒无公开发言且建议仍对应当前阶段时，才自动推进。 |
| `final_discussion` | 必须由玩家确认“准备进入投票”并满足最低时长。Director 的 phase-advance 建议只记为 advisory。 |
| `vote` | 不触发 AI 公开发言，不伪造 AI 选票。四名角色已投票且满足 Game Flow 条件后，Runtime 才可推进到 `ending`。 |

公共发言入口继续使用 Game Flow Manager 的 `can_public_speak` 规则。Runtime 主动发言必须针对本局 AI GameCharacter、通过 Speaker Scheduler 目标校验、满足真人静默和 AI 发言冷却。Character Context Builder 只提供该角色获准读取的信息。AI 回复过程中若游戏阶段改变，保存前会再次做阶段与 claim 检查，迟到的公开回复会被丢弃。

## API

所有 Runtime API 仅在 `APP_ENV=development` 开放，当前项目没有正式登录认证。

| 方法与路径 | 用途 |
| --- | --- |
| `GET /api/games/{game_id}/runtime` | 读取状态与最近安全动作日志，不创建状态、不触发 AI。 |
| `POST /api/games/{game_id}/runtime/start` | 为已开始的 GameSession 启用 Tick 调度。 |
| `POST /api/games/{game_id}/runtime/pause` | 阻止新 Tick 动作认领；已认领的动作可以完成。 |
| `POST /api/games/{game_id}/runtime/tick` | 尝试认领并运行一次有界调度。 |
| `POST /api/games/{game_id}/runtime/acknowledge-phase` | 只确认当前 `intro`、`act_1` 或 `act_2`。请求不接受客户端指定未来阶段。 |
| `POST /api/games/{game_id}/runtime/ready` | 为当前调查、讨论或最终讨论记录真人准备状态。 |

Tick 响应用 `action_type`、`execution_status`、阶段前后值和安全 `reason_code` 表示结果，不返回 Director reason、模型上下文或剧本秘密。Runtime 状态返回最多 10 条动作摘要，不包含 event key、claim token、完整 Context 或 Message 正文。

## SQLite 状态、日志与错误恢复

`GameRuntimeState` 保存开关、时间戳、水位、ready 标记、claim token、租约与安全错误码。`GamePhaseAcknowledgement` 对同一局的 Act 1/Act 2 确认提供唯一约束。`GameRuntimeActionLog` 以 `(game_session_id, event_key)` 唯一键去重，并只保存动作摘要与关联记录 ID。Director Recommendation 新增来源 phase、`phase_started_at` 和最新公开消息水位，用于拒绝过期建议。

Phase 9 migration 是 `20261012_phase9_runtime`，升级前需备份真实开发数据库并运行：

```bash
alembic -c backend/alembic.ini upgrade head
alembic -c backend/alembic.ini current
```

应用启动时 `Base.metadata.create_all()` 只补建缺失表，不会替已有表增加列，因此不能代替 Alembic。迁移没有删除或重建既有游戏、消息、Memory、Thought、Vote、ScriptDraft、ReviewRun、RevisionRecord 或 CanonicalData。

Runtime 将已知 Dify 错误转换为安全 reason code，例如 `director_timeout`、`director_not_configured`、`character_timeout`、`character_output_invalid`。错误响应和日志不包含 API Key、原始模型错误正文、DirectorContext、CharacterContext、inner_os、私人消息或 Script Truth。对某个事件的失败不会无限重试；页面可显示状态并由玩家继续公开交流、搜证、Ready 或手动暂停。

## 浏览器关闭与权限

V0.1 没有 Celery、Redis、APScheduler、WebSocket、SSE 或常驻后台 worker。页面关闭时客户端 Tick 停止，Runtime 不保证继续自主运行；游戏阶段计时仍按数据库中的服务端 `phase_started_at` 计算，页面重新打开不会重置时间。重新打开 Development 页面会重新读取服务器状态。

Runtime status 与日志都不包含私人运行时内容。Director 仍通过独立 DirectorContextBuilder 获得公开局势与其被授权的剧本信息；Character 仍通过当前 GameCharacter 的 CharacterContext 获得角色自己的信息。Runtime 不构造额外的信息通道。
