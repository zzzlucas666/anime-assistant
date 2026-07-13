# Day3 开发日志

Day 3 —— AI介入
今日目标

接入 DeepSeek API。

学习内容
1. API 原理

理解：

程序
↓
API
↓
DeepSeek
↓
AI回复

工作流程。

2. OpenAI SDK

安装：

pip install openai

学习：

from openai import OpenAI

调用模型。

3. chat.py

创建：

chat_with_ai()

负责：

发送消息
接收回复
4. 连续聊天

学习：

while True

和：

break

实现：

持续聊天
exit退出

功能。

5. Git 安全

学习：

API Key
不能上传GitHub

理解：

.gitignore
settings.example.json

的作用。

经典 Bug
ImportError
say_hello不存在

修复成功。

JSONDecodeError
{
    "api_key": "xxx",
}

最后一个逗号导致报错。

修复成功。

main() 未执行

忘记写：

if __name__ == "__main__":
    main()

修复成功。

Day 3 成果

Anime Assistant v0.2 发布

实现：

 DeepSeek API调用

 AI回复

 连续聊天

 exit退出

 GitHub版本管理

 配置安全优化
