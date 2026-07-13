# Day4 开发日志

Day 4 —— 记忆系统诞生
日期
Day 4
今日目标

让 Anime Assistant 记住当前会话中的聊天内容。

实现：

You
我叫Lucas

↓

You:
我叫什么名字？

↓

Anime Assistant:
你叫Lucas
 学习内容
1. AI为什么能记住上下文？

最开始的聊天流程：

用户输入
↓
发送一句话
↓
AI回复

发送的数据：

[
    {"role": "user", "content": "你好"}
]

问题：

每次请求都是独立的
AI看不到之前的聊天

所以无法记忆。

2. 理解 messages 机制

学习：

messages

实际上是：

[
    {"role": "user", "content": "你好"},
    {"role": "assistant", "content": "你好呀"},
    {"role": "user", "content": "我叫Lucas"}
]

理解：

AI并不是拥有真正记忆

而是重新阅读聊天历史

这是：

ChatGPT
DeepSeek
Claude
Gemini

等聊天AI的基础原理。

3. 创建聊天历史列表

在：

main.py

新增：

conversation_history = []

用于保存聊天记录。

学习：

append()

方法。

例如：

conversation_history.append(
    {
        "role": "user",
        "content": user_message
    }
)

理解：

聊天记录
=
一个不断增长的列表
4. 改造 chat.py

旧版本：

messages=[
    {"role": "user", "content": message}
]

只能发送单条消息。

升级为：

messages=message

直接发送整个聊天历史。

实现：

单轮聊天
↓
多轮聊天

升级。

5. 保存 AI 回复

新增：

conversation_history.append(
    {
        "role": "assistant",
        "content": reply
    }
)

形成：

[
    {"role":"user","content":"你好"},
    {"role":"assistant","content":"你好呀"},

    {"role":"user","content":"我叫Lucas"},
    {"role":"assistant","content":"很高兴认识你"}
]

理解：

完整对话
=
用户消息
+
AI消息
重要认知

今天最大的收获：

AI的记忆
≠
AI真的记住了

而是：

历史消息
↓
再次发送
↓
模型阅读
↓
继续回复

这是目前所有主流聊天AI的基础机制。

 GitHub 安全优化

发现问题：

settings.json
包含API Key

学习：

.gitignore

作用。

创建：

settings.example.json

作为公开配置模板。

执行：

git rm --cached config/settings.json

成功将：

settings.json

从仓库移除。

理解：

从Git索引删除
≠
删除本地文件
 遇到的问题
问题1
为什么AI能记住Lucas？

原因：

发送了完整聊天历史
问题2
退出程序后
聊天记录去哪了？

答案：

保存在内存(RAM)

程序关闭后消失

由此引出了：

长期记忆系统

需求。

 Day 4 成果

Anime Assistant v0.3 发布

实现：

 会话记忆

 多轮对话

 保存用户消息

 保存AI消息

上下文理解

 GitHub安全优化

 配置文件规范化
