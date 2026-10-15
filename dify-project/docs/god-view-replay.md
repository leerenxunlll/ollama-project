# God-View Replay

`GET /api/games/{game_id}/replay` 读取数据库中真实保存的事件，并按时间戳与稳定事件 ID 排序。只有游戏状态为 `finished`、阶段为 `ending` 且存在匹配本局 Script 的 `GameResolution` 时才开放；后端执行权限检查，不能通过客户端参数绕过。

回放复用现有记录：

| 回放内容 | 持久化来源 |
| --- | --- |
| 游戏开始与阶段 | `GameSession.started_at`、带 phase 的 system `Message` |
| public/private 发言 | `Message`，保留发送者、接收者、实际正文和发生阶段 |
| 虚构内心 OS | 与具体 AI 回复 `Message` 精确关联的 `CharacterThought` |
| 角色记忆 | `CharacterMemory` 的实际创建时间和来源消息；标记为主观记忆 |
| 搜证获得线索 | `GameCharacterClue`，保留角色、线索和发生阶段 |
| 正式私下/公开披露 | `GameClueDisclosure` 与关联消息；披露消息合并成一个披露事件，避免重复展示 |
| 四人投票 | `Vote`，结局揭晓后显示目标与 AI 保存的理由 |
| 真实真相与结局 | `ScriptCanonicalData`、`GameResolution`、`GameSession.ended_at` |

旧记录新加的 phase 列允许为 null。回放仅在有更早、真实持久化的 system 阶段消息时推导缺失阶段；不会按当前阶段倒填历史，也不会重建不存在的 Thought/Memory。Memory 以创建时间作为事件时间，并明确说明它是角色主观认知，不代表客观真相。

`inner_os` 是应用保存的虚构角色独白，不是模型供应商的隐藏 Chain-of-Thought。回放不请求任何 AI，也不访问供应商隐藏推理。私聊与其他角色私有记录只进入结束后的开发 God-View，不进入 Character 或 Director 的游戏中 Context。

当前没有登录认证，因此完整私密回放仅限 `APP_ENV=development`。该接口不能直接暴露到公网；正式部署前必须增加用户身份验证与 GameSession 级授权。
