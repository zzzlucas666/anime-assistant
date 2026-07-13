# Day12 - Runtime Reliability & CLI Experience

今天的开发重点放在 Runtime 的稳定性和用户体验优化上，

## 一、统一日志系统（Logger System）

新增 logger_utils.py，为整个项目提供统一日志接口。

主要特性：

* 所有模块共享统一 Logger
* 日志统一写入 data/app.log
* 控制台仅输出 Warning 及以上日志，避免正常运行时刷屏
* 后台线程异常也能够被记录，方便后续排查问题

统一日志系统让 Runtime 的运行状态更加透明，也提升了后续调试和维护效率。

---

## 二、主动消息冷却机制（Proactive Cooldown）

为 Initiative Engine 增加主动消息限制。

新增两层保护：

1. 两次主动消息之间必须满足最小时间间隔（默认 60 分钟）
2. 每日主动聊天次数存在上限（默认 3 次）

避免角色在持续满足触发条件时频繁打扰用户。

同时新增 proactive_tracker，用于记录：

* 最近一次主动消息时间
* 今日主动次数
* 自动跨天重置计数

让角色主动行为更加自然，更符合真实社交节奏。

---

## 三、终端聊天体验优化

引入 prompt_toolkit。

优化控制台聊天界面：

* 更友好的输入体验
* 更整洁的命令行交互
* 为后续终端 UI 升级提供基础

虽然未来计划接入 Desktop UI 与 Live2D，但终端版本依然保持良好的使用体验。

---

## 四、本日成果

完成：

✓ Logger System

✓ Runtime 日志统一管理

✓ Initiative Cooldown

✓ 主动聊天每日次数限制

✓ 主动聊天时间冷却

✓ Prompt Toolkit CLI 优化

---

## 五、下一步计划

继续完善 Runtime：

* Planner（行为规划器）
* Long-term Memory V2
* Context Builder 优化
* Runtime 调度器（Scheduler）

逐步构建真正具有自主行为能力的数字角色系统。

---

## 总结

今天没有新增大量功能，而是重点提升了 Runtime 的稳定性、可维护性以及终端交互体验。

主动聊天机制开始具备节制能力，日志系统也为长期运行和问题排查提供了统一支持，为整个项目进一步产品化做好了准备。
