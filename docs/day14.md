# Day14 开发日志

Day14 开发日志
Day14 - Hybrid Retrieval & Memory V2 Optimization

今天继续完善 Memory V2，正式完成 Hybrid Retrieval（混合检索） 的设计与实现。

Memory 检索不再仅依赖语义相似度，而是综合考虑 语义相关性、事件重要度以及时间衰减 三个维度，使 AI 在回忆历史事件时更加符合真实的人类记忆方式。

一、Hybrid Retrieval 正式实现

重新设计 Memory 检索流程。

检索评分由单一语义相似度升级为：

Final Score =
Semantic Similarity × 0.40
+ Importance × 0.35
+ Recency × 0.25

其中：

Semantic Similarity：语义相关性
Importance：事件重要程度
Recency：时间新鲜度（指数衰减）

真正实现了 Memory V2 的混合检索策略（Hybrid Retrieval）。

二、Memory V2 持续优化
event_manager.py

优化 Event Extraction Prompt。

此前 AI 容易生成：

用户表达了……

这种抽象事件。

新的 Prompt 明确要求：

事件必须包含：

人物
行为
具体内容

并加入正反例对照。

显著提高 Event 的信息密度，为 Embedding 与后续检索提供更高质量的数据。

新增：

created_at

为每个事件记录时间戳。

时间维度正式加入 Memory。

这是 Hybrid Retrieval 中时间衰减算法的重要基础。

新增：

load_all_events()

Context Builder 不再依赖 Event Manager 的预过滤。

统一获取全部事件后自行综合评分。

进一步降低模块耦合。

semantic_memory.py

新增：

compute_similarity_scores()

与原有：

find_semantically_relevant()

职责分离。

compute_similarity_scores：

仅负责计算全部事件的语义相似度。

不负责：

Top-K
阈值过滤

真正做到：

Embedding 模块只负责"计算"，排序交给 Retrieval。

进一步提高模块职责单一性。

context_builder.py

完成核心重构。

正式成为整个 Memory Pipeline 的检索中心。

负责：

获取全部事件
计算语义分数
计算时间衰减
综合 Importance
最终排序
Prompt Budget 控制

真正实现：

Memory

↓

Hybrid Retrieval

↓

Context Builder

↓

Prompt
三、时间衰减机制

引入：

指数衰减（Exponential Decay）。

采用：

半衰期 = 7 天

越新的事件：

权重越高。

越久远的事件：

影响自然减弱。

更符合真实的人类记忆规律。

四、动态权重分配

当：

query_text == None

时。

自动将：

Semantic Weight

重新分配给：

Importance
Recency

避免语义维度失效导致整体评分下降。

提高 Retrieval 的鲁棒性。

五、真实测试与调参

测试过程中发现：

一条：

Importance 很高
刚发生

的事件。

会压过：

语义高度相关但二十天前发生的事件。

经验证：

这不是程序 Bug。

而是 Hybrid Retrieval 权重配置产生的真实结果。

进一步确认：

Semantic Similarity 已正常工作。

后续需要根据真实使用情况持续调参。

目前：

SEMANTIC_WEIGHT

IMPORTANCE_WEIGHT

RECENCY_WEIGHT

全部定义为 Context Builder 顶部常量。

方便后续快速实验不同配置。

六、本日成果

完成：

 Hybrid Retrieval
Semantic + Importance + Recency 综合评分
Event 时间戳
 Event Prompt 优化
 Embedding 模块职责拆分
 Context Builder 核心重构
 指数时间衰减
 动态权重分配
 Memory Pipeline 持续优化
Day14 总结

今天最大的成果，是完成了 Memory V2 的 Hybrid Retrieval 系统。

AI 在回忆历史事件时，不再仅依赖语义相似度，而是综合考虑事件的重要程度、发生时间以及语义相关性，使整个记忆检索过程更加接近真实的人类记忆机制。

同时，对 Event Extraction、Embedding 模块以及 Context Builder 进行了进一步解耦与优化，使 Memory Pipeline 更加稳定、清晰且易于后续扩展。
