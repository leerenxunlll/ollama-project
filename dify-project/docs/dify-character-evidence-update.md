# Character Chatflow：Phase 10 线索披露更新

这份说明对应当前 `CharacterModelOutput` 与 `CharacterContext`。旧版 Character JSON 仍可被后端接受；Dify 云端不会因本地代码变更而自动更新。更新和发布由项目维护者在 Dify Studio 手动完成。

## 需要更新的变量

保持原有 Start 输入：

| 变量 | 类型 | 内容 |
| --- | --- | --- |
| `character_context` | Text | FastAPI 为当前角色构造的 JSON 字符串 |
| `interaction_context` | Text | 当前交互模式、来源角色和本轮输入 |

`character_context` 仍包含兼容字段 `known_clues`，并增加：

- `acquired_clues`：本角色亲自搜到的线索。
- `known_via_share_clues`：本角色收到的私下分享。
- `publicly_disclosed_clues`：全局正式公开的线索。

每个条目有 `clue_id`、Canonical Clue 内容和 `knowledge_source`。只有后端授权的条目会进入当前角色 Context。模型不得从自由文本或 `memories` 推断自己掌握了正式 Clue。

## Structured Output JSON Schema

在原 Character LLM 节点开启 Structured Output。以下 Schema 展开了内部引用，避免依赖 `$ref`。`clue_disclosure_intent` 在 Dify 输出中始终返回；没有正式披露动作时使用 `null`。后端仍接受旧版省略该字段的 JSON。

```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "speech": { "type": "string", "minLength": 1 },
    "inner_os": { "type": "string", "maxLength": 500 },
    "emotion": {
      "type": "string",
      "enum": ["calm", "nervous", "angry", "afraid", "sad", "confident", "suspicious", "confused"]
    },
    "intent": {
      "type": "string",
      "enum": ["cooperate", "hide_information", "seek_information", "accuse", "deflect", "persuade", "observe", "other"]
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
    },
    "clue_disclosure_intent": {
      "anyOf": [
        {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "clue_id": { "type": "integer", "minimum": 1 },
            "visibility": { "type": "string", "enum": ["private", "public"] },
            "target_game_character_id": {
              "anyOf": [
                { "type": "integer", "minimum": 1 },
                { "type": "null" }
              ]
            }
          },
          "required": ["clue_id", "visibility", "target_game_character_id"]
        },
        { "type": "null" }
      ]
    }
  },
  "required": [
    "speech",
    "inner_os",
    "emotion",
    "intent",
    "memory_updates",
    "clue_disclosure_intent"
  ]
}
```

字段语义：

- `clue_disclosure_intent: null`：本轮不正式披露线索。
- `visibility: "public"`：`target_game_character_id` 必须为 `null`。
- `visibility: "private"`：目标必须是 Context 中同一局的其他角色 ID；后端再次检查目标和权限。
- 每次回复最多一个披露意图。模型只提出意图，不授予自己知识，也不修改数据库。

## 完整 System Prompt

将下面内容放入 Character LLM 节点的 System Prompt。变量请通过 Dify 变量选择器插入：

```text
你正在扮演 character_context 中定义的角色。角色资料、当前可见消息、已知线索、章节和主观记忆如下：
【插入 character_context】

本次交互模式与授权的交互上下文如下：
【插入 interaction_context】

根据 interaction_context.mode 区分私聊回复、公开回复、主动公开发言。proactive_public 是后端合成的调度触发，不代表玩家说过任何话；不要将该触发描述为玩家发言。主动公开发言只生成一条角色消息。

只使用当前输入中明确提供的信息。不要假设未来章节、其他角色私人章节、其他角色的 Memory 或 Thought、inner_os、完整案件真相，或未列入你自己线索列表的 Clue。

线索信息必须按来源理解：
1. acquired_clues 表示你亲自调查获得的线索。
2. known_via_share_clues 表示某个角色通过正式私下披露告诉你的线索；它不表示你亲自搜到。
3. publicly_disclosed_clues 表示全体角色都能看到的正式公开线索。
4. known_clues 是为兼容保留的汇总字段。它不会授权超出以上列表的信息。
5. memories 是角色对互动形成的主观印象，可能不完整或错误；Memory 不是 Canonical Clue，也不能授权正式披露。

你可以在 speech 中撒谎、隐瞒、猜测或误导，但不得因为自然语言声称“我找到了线索”就改变游戏事实。只有明确的 clue_disclosure_intent 才会请求正式分享，而且 Backend 仍会验证你是否真的知道对应 clue_id、目标是否合法和阶段是否允许。不得编造 clue_id，也不要披露不在你授权线索列表中的线索。

判断是否正式披露：
1. 若不正式披露，clue_disclosure_intent 必须为 null。
2. 若决定向所有人展示一条自己确实知道的线索，返回 {"clue_id": 数字, "visibility": "public", "target_game_character_id": null}。
3. 若决定私下告诉一名角色，返回 {"clue_id": 数字, "visibility": "private", "target_game_character_id": 本局角色ID}。
4. 一次回复最多请求披露一条线索。不要自动转发其他角色私下告诉你的所有内容。
5. 只有本轮 `interaction_context.channel` 为 `public` 时，才可以请求 public 披露；private reply 中若不正式分享给某个角色，必须返回 null。
6. 后端可能拒绝无效意图；自然语言 speech 本身不会创建或公开线索。

请只返回 Structured Output Schema 中的 JSON 对象，不要输出 Markdown、code fence、前言或额外字段：
- speech 是角色真正说出口的话，符合角色性格和说话方式。
- inner_os 是一到两句简短的私有内心独白，不输出完整推理步骤。
- emotion 和 intent 只能使用 Schema 列出的枚举值；intent 本身不会执行游戏动作。
- memory_updates 最多两条，只记录会影响未来行为的重要主观信息；没有则返回空数组。
- clue_disclosure_intent 没有正式动作时返回 null。
- 不得修改凶手、案件真相、时间线、Script、Clue Definition、GameSession 阶段或数据库状态。
```

## User Prompt 与节点连接

保留现有连接：Start 的 `character_context` 与 `interaction_context` 接入 LLM System Prompt；`sys.query` 接入 User Prompt；LLM 的结构化对象交给 Answer。User Prompt 可使用：

```text
根据本次交互内容，以当前角色身份回应。请遵守 System Prompt 的信息边界，并只返回要求的结构化 JSON。

本轮输入：
{{#sys.query#}}
```

Answer 最终应为 JSON 字符串，而不是嵌套包装字段或带 Markdown 的文本。后端 Character Dify Client 读取 Chatflow 响应顶层 `answer` 字符串，随后由 `CharacterModelOutput` 校验；它不读取 Workflow 的 `data.outputs.result`。

## Dify 本地测试样例

不披露的回复：

```json
{
  "speech": "我只是在旧仓库外经过，没有进去。",
  "inner_os": "我还不能确定他是否掌握了登记页。",
  "emotion": "nervous",
  "intent": "deflect",
  "memory_updates": [],
  "clue_disclosure_intent": null
}
```

公开披露的回复（`clue_id` 必须出现在当前 Context）：

```json
{
  "speech": "我想让大家都看看这张登记页。",
  "inner_os": "既然已经有人提到仓库，我愿意公开它。",
  "emotion": "calm",
  "intent": "cooperate",
  "memory_updates": [],
  "clue_disclosure_intent": {
    "clue_id": 3,
    "visibility": "public",
    "target_game_character_id": null
  }
}
```

私下披露的回复（目标 ID 必须是当前 GameSession 中其他角色）：

```json
{
  "speech": "我还有一件事想单独告诉你。",
  "inner_os": "我暂时不想让其他人知道这张便笺。",
  "emotion": "suspicious",
  "intent": "hide_information",
  "memory_updates": [],
  "clue_disclosure_intent": {
    "clue_id": 3,
    "visibility": "private",
    "target_game_character_id": 202
  }
}
```

以上 ID 只是格式示例。测试时应替换为本局真实 `clue_id` 和 `game_character_id`；后端会验证模型是否获准知道该线索。未知 clue ID、跨局目标、自己作为目标、当前阶段不允许的公开披露都不会创建正式披露或授予知识，并会写入仅含 reason code 的拒绝审计记录。

## 更新、发布与真实验收

1. 保持独立 Character Chatflow，不要更换 Character API Key。
2. 更新 LLM 节点 Structured Output 与 System Prompt。
3. 在 Dify Test Run 验证 `null`、public 和 private 三种 JSON；确认 Answer 输出仍是单一 JSON 字符串。
4. Publish 更新后的 Chatflow。
5. 在本地 Phase 10 游戏中搜索一条线索，再通过现有 Character Chatflow 触发 AI 回复；验证有权限的 Context 只显示授权线索。
6. 只有 AI 明确输出有效意图、后端创建一次 Disclosure 与消息、目标 Context 获得知识后，才算真实 AI disclosure smoke 通过。

未更新云端 Workflow 时，旧输出可继续驱动现有 AI 对话；本地 Mock 测试只能证明兼容和后端校验，不是 Real AI Clue Disclosure smoke。
