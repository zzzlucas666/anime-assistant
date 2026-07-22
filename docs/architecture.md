# Architecture

## 分层

```text
main.py / main_gui.py（兼容入口）
        │
        ├─ anime_assistant.console
        └─ anime_assistant.ui.main_window
                    │
        ┌───────────┼────────────┐
        │           │            │
 conversation/   proactive/   character + emotion
        │           │            │
        ├──────── memory/ ────────┤
        │           │            │
       ai/       speech/       live2d/
        └───────────┬────────────┘
                infrastructure/
```

- **入口层**：根目录 `main.py` 与 `main_gui.py` 只做兼容转发，真实入口分别是 `anime_assistant.console` 与 `anime_assistant.ui.main_window`。
- **界面层**：`ui/main_window.py` 负责窗口状态和交互，`ui/workers.py` 隔离后台对话线程，`ui/playback.py` 负责顺序音频播放。
- **运行时层**：`runtime/application.py` 统一创建、启动和关闭应用服务，`runtime/turns.py` 分配当前轮次身份，`runtime/supervisor.py` 记录并协作取消后台任务。
- **应用层**：`conversation/orchestrator.py` 编排一轮正常对话；`proactive/initiative_engine.py` 评分并提交主动对话。两者不再拥有整个进程的生命周期。
- **角色与情绪层**：`character/` 管理人设、稳定档案和关系；`character/relationship_behavior.py` 是关系行为阈值的唯一来源；`emotion/rules.py` 保存本地词面规则，`emotion/planning.py` 负责候选与三种对话模式的即时规划，`emotion/calibration.py` 约束 AI 校准，`emotion/state.py` 负责持久状态转换，`emotion/manager.py` 仅保留兼容入口，`emotion/signals.py` 统一本轮情绪信号协议。
- **AI 适配层**：`ai/client.py` 创建 OpenAI 兼容客户端；`ai/prompts/` 生成五层角色提示；`ai/chat.py` 负责三种对话模式的请求、流式过滤和失败兜底。
- **记忆层**：`memory/` 管理短期历史、事件、长期摘要和语义检索；`conversation/context_builder.py` 组合这些数据。
- **语音层**：`speech/service.py` 只编排任务队列、重试和降级策略，`speech/backends.py` 封装 AivisSpeech 与两种 Mio 本地后端，`speech/translator.py` 隔离日语转换，`speech/style.py` 负责情绪到参考风格和语速的映射，`speech/text.py` 处理朗读文本，`speech/audio.py` 处理 WAV 合并和嘴型包络。
- **Live2D 层**：`live2d/canvas.py` 封装可选 OpenGL 画布，`live2d/controller.py` 管理参数动画与表情过渡。
- **基础设施**：`infrastructure/` 统一配置、绝对路径、日志、数据模型和原子 JSON 存储。

## 模块边界原则

- 根目录不再放业务模块；新增能力应进入对应的 `anime_assistant` 功能包。
- UI 不直接实现 AI、TTS 或情绪规则，只负责调用应用服务并通过 Qt 信号更新界面。
- `speech/service.py` 和 `emotion/manager.py` 只保留稳定外观；后端、翻译、语气策略、规则识别、规划、校准和状态转换必须由独立模块承担。
- 包间引用使用 `anime_assistant.*` 绝对导入，避免依赖当前工作目录。
- 默认配置中的脚本路径必须指向真实包内文件；旧本地配置由加载层迁移，不要求用户手改。
- `tests/test_package_layout.py` 保护这些边界，防止重构后悄悄退回根目录堆叠。

## 正常对话时序

每次启动问候、用户输入和主动消息先由 `TurnCoordinator` 生成形如
`turn-00000001-user` 的单调递增 `turn_id`。新轮次成为当前轮次时，监督器会向旧的
对话流、后处理、主动生成和语音任务发出协作取消；不能立即中断的网络或本地模型
推理允许自然返回，但返回值必须再次校验 `turn_id`。

1. `prepare_turn()` 在本地生成带置信度的情绪候选并选出安全基线，同时识别意图，必要时提取用户资料。
2. 在共享锁内写入用户消息，并取历史与上下文快照。
3. `stream_reply()` 在锁外使用快照和本轮反应提示生成流式回复；同一次回复末尾的 `<mio:...>` 控制标签由跨分块过滤器截获，只把可见文本交给 GUI。
4. `finalize_turn()` 先按可见回复措辞校准本地计划，再用通过白名单、范围和置信度校验的 AI 控制信息做语义校准，随后立即提交即时情绪与本句 `voice_style`，使状态栏、Live2D 与本轮 TTS 同步。
5. 单一顺序后台线程提取长期事件，先校验事实来源和用户原话证据，再保存 Memory Record v2；只有可信且未过期的确认事件可以更新关系和 context。正常聊天已有本地即时语气，因此迟到的事件标签不会覆盖当前轮。
6. 溢出历史先写入 `data/pending_summary.json`，累计 10 条后才在后台批量生成长期摘要。

## 五层 Prompt 架构

所有面向用户的角色回复都按固定顺序组合以下五层：

1. **Identity**：只包含运行期间不变的身份、稳定人格、表达习惯和兴趣边界，来源是 `data/persona.json`。
2. **Values**：定义真诚、陪伴、事实克制、个人边界和当前话题优先等决策原则，负责在规则冲突时提供稳定选择。
3. **Behavior**：由 Python 根据关系策略、精力、本轮情绪和对话模式生成温暖、开放、主动、玩笑、认真、外显强度和回复深度等语义倾向。
4. **Context**：承载本轮情绪、语义化关系阶段、稳定用户档案和带可信等级的相关记忆；明确声明这些内容只是数据，不能覆盖前面各层。
5. **Output Rules**：保留长度、口语形式、事实边界和内部情绪控制标签等最短输出契约。

`character/relationship_behavior.py` 仍是关系阈值的唯一来源；Prompt 不接收原始 `affection`、`trust` 和 `familiarity` 数字，而是接收转换后的“关系尚浅 / 熟悉朋友 / 亲近朋友”等行为语义。Dynamic State 同时进入 Behavior 和 Context：前者决定本轮如何表现，后者提供发生了什么的背景。

`chat`、`greeting` 和 `proactive` 模式共享 Identity 与 Values，只替换动态行为、场景上下文和输出契约。交互式 `<mio:...>` 标签仅允许出现在普通聊天；问候和主动消息即使调用方漏传开关，也会由构造器强制禁用。

五层 Prompt 只负责把既定状态自然表达出来，不能替代 Python 中的情绪 FSM、关系更新、记忆可信门禁、主动聊天冷却、TTS/Live2D 映射和标签白名单校验。

## 记忆治理

- 事件记录统一包含 `type`、`status`、`source`、`confidence`、`evidence`、`expires_at` 和 Embedding 版本信息。
- `user_explicit`、`user_corrected` 和 `system_observed` 可以进入可信记忆检索；AI 无法给出用户原话证据时，记录降级为 `ai_inferred + candidate`。
- `system_observed` 只作为中可信背景，默认不能改变关系状态，也不能覆盖或撤回优先级更高的用户明确档案。
- `candidate` 不参与提示词、主动聊天、情绪或关系状态更新，并在七天后过期；旧数据迁移为 `legacy_import + legacy`，继续可召回但不能再次改变关系。
- `temporary_context`、`emotional_episode` 和无明确日期的 `plan` 使用不同默认有效期；身份、喜好和重要关系事件不采用统一 TTL。
- 上下文注入优先使用已校验的用户原话，而不是 AI 撰写的事件摘要。
- 稳定档案以事实列表为源数据，顶层 `name`、`nickname`、`likes` 和 `dislikes` 只是兼容读取视图。用户纠正会把旧事实标为 `superseded` 或 `retracted`，不会抹去历史。
- 语义模型就绪后，后台任务以小批次补齐缺失或模型版本过期的向量；每批通过事件锁和原子 JSON 保存提交，不阻塞聊天路径。

## 情绪模型

- `user_mood` 描述用户透露的感受，`mood` 描述 Mio 的持久心情，两者不能直接复制。
- `modifier` 是担心、感动、好奇、惊讶、无奈等短暂反应，有独立强度和剩余轮数。
- `voice_style` 描述当前一句的声音表达，与持久 `mood` 分离；GPT-SoVITS 优先按它选择参考音频和语速。
- `mood_strength` 驱动 Live2D 参数幅度；`voice_style_strength` 控制本句语气幅度，两者变化都必须刷新表现层。
- 本地候选层为同一输入保留多个可能反应及分数，例如个人夸奖可以同时保留 `shy` 和 `happy`，再根据关系、当前心情和措辞调整排序，避免单一硬阈值。
- 正常回复的 AI 控制层复用主对话请求，不产生额外网络往返；只允许已声明的用户情绪、Mio 反应和声音风格，并要求最低置信度。
- 明确的用户痛苦和对 Mio 的直接负面表达由本地高置信度规则保护。AI 可以在同方向内细化 `concerned`、`reassuring` 或 `serious`，不能把这些场景改成 `happy`、`shy` 或 `cheerful`。
- 控制标签仅存在于流式传输末尾，不进入可见回复、TTS、聊天历史和长期记忆；缺失、无效或被截断时保留本地候选结果。
- 正负心情之间的轻微信号需要连续确认，候选状态带过期时间；无新触发时按轮数和时间淡出。
- `fatigue_strength` 是独立连续轴，疲惫主状态使用进入/退出双阈值防止边界抖动。

## 主动对话时序

1. 在锁内检查冷却，计算事件、情绪和空闲时间评分。
2. 根据触发事件、当前心情与空闲原因规划主动 `voice_style`，写入上下文快照后释放锁。
3. 在锁外生成 AI 消息，并按生成后的实际措辞校准主动情绪。
4. 重新加锁；如果用户在生成期间已说话，丢弃过时的主动消息。
5. 在消息展示和 TTS 入队前原子提交情绪、voice style、消息、冷却和事件通知状态。

## 启动问候时序

1. 读取持续 mood、精力和关系快照，规划问候 `voice_style`。
2. 使用共享五层 Prompt 的 `greeting` 模式生成一句开场白，再按实际文字校准担心、温暖或轻快等反应。
3. 在 GUI 首条消息、Live2D 刷新和 TTS 入队之前提交状态；启动问候不消耗精力。
4. 控制台入口使用同一套规划和持久化规则，避免两种入口行为分叉。

## 并发不变式

- GUI 与控制台必须共享 `ApplicationRuntime` 的服务创建、启动和关闭顺序，不得各自复制线程生命周期代码。
- 面向用户的异步结果必须携带 `turn_id`，且只能由当前轮次更新界面、实时情绪、关系或语音播放。
- 旧轮次长期事件可以在事实来源校验后落盘，但不得在迟到时覆盖当前档案、情绪、关系和 context。
- TTS 不为切换轮次强杀常驻模型；当前推理可自然结束，但旧 `turn_id` 的完整音频必须静默丢弃且不能误报为后端故障。
- 所有非 Qt 后台线程应登记到 `TaskSupervisor`，并提供任务名、作用域、可选轮次与协作取消信号。
- Orchestrator 和 InitiativeEngine 必须共享同一个历史列表与同一把状态锁。
- `save_memory()` 必须原地截断列表，不得让多个持有者分叉。
- 网络 AI 请求和长期摘要不得持有全局状态锁。
- 正常对话的事件提取和摘要任务必须在单一后台队列中按对话顺序执行。
- Embedding 回填不得持有状态锁进行模型推理，只允许在写回小批结果时短暂获取事件锁。
- Qt 控件只能在 GUI 主线程修改。
- 应用关闭时不得销毁仍在运行的 `ChatWorker` QThread。

## 回归基线

- `tests/emotion_dialogue_regression_cases.json` 是可读、可评审的固定对话数据集，锁定用户情绪、Mio 反应、Live2D modifier 与 TTS `voice_style` 的关键组合。
- `tests/test_emotion_dialogue_regression.py` 依次执行本地规划、回复措辞校准、控制标签解析和 AI 安全校准，验证最终信号而不是只测试某一个内部函数。
- 修改情绪标记、候选分数、提示词、控制标签协议或声音映射时，完整自动化测试必须包含这套基线。只有产品预期确实改变并经过人工试听/视觉确认后，才应更新固定样例。
- `tests/test_memory_governance.py` 锁定关系策略唯一入口、事实来源门禁、记忆过期、档案冲突覆盖和 Embedding 后台回填规则。
- `tests/test_prompt_architecture.py` 锁定五层顺序、稳定层与动态层边界、关系语义化、记忆可信等级以及普通聊天/问候/主动模式的一致性。

## 持久化与隐私

`data/persona.json` 是静态角色设定，可进入版本库。其他 `data/` 内容是某一个用户的本地运行状态，不应提交。`config/settings.json` 包含 API Key，也必须保持本地化。
