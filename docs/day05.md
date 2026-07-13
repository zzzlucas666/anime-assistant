# Day5 开发日志

引入 JSON 持久化存储

学习并使用 json 模块，实现数据持久化：

json.dump()
json.load()

实现功能：

将聊天记录保存到本地文件
从文件恢复历史对话
 创建 memory_manager 模块

新增模块：

memory_manager.py

核心功能：

save_memory(conversation_history)
load_memory()

作用：

✔ 保存对话历史到本地 JSON
✔ 启动程序时自动加载历史记录
实现长期记忆机制

在main.py 中加入

conversation_history = load_memory()

并在每次对话后

save_memory(conversation_history)

实现效果

AI 可以“跨程序记住用户”
重启后仍·保留聊天上下文
 接入DeepSeek Chat API(增强版调用)

优化chat模块

client.chat.completions.create(
    model=model,
    messages=conversation_history
)

实现：

支持完整message history
支持多轮对话上下文理解
修复关键问题(Bug Fix)
 问题1：JSON格式错误

修复：

trailing comma 导致 JSONDecodeError
问题2：Git keep 文件错误

修复：

.gitkeep.json → .gitkeep
 问题3：Git 未提交误解

理解：

git add ≠ push
必须 commit 才会更新 GitHub
今日关键收获（核心认知）
 1. AI 记忆本质

AI 记忆不是“AI自己记住”，而是：

数据存储 + 历史传递 + 上下文注入
 2. Git 三阶段模型
working directory → staging → commit → push
 3. 项目结构意识建立

开始理解真实工程结构：

config/   配置
data/     数据（记忆）
ai/       模块逻辑
main.py   入口
 4. 相对路径理解
data/file.json
= 基于当前运行目录查找
 Day 5 成果总结

✔ 实现 AI 长期记忆系统
✔ 可跨会话保留用户信息
✔ 完成 JSON 数据持久化
✔ 完成 API + memory 系统整合
✔ Git 工作流基本掌握

 项目进化状态
Day 1 → 项目初始化
Day 2 → 配置系统
Day 3 → API接入
Day 4 → 聊天循环
Day 5 → 记忆系统（重大升级）
 当前版本
Anime Assistant v0.4

新增能力：

 记住用户
保存聊天记录
 重启不丢失上下文
 多轮对话能力
