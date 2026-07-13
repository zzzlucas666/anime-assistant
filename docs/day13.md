# Day13 开发日志

Day13 开发日志
Day13 - Memory V2：Semantic Memory & Long-term Memory

今天完成了 Memory 系统的第二次重大升级，正式引入语义记忆（Semantic Memory）与长期记忆（Long-term Memory），同时重构了整个 Memory Pipeline，使 AI 的记忆能力从简单的历史记录升级为真正能够参与推理的长期记忆系统。

一、Semantic Memory（语义记忆）

新增：

semantic_memory.py

引入本地 Embedding 模型 BAAI/bge-small-zh-v1.5。

实现：

本地文本向量化（Embedding）
余弦相似度（Cosine Similarity）计算
Top-K 语义检索

事件在保存时自动生成向量。

检索时不再依赖关键词，而是根据语义寻找历史事件，使角色拥有真正意义上的"联想能力"。

二、Long-term Memory（长期记忆）

新增：

long_term_memory.py

Conversation History 超过容量后：

旧对话

↓

AI 自动总结

↓

长期摘要

↓

永久保存

长期摘要将在后续 System Prompt 中持续参与推理，使 AI 即使遗忘具体聊天内容，也能保留长期经历。

三、Context Builder

新增：

context_builder.py

统一负责 Memory Context 的构建。

目前 Context 包括：

最近重要事件
语义相关事件
长期摘要

同时实现：

自动去重
Prompt 字符预算控制
Memory 优先级管理

Prompt 不再由各模块分别拼接，而是统一由 Context Builder 管理。

四、Memory Pipeline 重构

重新设计 Memory 工作流程：

用户输入
    │
    ▼
Semantic Retrieval
    │
最近事件 + 长期摘要
    │
    ▼
Context Builder
    │
    ▼
System Prompt
    │
    ▼
  LLM

Memory 正式从"聊天记录"升级为 AI 推理的重要组成部分。

五、模块优化
event_manager.py
保存事件时自动生成 Embedding
新增语义检索接口
支持获取语义相关事件
memory_manager.py

修复隐藏 Bug：

此前 save_memory 仅保存截断后的副本。

原始 conversation_history 实际不会缩短。

长期运行后内存会持续增长。

现改为返回：

(new_history, overflow_messages)

调用方重新赋值，彻底修复 Memory 无限增长问题。

chat.py
System Prompt 改为 Context Builder 统一生成
新增 query_text 参数支持语义检索
新增长期记忆摘要区域
orchestrator.py

同步适配新的 Memory Pipeline。

主要优化：

修复新的 save_memory 调用方式
累积 Overflow Message
摘要生成改为回复结束后后台处理

降低当前回复延迟。

initiative_engine.py

同步适配新的 Memory 保存方式。

统一整个 Runtime 的 Memory 流程。

今日成果

完成：

 Semantic Memory
 Embedding 向量化
 Cosine Similarity 检索
 Long-term Memory
 AI 自动摘要
 Context Builder
 Prompt Budget 控制
 Memory Pipeline 重构
 Memory 无限增长 Bug 修复
Runtime 全模块适配
