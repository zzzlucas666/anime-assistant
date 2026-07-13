# Day11 - Autonomous Behavior & Emotion System V2

今天的开发重点是让 AI 从"被动回复"逐步迈向"主动思考"，同时对情绪系统进行了较大规模的重构，进一步完善了角色内部状态的管理逻辑。

---

## 一、Initiative Engine（主动行为系统）

新增 Initiative Engine，用于管理 AI 的主动聊天行为。

整体设计遵循：

* 是否主动聊天：由规则判断（稳定、低成本）
* 主动说什么：交由 LLM 生成（自然、符合人设）

目前实现了三级触发机制：

### 1. 重要事件触发（最高优先级）

当 Event Memory 中存在：

* importance ≥ 0.7
* 尚未主动提起（notified=False）

AI 会主动提起相关事件，与用户继续展开交流。

---

### 2. 情绪触发

当：

* 长时间未互动
* 当前情绪低落（sad）
* 或 Energy 较低

AI 会主动寻找用户聊天，希望缓解自己的情绪。

---

### 3. 长时间未互动

如果：

* 长时间没有聊天
* Relationship 熟悉度达到一定程度

AI 会主动发起"好久不见"类型的对话。

---

整个 Initiative Engine 已运行于后台线程，可周期性检查是否需要主动与用户互动。

AI 开始具备了自主发起交流的能力，而不仅仅是等待用户输入。

---

## 二、Emotion System V2

重新设计了 Emotion Manager，使情绪状态更加符合真实角色的发展过程。

### 1. 移除重复的 Affection

Emotion 中废弃 affection 字段。

Relationship 成为好感度的唯一来源（Single Source of Truth）。

避免两套好感度数据出现冲突。

---

### 2. 情绪来源升级

旧版本：

根据关键词直接判断：

"开心" → happy

新版本：

event_manager.extract_event()

↓

AI 判断事件情绪

↓

Emotion Manager 更新 mood

情绪开始由 AI 对事件的理解决定，而不是简单的关键词匹配。

---

### 3. Mood 自然衰减

新增 Mood Decay。

当长时间没有新的强情绪事件时：

happy

↓

neutral

sad

↓

neutral

避免角色永远停留在同一种情绪。

---

### 4. Energy 被动恢复

Energy 不再只会不断下降。

现在会依据真实流逝时间自动恢复：

* 每 10 分钟恢复 1 点
* 单次恢复存在上限

模拟角色休息后的精力恢复过程。

---

### 5. 身体状态优先级

当 Energy < 20 时：

Mood 自动进入 tired。

疲劳状态优先于普通情绪，体现身体状态对角色行为的影响。

---

## 三、系统联动调整

为了配合 Emotion System V2，对多个模块进行了同步修改。

包括：

* generate_greeting 改为读取 Relationship.affection
* Router 查询好感度统一读取 Relationship
* Intent Prompt 移除废弃字段
* Orchestrator 更新 Emotion 时改为传入 Event，而非用户原始输入
* Router 接口同步增加 Relationship 参数

进一步统一了整个 Runtime 中的数据来源。

---

## 四、本日成果

完成：

✓ Initiative Engine V1

✓ AI 主动聊天机制

✓ Emotion System V2

✓ Mood 自然衰减

✓ Energy 时间恢复

✓ Relationship 成为唯一好感度来源

✓ Emotion 与 Event 深度联动

✓ 多模块数据统一

---

---

## 总结

今天最大的变化，是 AI 从"等待用户输入后再回复"，迈向了"能够依据自身状态与环境主动做出行为决策"。

同时，Emotion System 完成重构，角色内部状态更加统一、自然，也为未来 Planner 与长期记忆系统提供了稳定的状态基础。

整个项目开始从传统聊天机器人逐渐演变为一个具备自主行为能力的数字角色（Autonomous Digital Character）。
