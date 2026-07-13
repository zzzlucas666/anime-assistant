# Day15 开发日志

Day15 开发日志
Day15 - GUI Interface & Memory Retrieval Optimization

今天完成了项目的首个图形化界面（GUI），同时继续优化 Memory V2 的 Prompt 与 Hybrid Retrieval，使 AI 在检索历史记忆时更加准确、自然，并进一步降低无关记忆干扰当前对话的问题。

一、GUI 界面

新增项目图形化聊天界面。

相比之前仅能通过命令行（CLI）进行交互，现在已经能够通过 GUI 与角色进行聊天。

GUI 的加入意味着：

项目拥有了更加友好的交互方式
为后续接入 Live2D 提供了界面基础
后续 UI 风格可逐步演进，无需再次重构整个聊天框架

项目开始从开发工具逐渐向真正的应用程序演进。

二、Memory Prompt 优化

继续优化 Chat Prompt。

重新收紧 Memory 的引用策略。

之前 Prompt：

可以自然地提起相关记忆。

这种表达仍然给模型留下了较大的自由发挥空间。

现修改为：

只有与当前话题真正相关时，才允许引用对应记忆；无关内容应完全忽略，不主动提及。

Memory 的使用原则进一步明确。

有效减少 AI 为了"利用记忆"而强行插入无关历史内容的问题。

三、增加最高优先级行为规则

新增两条 Runtime 核心约束：

1. 当前对话优先

当前正在进行的聊天内容永远优先于历史记忆。

AI 不允许因为历史事件而忽略当前用户真正的问题。

2. 保持人格一致性

AI 必须保持自身设定一致。

已经说过的内容：

不重复编造
不随意修改
不制造矛盾设定

进一步提升角色人格的一致性与连续性。

四、Hybrid Retrieval 持续优化

继续完善 Context Builder。

新增：

MIN_SEMANTIC_RELEVANCE_WHEN_QUERY = 0.25

当用户提出明确问题时：

系统已经进入：

Semantic Retrieval。

此时：

若某条事件：

Semantic Similarity

低于：

0.25

即使：

Importance 很高
刚刚发生

也会直接排除。

避免：

Hybrid Retrieval 被：

Importance

或者：

Recency

强行拉偏。

五、Memory 检索准确率提升

实际测试验证：

此前：

即使用户讨论完全无关的话题。

某些：

Importance 很高

且：

刚发生

的事件。

仍有可能进入 Prompt。

现在：

新增 Semantic Threshold 后。

这类事件将直接过滤。

Memory 真正开始：

只回忆真正相关的经历。

进一步提高 Retrieval Precision。

六、本日成果

完成：

 GUI 图形聊天界面
 Memory Prompt 重构
当前对话优先规则
 Persona 一致性规则
 Semantic Threshold
 Hybrid Retrieval 精度优化
 Memory V2 持续优化
