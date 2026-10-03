# Development Log

## 2026-10-03-1.00

### Goal
    - 创建项目git管理框架
    - 
### Completed
    - 创建项目空间
    - 初始化git
    - global git的提交名字和邮箱
    - .gitgore不提交的对象
    - 目前只使用main分支 

### Decisions
    - 第一阶段先搭建开放管理框架，简单完成给定任务。
### Problems
    - None
### Next
    - 部署ollama
    - 完成技术选型

## 2026-10-03-14.24

### Goal
    - 搭建ollam服务
### Completed
    - 拉取官方ollam-install.sh并进行检查
    - 执行安装操作并注意到官方启动文件检查gpu后安装ROMc（不启用）
    - 测试服务端口连接成功
    - 部署qwen3:4b模型

### Decisions
    - 完成服务搭建
    - 部署大模型并进行单次性能测试
### Problems
    - qwen4:4b在think:false的条件下依旧会输出思考内容，导致消耗大量token
### Next
    