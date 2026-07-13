# Day7 开发日志

## 今日目标

让秋山澪不再只会机械地匹配固定关键词，而是能够理解用户的真实意图。

---

## 完成内容

### 1. 引入 Intent Analyzer

新增：

* detect_intent()

系统能够识别用户当前意图。

例如：

用户：

我喜欢什么？

识别结果：

{
"intent": "get_profile",
"confidence": 0.95
}

用户：

最近一直在听摇滚乐

识别结果：

{
"intent": "set_profile",
"confidence": 0.92
}

---

### 2. 建立 Router 逻辑

新增：

* handle_intent()

将用户请求分流处理。

流程：

用户输入
↓
Intent识别
↓
Router
↓
对应模块

实现了系统从"关键词判断"向"意图驱动"转变。

---

### 3. Profile查询优化

实现：

* 我喜欢什么
* 我讨厌什么
* 我的昵称是什么
* 我的名字是什么

不再依赖固定问法。

---

### 4. Memory清理机制

新增：

clean_history()

解决历史记录中出现：

* None
* 空字符串
* 无效消息

导致API报错的问题。

---

## 遇到的问题

### None消息污染History

由于Greeting函数返回异常，

conversation_history中出现：

{
"role": "assistant",
"content": null
}

导致DeepSeek返回：

400 Invalid assistant message

最终通过：

clean_history()

解决。

---

## 今日收获

第一次接触：

Intent
Router
Memory Cleaning

理解了：

AI系统 ≠ 直接调用大模型

真正的AI项目需要：

输入
↓
理解
↓
路由
↓
处理
↓
回复

完整链路。
