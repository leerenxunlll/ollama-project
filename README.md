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

## AI Usage

本项目会使用 ChatGPT 和 Codex 辅助学习、设计、调试与代码 Review。
AI 生成的建议和代码不会直接视为正确结果，所有重要修改都会经过人工理解、测试和 Git Diff 检查。
