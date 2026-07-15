# Anime Assistant

一个以角色人设、长期记忆和 Live2D 表现为核心的本地 AI 聊天助手。项目同时提供控制台和 PySide6 桌面界面，默认使用 DeepSeek 的 OpenAI 兼容 API。

## 已有功能

- 流式聊天、角色开场白和失败兜底。
- 用户姓名、昵称、喜好和厌恶等资料记忆。
- 情绪、精力、好感、信任和熟悉度状态。
- 事件提取、中文语义检索和长期对话摘要。
- 根据重要事件、情绪和空闲时间主动发起对话。
- 可选 Live2D 立绘、情绪参数映射和真实音频振幅嘴型。
- 可选 Mio 本地 Style-Bert-VITS2 / AivisSpeech 日语语音；中文回复在后台转成自然日语后发声。
- JSON 原子保存、备份恢复和本地日志。

语义模型会在启动后后台预热；预热完成前自动使用轻量词面检索，不阻塞聊天首字。事件提取和长期摘要在顺序后台队列中执行；摘要默认每累计 10 条溢出消息批量生成一次。

## 环境

建议使用 Windows 和 Python 3.14。项目当前使用的 `live2d-py==0.7.0.4`
已适配这一运行环境；旧版 `0.6.1.1` 在 Python 3.14 下可能因缺少 wheel 而安装失败。

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
3. 根据需要调整模型、主动聊天、Live2D 和语音后端配置。

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
| `chat_thinking_enabled` | 日常主对话是否启用 DeepSeek 思考模式；关闭时响应更快且避免思考耗尽短回复预算 | `false` |
| `chat_history_max_messages` | 主回复参考的最近消息数；限制旧回复对当前口吻的影响 | `8` |
| `live2d_model_path` | `model3.json` 绝对路径，或相对项目根目录的路径 | 空，即禁用 Live2D |
| `live2d_waiting_motion_intensity` | 等待语音时摆头与物理头发动作倍率（0～2） | `1.0` |
| `live2d_waiting_gaze_intensity` | 等待语音时视线游移幅度倍率（0～2） | `1.0` |
| `live2d_waiting_motion_speed` | 待机头部、身体、眉毛和视线节奏倍率 | `1.4` |
| `tts_enabled` | 启用语音 | `true` |
| `tts_backend` | 语音后端：`aivis`、`mio_style_bert_vits2` 或 `mio_gpt_sovits_v2proplus` | `aivis` |
| `tts_fallback_to_aivis` | Mio 本地模型失败时是否整条回退 AivisSpeech | `true` |
| `tts_translate_to_japanese` | 中文回复是否另行翻译为日语发声 | `true` |
| `tts_speed_scale` | 语速倍率 | `1.0` |
| `tts_volume_scale` | 音量倍率 | `1.0` |
| `aivis_endpoint` | 本地 AivisSpeech Engine 地址 | `http://127.0.0.1:10101` |
| `aivis_timeout_seconds` | 单个语音片段的最长合成等待时间 | `60` |
| `aivis_max_chars_per_request` | 单次合成的最大日语字符数 | `56` |
| `aivis_mood_speakers` | 五种心情对应的 AivisSpeech Style ID | コハク的四种风格 |
| `mio_tts_model` | Mio `.safetensors` 模型路径（相对项目根目录或绝对路径） | 第一版 2000 步模型路径 |
| `mio_tts_python` | Style-Bert-VITS2 独立 Python 3.10 路径 | `data/training_tools/.../python.exe` |
| `mio_gpt_sovits_gpt_weights` | Mio GPT-SoVITS 语义权重 | V2ProPlus GPT e15 |
| `mio_gpt_sovits_sovits_weights` | Mio GPT-SoVITS 声学权重 | V2ProPlus SoVITS e8 |
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

### Mio 本地语音与 AivisSpeech

将 `tts_backend` 设为 `mio_style_bert_vits2` 或
`mio_gpt_sovits_v2proplus` 后，GUI 会在第一次需要语音时启动隐藏的
Python 3.10 后台进程，并把 Mio 模型常驻内存；主程序仍可使用 Python 3.14
和 Live2D，不需要在同一环境安装两套互相冲突的依赖。模型和训练环境位于
被 Git 忽略的 `data/` 目录，因此换电脑后需要单独复制或重新准备这些本地
文件。窗口关闭时后台语音进程会一并退出。

Style-Bert-VITS2 第一版只有 `Neutral` 风格。GPT-SoVITS V2ProPlus 后端固定
使用 GPT e15 与 SoVITS e8，并根据 `neutral`、`happy`、`shy`、`sad`、
`tired` 选择对应的 Mio 原声参考片段，使语音情绪与 Live2D 心情同步。

当 `tts_fallback_to_aivis` 为 `true` 时，本地模型缺失、启动失败或合成超时
会让整条回复重新交给 AivisSpeech，不会混播两种音色或只播放前半句。

先启动 AivisSpeech，并确认语音合成引擎监听 `127.0.0.1:10101`，再启动
`main_gui.py`，即可使用 AivisSpeech 或作为 Mio 的降级后端。文字回复不会等待语音：日语转换和语音合成都在后台完成；整条
回复的所有语音片段准备完毕后会在后台合并为一个完整 WAV，再一次性交给
QtMultimedia 播放，不会只播放前半段，也避免分段切换音频源导致界面卡死。
等待合成期间，Live2D 会进入安静的思考待机状态，以平滑视线、眉毛、头部和
身体微动带动模型物理头发；语音开始后自动切换到真实音频嘴型。
播放时 Live2D 嘴型由 WAV 的实际短时响度驱动；引擎未启动、翻译失败或任一
片段合成失败时，整条语音会取消并保留纯文字聊天，不影响对话主流程。

示例配置默认使用「コハク」：平静对应ノーマル，开心和害羞对应あまあま，
低落对应せつなめ，疲惫对应ねむたい。以后导入 Mio 的 `.aivmx` 模型后，
只需将 `aivis_mood_speakers` 中的 Style ID 换成 Mio 的 ID。

GUI 顶部的“调表情”窗口提供“待机摆头/头发强度”滑块。`0.00×` 为关闭，
`1.00×` 为推荐值，最高 `2.00×`；拖动时实时预览，点击“保存待机强度”后
写入本地 `settings.json`。“待机视线游移强度”使用相同倍率范围，并可通过
“保存视线强度”独立保存。
“待机动作速度”范围为 `0.50×～2.00×`，默认 `1.40×`；修改速度不会重置
当前动作相位，因此实时预览时不会突然跳动。

## 情绪状态机

每轮回复前会先区分“用户当前感受”和“Mio 应有的反应”，因此用户难过时
Mio 会表现为担心和关心，而不是简单复制成自己的低落。持久心情使用
`mood + mood_strength`，并叠加有独立持续轮数的 `worried`、`touched`、
`curious`、`surprised`、`annoyed` 短暂反应。心情会按对话轮数和真实时间
自然淡出，轻微的正负转变需要连续信号，候选信号超过有效期会自动清除。

疲劳由精力计算为连续强度，并使用不同的进入/退出阈值避免边界闪烁。
Live2D 参数、状态栏、回复语气和 TTS 参考音频/轻微语速调整都读取同一份
情绪状态。

## 测试

```powershell
python -m unittest discover -s tests -v
```

`test_live2d_load.py` 和 `test_live2d_glfw.py` 是需要真实显示器与 OpenGL 环境的人工诊断脚本，不属于自动化测试。模型路径通过第一个命令行参数或 `LIVE2D_MODEL_PATH` 环境变量传入。

## 数据与隐私

运行时数据保存在 `data/`，包括聊天历史、用户资料、事件记忆、关系和情绪状态。除静态角色设定 `data/persona.json` 和目录占位文件外，这些内容都不应该进入版本库。

如果仓库在本次整理前已经推送到远程，旧 Git 历史中仍可能包含这些文件。`.gitignore` 和停止跟踪只保护今后的提交；清理已发布历史需要单独评估并使用 `git filter-repo` 等工具重写历史。

详细模块边界、对话时序和并发约束见 [docs/architecture.md](docs/architecture.md)。
