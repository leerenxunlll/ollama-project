# AI Interview Lab

人工智能协会创智部二面实战项目。

本仓库用于记录和实现本次面试实战任务，并在开发过程中学习 AI 应用开发、软件工程、Git 版本控制和项目管理。

## Goals

当前计划逐步完成：

- 本地大语言模型部署
- 本地模型 API 调用
- Agent 搭建
- 应用接入
- YOLO 训练与实时推理
- AI 与硬件结合
- Harness 探索

## Current Stage

当前阶段：项目初始化。

正在完成：

- [x] 开发环境检查
- [x] Git 仓库初始化
- [ ] 本地大语言模型部署
- [ ] Python 调用本地模型
- [ ] Agent
- [ ] 应用接入

## Development Environment

- OS: Ubuntu 22.04
- CPU: AMD Ryzen 7 8745HS
- GPU: AMD Radeon 780M
- RAM: 35 GiB
- Python: 3.10.12
- Git: 2.34.1
- Docker: 29.8.1
- Editor: Visual Studio Code
## Projiexct install
- ollama 0.35.1(执行ollama-install.sh脚本会检查gpu,自动完成cuda依赖安装，目前官方已经将AMD Raden 780M列入支持，但我的系统（ubuntu22.04）不在支持范围了内，故不启动ROMc(已安装，不启用))

## Project Structure

```text
ai-interview-lab/
├── README.md
├── .gitignore
├── docs/
│   └── dev-log.md
└── src/
```

## Development Principles

- 使用 Git 管理所有有效代码和文档修改
- 每个 Commit 对应一个清晰、可解释的逻辑变化
- AI 生成或修改的代码必须经过人工 Review
- 新增依赖前先理解其用途
- 遇到问题时记录原因、排查过程和解决方案
- 优先实现最小可工作的版本，再逐步优化

## Project copy

## AI Usage

本项目会使用 ChatGPT 和 Codex 辅助学习、设计、调试与代码 Review。
AI 生成的建议和代码不会直接视为正确结果，所有重要修改都会经过人工理解、测试和 Git Diff 检查。

## Local LLM Baseline

当前已完成 Ollama 本地模型服务与 Qwen3 4B 的基础部署验证。

### Environment

| Item | Configuration |
| --- | --- |
| OS | Ubuntu 22.04 |
| CPU | AMD Ryzen 7 8745HS, 8 cores / 16 threads |
| GPU | AMD Radeon 780M |
| RAM | 35 GiB |
| Ollama | 0.35.1 |
| Model | qwen3:4b |
| Model size | 2.5 GB |
| Runtime processor | 100% CPU |

### Single-run Performance

测试接口：

`POST http://localhost:11434/api/chat`

测试条件：

- `stream: false`
- `think: false`
- Processor: CPU
- Prompt: `请用不超过50个汉字解释Git和GitHub的区别。`

| Metric | Result |
| --- | ---: |
| Prompt tokens | 23 |
| Generated tokens | 2726 |
| Prompt evaluation time | 0.0598 s |
| Generation time | 206.022 s |
| Total request time | 206.106 s |
| Generation speed | ~13.23 tokens/s |

> 本结果为单次运行结果，仅用于建立当前设备的初始 CPU 推理 baseline，不代表稳定平均性能。

### Observation

虽然请求设置了 `think: false`，本次响应仍产生了较长的 reasoning 内容，导致仅有较短最终答案的情况下生成了 2726 tokens。

后续将进一步验证 thinking 模式行为，并通过多次重复测试比较模型大小、推理后端和运行参数对性能的影响。

## 多轮对话

运行 `python src/chat_client.py` 后可连续对话，输入 `exit` 退出。成功完成的问答
会保存在 `data/chat.db`；新会话标题取首条成功提问，最长 30 个字符。已有数据库迁移时
保留旧会话标题。数据库时间以 UTC 保存，列表显示本地时间。每次启动后的首条成功问答会
开始新的会话，`/new` 会立即创建空会话。历史可通过 `/list` 和 `/open <number>` 查看并恢复。

可用命令：

- `/list`：按最近更新时间列出会话。
- `/open <number>`：恢复列表中对应会话并继续聊天。
- `/new`：开始一个空白会话。
- `/history`：显示当前会话的问答轮次。
- `/delete <number>`：确认后删除列表中对应会话及其历史。
- `/delete-turn <number>`：删除当前会话的一轮；删除中间轮次后续回答不会重新生成。
- `/exit`：退出；也可输入 `exit`。
