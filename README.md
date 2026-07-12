# Anime Assistant

一个以角色人设、长期记忆和 Live2D 表现为核心的本地 AI 聊天助手。项目同时提供控制台和 PySide6 桌面界面，默认使用 DeepSeek 的 OpenAI 兼容 API。

## 已有功能

- 流式聊天、角色开场白和失败兜底。
- 用户姓名、昵称、喜好和厌恶等资料记忆。
- 情绪、精力、好感、信任和熟悉度状态。
- 事件提取、中文语义检索和长期对话摘要。
- 根据重要事件、情绪和空闲时间主动发起对话。
- 可选 Live2D 立绘、情绪参数映射和模拟嘴型。
- JSON 原子保存、备份恢复和本地日志。

语义模型会在启动后后台预热；预热完成前自动使用轻量词面检索，不阻塞聊天首字。事件提取和长期摘要在顺序后台队列中执行；摘要默认每累计 10 条溢出消息批量生成一次。

## 环境

建议使用 Windows 和 Python 3.12。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

`requirements.txt` 只包含控制台聊天的必需依赖。按需安装可选能力：

```powershell
# 桌面 GUI
pip install -r requirements-gui.txt

# 本地语义记忆（体积较大）
pip install -r requirements-memory.txt

# GUI + Live2D/OpenGL 及诊断工具
pip install -r requirements-live2d.txt

# 一次安装全部功能
pip install -r requirements-all.txt
```

## 配置

1. 复制 `config/settings_example.json` 为 `config/settings.json`。
2. 填写 `api_key`。
3. 根据需要调整模型、主动聊天和 Live2D 配置。

最小配置：

```json
{
  "assistant_name": "Anime Assistant",
  "model": "deepseek-chat",
  "api_key": "YOUR_API_KEY_HERE"
}
```

常用可选字段：

| 字段 | 作用 | 默认值 |
| --- | --- | --- |
| `base_url` | OpenAI 兼容 API 地址 | `https://api.deepseek.com` |
| `live2d_model_path` | `model3.json` 绝对路径，或相对项目根目录的路径 | 空，即禁用 Live2D |
| `proactive_check_interval_minutes` | 主动聊天检查周期 | `5` |
| `proactive_idle_threshold_minutes` | 空闲时间参考阈值 | `30` |
| `proactive_min_interval_minutes` | 两次主动消息最小间隔 | `120` |
| `proactive_max_per_day` | 每日主动消息上限 | `3` |

`settings.json` 已被 Git 忽略，不要把真实 API Key 写进示例文件。

## 启动

```powershell
# 控制台
python main.py

# 桌面 GUI
python main_gui.py
```

如果未安装 Live2D 依赖、未配置模型，或模型路径无效，GUI 会自动退化为纯聊天界面。

## 测试

```powershell
python -m unittest discover -s tests -v
```

`test_live2d_load.py` 和 `test_live2d_glfw.py` 是需要真实显示器与 OpenGL 环境的人工诊断脚本，不属于自动化测试。模型路径通过第一个命令行参数或 `LIVE2D_MODEL_PATH` 环境变量传入。

## 数据与隐私

运行时数据保存在 `data/`，包括聊天历史、用户资料、事件记忆、关系和情绪状态。除静态角色设定 `data/persona.json` 和目录占位文件外，这些内容都不应该进入版本库。

如果仓库在本次整理前已经推送到远程，旧 Git 历史中仍可能包含这些文件。`.gitignore` 和停止跟踪只保护今后的提交；清理已发布历史需要单独评估并使用 `git filter-repo` 等工具重写历史。

详细模块边界、对话时序和并发约束见 [docs/architecture.md](docs/architecture.md)。
