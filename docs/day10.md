# Day10 - Runtime Refactor & Fallback Architecture

今天完成了项目的一次重要架构升级，重点优化了 AI 助手的运行流程和系统稳定性。

## 一、Conversation Orchestrator（对话编排器）

新增 `ConversationOrchestrator`，统一管理一轮完整对话的生命周期，使聊天流程更加模块化。

目前一轮对话被划分为三个阶段：

### prepare_turn()

负责：

* 输入清洗
* Intent 识别
* Profile 提取
* Router 判断
* 用户消息记录

### stream_reply()

负责：

* Router 回复
* AI 流式回复

### finalize_turn()

负责：

* Emotion 更新
* Event 提取
* Relationship 更新
* Memory 保存
* Context 同步

main.py 不再直接负责业务逻辑，仅保留：
* 获取用户输入
* 调用编排器
* 输出回复
* 维持聊天循环

业务流程正式从 main.py 中解耦。

---

## 二、Storage Layer（统一存储层）

新增 `storage_utils.py`，为整个项目建立统一的数据读写接口。

主要提供：

* safe_save_json()
* safe_load_json()

新增能力包括：

* 自动创建数据目录
* JSON 原子写入（临时文件替换）
* 自动维护 .bak 备份
* 主文件损坏时自动恢复
* 自动使用默认数据初始化

整个项目的数据存储稳定性得到明显提升。

---

## 三、Fallback Architecture（容错恢复机制）

基于 Storage Layer，为整个项目建立统一的 Fallback 思路。

读取数据时采用三级恢复策略：

主文件

↓

备份文件（.bak）

↓

默认数据（Default Factory）

即使：

* JSON 文件损坏
* 数据不存在
* 写入异常

系统仍然能够正常启动，而不会因为单个文件损坏导致整个 AI 停止运行。

这一机制也为后续：

* Planner
* Initiative Engine
* Memory V2
* Tool Calling

提供统一的异常恢复能力。

---

## 四、Streaming Pipeline 优化

进一步统一流式回复流程。

ConversationOrchestrator 接管 Streaming 输出，使回复生成与输出解耦。

为未来接入：

* Live2D
* TTS
* Lip Sync

预留统一接口。

---

## 五、项目架构变化

旧架构：

User

↓

main.py

↓

各 Manager

新架构：

User

↓

ConversationOrchestrator

↓

Intent

↓

Router

↓

LLM

↓

Event

↓

Relationship

↓

Memory

↓

Storage Layer

↓

Context

整个聊天流程开始形成统一的 Runtime Pipeline。

---

## 六、本日成果

完成：

✓ 引入 ConversationOrchestrator

✓ Main.py 大幅瘦身

✓ Streaming 流程统一

✓ 新增 Storage Layer

✓ 建立统一 Fallback 机制

✓ Context 管理进一步统一

---

## 七、下一步计划

Day11：

开始开发 Planner（行为规划器）。

Planner 将负责 AI 的自主行为决策，例如：

* 是否主动发起聊天
* 是否主动分享内容
* 是否调用工具
* 是否整理长期记忆

未来所有 AI 行为将逐步交由 Planner 统一规划。

---

## 总结

今天最大的变化不是新增聊天功能，而是完成了项目底层运行架构的重要升级。

ConversationOrchestrator 统一了对话生命周期，Storage Layer 为数据读写提供了可靠保障，Fallback 机制显著提升了系统容错能力。

整个项目开始从多个独立模块逐步演变为一个具备统一运行流程和稳定基础设施的 AI Runtime，为后续 Planner、长期记忆、Live2D 以及更多能力扩展打下了坚实基础。
