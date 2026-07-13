# Day2 开发日志

Day 2 —— 项目配置系统
今日目标

让程序拥有配置文件。

学习内容
1. JSON

创建：

{
    "assistant_name": "Anime Assistant",
    "model": "deepseek-chat"
}

理解：

JSON
=
配置数据存储格式
2. 配置读取

创建：

config_loader.py

学习：

json.load()

读取配置文件。

3. 模块化思想

理解：

main.py
负责启动

config_loader.py
负责读取配置
第一次 Debug

遇到：

JSONDecodeError

学习：

查看报错
定位问题
修复问题

流程。

Day 2 成果

程序能够：

读取配置文件
显示助手名称
