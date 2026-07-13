# Day6 开发日志

为 Anime Assistant 增加角色人格系统和情绪系统。
项目名称
Anime Assistant
Day6 - Persona + Emotion + Profile System
让 AI 不再只是普通聊天机器人，而是拥有固定身份的「秋山澪」。

一、角色人格系统（Persona）
新增
data/persona.json

用于存储：

{
    "name": "秋山澪",
    "identity": "...",
    "personality": "...",
    "likes": [ ],
    "dislikes": [ ]
}
实现

新增：

load_persona()
build_system_prompt()

功能：

启动时读取角色设定
↓
动态生成 System Prompt
↓
让模型始终扮演秋山澪
收获

理解了：

Prompt ≠ 写死文本

Prompt
=
程序动态生成
二、情绪系统（Emotion）
新增
data/emotion_state.json

结构：

{
    "mood": "happy",
    "affection": 50,
    "energy": 100
}
新增文件
emotion_manager.py

实现：

load_emotion()
save_emotion()
收获

理解了：

角色人格(Persona)
≠
角色状态(Emotion)

例如：

人格：
永远是秋山澪

状态：
开心
害羞
疲惫
难过

可以变化。

三、情绪接入 Prompt

实现：

build_system_prompt(
    persona,
    emotion
)

新增：

当前情绪状态：
- mood
- affection
- energy
收获

理解了：

Emotion
↓
Prompt
↓
影响回复风格

未来：

Live2D表情
语音语调

也会依赖 Emotion。

四、用户档案系统（Profile）
新增
data/user_profile.json

结构：

{
    "name": "Lucas",
    "likes": [ ],
    "dislikes": [ ],
    "nickname": ""
}
新增
profile_manager.py

实现：

load_profile()
save_profile()
update_profile()
收获

理解了：

聊天记录
≠
用户档案

聊天记录记录：

发生过什么

用户档案记录：

用户是谁
五、Profile 接入 Prompt

完成：

build_system_prompt(
    persona,
    emotion,
    profile
)

实现：

Persona
+
Emotion
+
Profile

三合一 Prompt 架构。

收获

理解了：

长期记忆

与：

上下文记忆

的区别。

六、AI动态打招呼系统

实现：

generate_greeting()

功能：

启动程序
↓
AI生成一句新的问候语
↓
根据用户资料变化

例如：

欢迎回来呀，Lucas♪

而不是：

Hello

固定文本。

收获

理解了：

AI不仅能回复
还能主动生成内容
七、记忆清理系统

新增：

clean_history()

功能：

if msg.get("content")

过滤：

None
空消息
异常数据

同时实现：

MAX_HISTORY = 50

自动裁剪历史记录。

收获

理解了：

代码修好
≠
数据正确

很多 Bug 来源于历史数据污染。

今日踩坑记录
坑1
chat_with_ai()

忘记 return

导致：

Mio:
None
坑2
generate_greeting()

函数写了一半

没有发送请求

没有 return

导致：

Anime Assistant:
None
坑3

历史记录中出现：

{
    "role": "assistant",
    "content": null
}

导致：

Invalid assistant message

API报错。

坑4

Profile误识别

我喜欢什么？

↓

{
    "likes": ["什么？"]
}

这也成为 Day7 的重点优化方向。

Day6 最终成果

目前 Anime Assistant 已拥有：

✓ Persona System
✓ Emotion System
✓ Profile System
✓ Memory System
✓ Dynamic Greeting
✓ History Cleaner

整体架构：

                Persona
                   │
                   ▼
User ──► Memory ─► AI
                   ▲
                   │
              Emotion
                   ▲
                   │
                Profile
