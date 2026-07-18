# Day26 开发日志

日期：2026-07-17

## 今日目标

在情绪、语音、Live2D、记忆和主动聊天逻辑已经稳定后，开始解决项目根目录臃肿、模块职责过大和导入关系难以继续维护的问题。今天的目标是把业务代码整理为正式的 Python 功能包，拆出大型模块中已经成熟且边界清晰的职责，同时保持原启动命令、本地配置和现有功能完全兼容。

## 完成内容

### 1. 建立统一的应用功能包

- 新建 `anime_assistant/` 主包，并按业务能力划分十个子包：
  - `ai`：AI 客户端、回复生成和兜底；
  - `character`：角色行为、资料与关系；
  - `conversation`：对话编排、意图、路由和上下文；
  - `emotion`：情绪判断、信号与状态转换；
  - `infrastructure`：配置、路径、日志、数据模型与存储；
  - `live2d`：模型加载、画布、参数控制与调参；
  - `memory`：短期、长期、事件与语义记忆；
  - `proactive`：主动聊天及交互状态追踪；
  - `speech`：TTS 服务、worker、文本与音频处理；
  - `ui`：Qt 主窗口、工作线程和播放控制。
- 原本散落在仓库根目录的业务文件全部迁入对应功能包，Git 保留文件移动历史。
- 人工 Live2D 诊断脚本移入 `scripts/`，与自动化测试和生产模块分离。

### 2. 保持启动方式兼容

- 根目录继续保留 `main.py` 与 `main_gui.py`，但它们现在只是轻量兼容入口。
- 控制台真实入口迁到 `anime_assistant.console`。
- 桌面窗口真实入口迁到 `anime_assistant.ui.main_window`。
- 用户仍可继续执行 `py -3.14 main_gui.py`，不需要记忆新的模块命令。
- 所有内部导入统一改为 `anime_assistant.*` 绝对路径，不再依赖运行时当前目录。

### 3. 兼容旧本地 TTS 配置

- Style-Bert-VITS2 与 GPT-SoVITS worker 迁入 `anime_assistant/speech/`。
- 示例配置更新为新的包内 worker 路径。
- 配置加载层增加旧路径迁移：已经存在且被 Git 忽略的 `settings.json` 即使仍记录旧文件名，也会在运行时自动转换到新位置。
- 新增测试确认旧路径迁移，不要求用户手工修改包含私密 API Key 的本地配置。

### 4. 拆分语音服务的纯处理职责

- 从大型 `speech/service.py` 中抽出 `speech/text.py`：
  - 舞台动作清理；
  - 日文假名检测；
  - 中文/日文句子分段与长度限制。
- 抽出 `speech/audio.py`：
  - `SpeechAudio` 数据结构；
  - WAV 合并；
  - 停顿插入；
  - Live2D 真实音频嘴型包络计算。
- `speech/service.py` 只继续负责翻译器、各 TTS 后端、常驻 worker 生命周期、重试、降级和队列编排。
- 为保持兼容，原来从 `speech.service` 导入的公共名称仍然可用，原测试和调用方无需同步改写。

### 5. 拆分 Qt 界面与 Live2D 画布

- `ui/workers.py` 独立管理 `ChatWorker`、主动消息桥接和 TTS 信号桥接。
- `ui/playback.py` 独立管理内存 WAV 队列、QtMultimedia 状态切换和嘴型响度回调。
- `live2d/canvas.py` 独立管理可选 Live2D/OpenGL 依赖、模型画布、持续刷新和参数写入。
- `ui/main_window.py` 更专注于窗口布局、对话状态、控件事件和各服务之间的连接。
- Live2D 不可用时仍保留原来的纯聊天降级行为。

### 6. 统一情绪信号协议

- 新增 `emotion/signals.py`，集中定义：
  - 持久心情和短暂 modifier 的默认持续轮数；
  - 完整的本轮情绪信号结构；
  - 主心情、modifier 和 `voice_style` 的写入方法；
  - 是否存在有效即时情绪信号的判断。
- `emotion/manager.py` 继续保留语义候选、AI 安全校准和状态机，但不再自行重复维护信号结构。
- 正常聊天、主动聊天、启动问候、Live2D 与 TTS 继续共享同一套情绪字段，不改变 Day25 已确认的表现。

### 7. 增加架构边界回归测试

- 新增 `tests/test_package_layout.py`。
- 自动检查十个功能包均可正常导入。
- 检查根目录只保留兼容启动入口，关键旧业务模块不会重新出现。
- 检查默认 TTS worker 路径确实指向存在的包内文件。
- README 和架构文档同步记录功能包职责、模块边界与未来新增代码的放置规则。

## 关键结论

### 为什么现在适合拆分

项目的情绪、语音和 Live2D 已经过多轮真实测试，职责与数据流已经相对稳定。此时拆分主要是在移动成熟边界，而不是一边探索功能一边调整目录，因此风险可由现有回归测试控制。若继续把新能力堆在根目录和单个大文件中，后续接入 WebSocket、多客户端或更多 TTS 后端时，修改范围会越来越难判断。

### 为什么没有一次性彻底重写

本次采用渐进式重构：先建立功能包，再抽取无状态工具、Qt 适配层和统一信号协议，同时保留原 façade 与启动入口。这样每个阶段都能独立提交和回归，出现问题时容易定位，也不会迫使所有调用方一次性迁移。

### 为什么要保留根目录入口

用户已经形成 `py -3.14 main_gui.py` 的测试习惯，README、编辑器任务和外部快捷方式也可能引用该命令。保留两份很小的转发文件几乎没有维护成本，却能避免架构整理变成使用方式上的破坏性更新。

## 验证结果

- 完整 `unittest` 回归共 139 项，全部通过。
- 新增 3 项包结构边界测试，全部通过。
- Python 3.14 `compileall` 编译检查通过。
- `main.py`、`main_gui.py`、情绪 façade 和语音 façade 导入冒烟测试通过。
- 旧 TTS worker 配置迁移测试通过。
- 情绪混合判断固定对话基线全部通过。
- 语音完整批次、重启重试、Aivis 降级和嘴型包络测试全部通过。
- `git diff --check` 与两次提交前的暂存区检查通过。
- 本地 `settings.json`、API Key、用户状态、训练数据、授权音频和模型权重均未进入提交。

## GitHub 提交

开发分支：`codex/day26-modular-architecture`

- `590119a` — `day26: organize modules into feature packages`
- `2a4047e` — `day26: split UI speech and emotion responsibilities`
- 文档与本日志使用独立的 `day26: document modular architecture` 提交。

## 后续方向

- 在真实 GUI、GPT-SoVITS 和 Live2D 联合测试稳定后再合并 Day26 分支。
- 继续把 `emotion/manager.py` 拆成“语义候选策略”和“状态生命周期”两个模块。
- 继续把 `speech/service.py` 中的 Aivis、Style-Bert-VITS2 与 GPT-SoVITS 客户端拆为独立后端适配器。
- 将 `ui/main_window.py` 的聊天 HTML 渲染与设置/调参窗口连接进一步抽离。
- 为包之间建立更明确的应用事件结构，为以后接入 WebSocket、网页端、手机端或 OBS 渲染端做准备。
- 拆分期间继续以固定情绪对话集、TTS 单元测试和真实 Live2D 观察三层验证为准，不为追求文件变小而改变已确认的角色表现。
