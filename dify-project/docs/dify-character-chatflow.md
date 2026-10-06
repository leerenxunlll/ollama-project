# Dify Character Chatflow 配置

Phase 5 将 Character Chatflow 的输出从单独台词升级为结构化 JSON。Phase 6 继续使用同一个 Character Chatflow；后端通过 `character_context` 和 `interaction_context` 提供角色可见信息及交互模式。Dify 仍只负责生成角色回复；后端负责校验、权限判断、调用顺序和持久化。

## 更新现有 Chatflow

1. 打开当前已发布的 Character Chatflow，编辑原 LLM 节点，保留现有 **Structured Output** 和下方 JSON Schema。
2. 确认开始节点提供 `character_context` 与 `interaction_context` 两个文本变量。它们由后端按本次角色调用分别构造；`character_context` 含该角色获准的信息，`interaction_context` 含交互模式和当前交互所需上下文。
3. 将 `character_context` 和 `interaction_context` 通过 Dify 变量选择器插入 LLM 节点的 System Instruction。`sys.query` 仍连接到 User 内容，作为本次调用的输入。
4. 根据 `interaction_context.mode` 让角色以正确的沟通方式回应。可用值为 `private_reply`、`public_reply` 和 `proactive_public`，语义见下节。
5. 将结构化输出交给 Answer 节点。Answer 的最终 `answer` 必须是一个 JSON 字符串，不能添加说明文字或 Markdown code fence。
6. 保存并重新发布 Chatflow，再分别验证私聊、公开回复与主动公开发言；需要真实 Dify 凭据与可用模型配额，文档本身不代表真实服务 smoke test 已通过。

## Phase 6 输入与交互模式

同一个 Character Chatflow 服务所有 AI 角色。每次请求都提供 `character_context` 和 `interaction_context`，而不是为公开对话另建 Chatflow。后端负责生成这两个上下文并过滤信息；Dify 变量仅供模型理解角色和本次交互。

| `interaction_context.mode` | 含义 | `speech` 的去向 |
| --- | --- | --- |
| `private_reply` | 回应发给该角色的私聊消息 | 私聊回复 |
| `public_reply` | 回应玩家或上一位 AI 在公共频道的发言 | 公共频道回复 |
| `proactive_public` | 角色被后端选中，在没有玩家新发言时主动发言 | 公共频道的一条主动消息 |

每次 `proactive_public` 调用都会带有后端生成的固定 synthetic trigger，用于说明本次主动发言的时机。它只是编排信号，不是玩家说过的话，不得在 `speech` 中冒充玩家发言，也不是游戏 `Message`，后端不会把它作为 Message 持久化。一次主动 step 只生成一条角色回复。普通公开回合由后端顺序调用角色，最多请求两条 AI 公开回复。

三个模式仍使用同一个 Phase 5 Structured Output。模式不改变 Schema，也不授权角色访问额外信息；角色只能依据后端提供的 `character_context`、`interaction_context` 和本次输入生成回复。`inner_os` 与 `memory_updates` 仍由后端校验并按 Phase 5 规则处理，不作为普通公开消息展示。

如果当前模型不支持 Dify 的 Structured Output，建议在 Dify 中选择支持该功能的模型。也可以先用提示词要求输出该格式，但后端仍会严格校验；格式错误时本轮不会写入数据库。

## Structured Output Schema

```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "speech": {
      "type": "string",
      "minLength": 1,
      "description": "角色实际说出口的话"
    },
    "inner_os": {
      "type": "string",
      "maxLength": 500,
      "description": "一到两句简短的私人内心独白，不包含完整推理步骤"
    },
    "emotion": {
      "type": "string",
      "enum": [
        "calm",
        "nervous",
        "angry",
        "afraid",
        "sad",
        "confident",
        "suspicious",
        "confused"
      ]
    },
    "intent": {
      "type": "string",
      "enum": [
        "cooperate",
        "hide_information",
        "seek_information",
        "accuse",
        "deflect",
        "persuade",
        "observe",
        "other"
      ]
    },
    "memory_updates": {
      "type": "array",
      "maxItems": 2,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "properties": {
          "content": { "type": "string", "minLength": 1 },
          "importance": { "type": "integer", "minimum": 1, "maximum": 5 }
        },
        "required": ["content", "importance"]
      }
    }
  },
  "required": ["speech", "inner_os", "emotion", "intent", "memory_updates"]
}
```

Answer 示例（Answer 内容只返回 JSON 本身）：

```json
{
  "speech": "我昨晚一直在旧仓库附近。",
  "inner_os": "他问得太具体了，我得先弄清他知道多少。",
  "emotion": "nervous",
  "intent": "deflect",
  "memory_updates": [
    {
      "content": "玩家追问了旧仓库附近的行踪。",
      "importance": 3
    }
  ]
}
```

若本轮没有值得长期记住的信息，返回 `"memory_updates": []`。不要为了填充字段而记录每一句对话。

## System Instruction

将以下内容放入 LLM 节点的 System Instruction，并通过 Dify 变量选择器插入 `character_context`：

```text
你正在扮演 character_context 中定义的角色。角色资料、当前可见消息、线索和该角色自己保留的记忆如下：
【在此通过 Dify 变量选择器插入 character_context】

本次交互模式与授权的交互上下文如下：
【在此通过 Dify 变量选择器插入 interaction_context】

根据 interaction_context.mode 区分私聊回复、公开回复、主动公开发言。proactive_public 表示后端发出的合成编排触发，不代表玩家说过任何话；不要将该触发描述为玩家发言。主动公开发言只生成一条角色消息。

只使用 character_context、interaction_context 和本次调用输入中允许你获知的信息。不要声称知道未提供的事实。

请返回符合 Structured Output Schema 的 JSON 对象，且只返回这个对象：
1. speech 是角色真正说出口的话，符合角色的性格和说话方式。
2. inner_os 是一到两句简短、角色化的私人内心独白；不要输出完整推理步骤，也不要描述系统实现。
3. emotion 表示本轮结束时角色的主要情绪，只能使用 Schema 列出的值。
4. intent 描述这轮的行为目的，只能使用 Schema 列出的值。它只是描述，不会执行游戏动作。
5. memory_updates 只记录会影响未来行为的重要信息，例如玩家透露的重要事实、形成的怀疑、承诺或重要关系变化。不要记录每句话；没有重要内容时返回空数组。
6. 不得创造、宣布或授予正式线索，不得改变案件真相、GameSession 状态或当前阶段。
7. 不得输出 Markdown、code fence、前言、解释或 Schema 外的字段。
```

## 后端请求与校验边界

后端仍调用 `POST {DIFY_API_URL}/chat-messages`，使用 `DIFY_CHARACTER_API_KEY`。请求的 `character_context` 与 `interaction_context` 都由后端构造并作为 Chatflow 输入；角色可见信息由后端权限过滤。真人当前消息通过 `query` 提供；主动发言使用的 synthetic trigger 仅作本次调用输入，不是玩家 Message。每次请求都使用新的 Dify conversation，不依赖 Dify 保存对话历史。

Dify Client 只处理 HTTP。Character Agent 从 Answer 读取 JSON 并使用后端 `CharacterModelOutput` 校验字段、枚举和数量。无效 JSON 或字段校验失败时，不保存失败角色的 AI Message、Thought、Memory 或 emotion。私聊仍按整轮 atomic 语义不保存玩家消息；公开回合的 Human public Message 已在 AI 调用前提交，因此保留并以脱敏 `partial` 结果报告角色调用失败。

成功时普通聊天响应只包含玩家消息与角色 `speech`。`inner_os` 和 `memory_updates` 不进入普通消息；它们由后端在同一事务里保存到 `CharacterThought` 与 `CharacterMemory`。开发调试 API 仅在 `APP_ENV=development` 开放。

Structured Output 和 System Instruction 都不是信息安全边界。权限隔离必须由 FastAPI 后端构造角色专属 Context；普通角色上下文不得包含完整剧本真相、其他角色私密记忆或内心状态。不要在 Dify 工具中添加修改游戏状态、推进阶段或发放线索的能力。
