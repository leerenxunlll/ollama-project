# 投票与结局

Phase 11 在既有 `Vote` 表上增加 AI 投票决策，不创建第二套票数存储。开始游戏时保持一个 Human 和三个 AI；Director 不投票。

## 规则与隐私

- 每个 GameCharacter 在 `vote` 阶段只能投一票，不能自投，不能改票。数据库唯一约束和同局复合外键约束 voter/target，服务校验 Human 与 AI 身份。
- Human 通过既有 `POST /api/games/{game_id}/votes` 投票。AI 由 Runtime 按 `GameCharacter.id` 稳定顺序选择下一位未投票角色，一次 Tick 最多调用一个 AI Vote Workflow。
- Dify Vote Workflow 仅使用独立 `DIFY_VOTE_API_KEY`。`CharacterVoteContext` 包含该 AI 自己的 `CharacterContext` 和三名公开候选人，不包含 Canonical Truth、DirectorContext、其他人的票、理由、Thought、Memory 或私聊。
- Runtime 使用数据库中的 Phase 9 claim/token/lease/stale-phase guard；`votes` 表唯一约束防止同一角色重复选票。失败最多重试 3 次，每次间隔 30 秒，不随机代投。
- 普通 `GET /api/games/{game_id}/vote/status` 只返回总进度、Human 状态与 AI 的已投票标志。详细票数接口 `/votes/result` 仍是 Development-only。

## 平局与正式结算

现有确定性 `tally_votes` 按最高票数决定唯一被指认者；如最高票并列，`winner_game_character_id` 为 null 且 `is_tie=true`，不随机选人。只有四名角色各有一张合法票后才能从 `vote` 转到 `ending`。

`GameResolution` 每局只有一行，以 `game_session_id` 主键保证唯一。Game Engine 从已发布 `ScriptCanonicalData.case_truth_json.culprit_role_key` 和 `role_character_ids_json` 读取凶手，并核对其与 Script 中唯一 `is_killer` 角色一致。角色发言、Memory、Thought、Director 建议和投票理由都不能修改真相。结算同时记录集体投票结果与真人是否单独猜中凶手。

`vote → ending` 与 GameResolution、结束时间和 system ending 消息在一个事务内完成。条件更新和唯一主键防止两个请求重复结算。完整 Ending 由程序从 Canonical Truth、Canonical Timeline、关键 Clue 与四张真实 Vote 构造，不请求 Ending LLM。

## API

| 方法 | 路径 | 权限与用途 |
| --- | --- | --- |
| GET | `/api/ai/vote/status` | 返回 Vote Workflow 是否配置，不返回密钥 |
| GET | `/api/games/{game_id}/vote/status` | 投票进度安全投影，不返回选择目标或理由 |
| POST | `/api/games/{game_id}/votes` | Development-only Human 投票，不能代投 AI |
| GET | `/api/games/{game_id}/votes/result` | Development-only 详细计票调试 |
| GET | `/api/games/{game_id}/ending` | Development-only；只在正式结算后揭示真相及投票 |
| GET | `/api/games/{game_id}/replay` | Development-only；只在正式结算后返回 God-View |

没有真实登录认证；Ending/Replay 仅在 `APP_ENV=development` 提供。公网部署前必须增加用户身份与 GameSession 授权。
