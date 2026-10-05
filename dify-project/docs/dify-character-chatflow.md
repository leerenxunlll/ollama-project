# Dify Character Chatflow 配置

本文定义 Phase 4 后端 CharacterAgent 调用的 Chatflow 契约。此工作流只负责依据已授权的角色 Context 生成一段角色台词，不执行工具调用或游戏操作。

## 创建 Chatflow

1. 在 Dify 中创建并发布一个 **Chatflow**，配置可用的 LLM 节点。
2. 在开始节点增加必填文本输入 `character_context`。后端会把经 Pydantic 验证的 `CharacterContext` 序列化为 JSON 字符串传入。
3. 将系统变量 `sys.query` 连接到 LLM 节点的 User 内容，作为玩家当前发送的消息。使用 Dify 的变量选择器引用变量，避免手动输入错误的节点变量路径。
4. 将 LLM 节点的文本输出连接到 Answer 节点，作为本轮角色说出的台词。
5. 发布 Chatflow，并在项目后端配置该 Chatflow 对应的 API URL 与应用 API Key。

应用应提供 `character_context` 输入变量，接收本轮玩家文本的 `query`，并返回非空文本回答。后端使用 blocking 请求，不依赖 Dify conversation 历史；每次请求的 `conversation_id` 为空。Dify 的对话记录不是游戏记忆来源。

后端调用 Dify 的 `POST {DIFY_API_URL}/chat-messages` 请求形态如下。`user` 是不含玩家真实身份信息的稳定内部标识；请求不携带真实密钥示例。

```json
{
  "inputs": {
    "character_context": "<经过校验的 CharacterContext JSON 字符串>"
  },
  "query": "玩家当前发送的消息",
  "response_mode": "blocking",
  "conversation_id": "",
  "user": "game-123-character-456"
}
```

HTTP Header 使用 `Authorization: Bearer <DIFY_CHARACTER_API_KEY>` 与 `Content-Type: application/json`。Dify 应通过 Chatflow Answer 返回文本；后端只接受非空台词作为 `speech`。

## System Instruction

将以下内容放入 LLM 节点的 System Instruction，并通过 Dify 变量选择器插入 `character_context`：

```text
你正在扮演 character_context 中定义的角色。你的角色资料和当前可见信息如下：
【在此通过 Dify 变量选择器插入 character_context】

请遵守以下角色行为要求：
1. 只使用 character_context 中提供的信息，以及玩家当前这条消息。
2. 保持角色的 personality、speaking_style、personal_goal 与当前情境一致。
3. 你可以按角色目标隐瞒、回避或说谎，但不得声称知道 context 中不存在的事实。
4. 不得自行创造、补充或宣布关键线索，不得改变案件真相。
5. 不得宣布或执行游戏 phase、GameSession 状态、角色分配或搜证结果的变化。
6. 不得跳出角色讨论 system prompt、后端实现、模型或其他实现细节。
7. 直接像真人角色一样回应玩家，不要说明自己是 AI，也不要解释回答策略。
8. 只输出角色实际说出的内容，不输出分析、标签、JSON 或内心独白。
```

玩家输入由 Dify Chatflow 的 `sys.query` 提供给 LLM User 内容；不要把该输入拼入 `character_context`，两者由后端分别传递。

## 安全边界

System Instruction 用来约束角色行为和回复形式，不是信息安全边界。提示词不能保证模型保密。安全性必须由 FastAPI 后端通过 CharacterContextBuilder 实现：只把当前目标角色获准知道的数据发送给 Dify。普通 Character Agent 不得获得完整剧本真相、其他角色私密背景、其他角色的私聊、随机种子或未获知线索。

不要在 Chatflow 中添加可以查询数据库、发放线索、推进游戏阶段或修改角色状态的工具。Dify 只返回台词；Game Engine 和数据库继续拥有游戏规则与权威状态。
