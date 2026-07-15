# Architecture

## 分层

```text
main.py / main_gui.py
        │
        ├─ ConversationOrchestrator ── 正常对话流程
        └─ InitiativeEngine       ── 后台主动对话
                    │
        ┌──────────┼──────────┐
        │          │          │
      ai/       domain managers   context/memory
        │          │          │
        └──── Storage_utils / local JSON
```

- **入口层**：`main.py` 负责控制台交互，`main_gui.py` 负责 Qt 界面、Live2D 和跨线程信号。
- **应用层**：`ConversationOrchestrator` 编排一轮对话；`InitiativeEngine` 评分是否应该主动发言。
- **领域状态**：profile、emotion、relationship、event 等 manager 负责状态规则和持久化入口。
- **AI 适配层**：`ai/client.py` 创建 OpenAI 兼容客户端，`ai/chat.py` 组装角色提示词并生成回复。
- **记忆层**：`context_builder.py` 整合事件语义分数、重要度、时间衰减和长期摘要。
- **数据模型层**：`data_models.py` 统一校验配置、持久化状态与 AI JSON，限制枚举、类型和数值范围。
- **基础设施**：`Storage_utils.py` 使用临时文件替换和 `.bak` 备份保护 JSON。

## 正常对话时序

1. `prepare_turn()` 在本地规划用户情绪与 Mio 本轮反应，同时识别意图，必要时提取用户资料。
2. 在共享锁内写入用户消息，并取历史与上下文快照。
3. `stream_reply()` 在锁外使用快照和本轮反应提示生成流式回复。
4. `finalize_turn()` 校准并立即提交即时情绪，使状态栏、Live2D 与本轮 TTS 同步，然后快速保存回复并投递后台任务。
5. 单一顺序后台线程提取长期事件，再在锁内提交关系和 context；只有本地没有明确即时信号时，事件情绪才作为心情兜底。
6. 溢出历史先写入 `data/pending_summary.json`，累计 10 条后才在后台批量生成长期摘要。

## 情绪模型

- `user_mood` 描述用户透露的感受，`mood` 描述 Mio 的持久心情，两者不能直接复制。
- `modifier` 是担心、感动、好奇、惊讶、无奈等短暂反应，有独立强度和剩余轮数。
- `mood_strength` 驱动 Live2D 参数幅度和 TTS 表现；同一心情的强度变化也必须刷新表现层。
- 正负心情之间的轻微信号需要连续确认，候选状态带过期时间；无新触发时按轮数和时间淡出。
- `fatigue_strength` 是独立连续轴，疲惫主状态使用进入/退出双阈值防止边界抖动。

## 主动对话时序

1. 在锁内检查冷却，计算事件、情绪和空闲时间评分。
2. 保存最后互动时间和上下文快照，释放锁。
3. 在锁外生成 AI 消息。
4. 重新加锁；如果用户在生成期间已说话，丢弃过时的主动消息。
5. 提交消息、冷却和事件通知状态。

## 并发不变式

- Orchestrator 和 InitiativeEngine 必须共享同一个历史列表与同一把状态锁。
- `save_memory()` 必须原地截断列表，不得让多个持有者分叉。
- 网络 AI 请求和长期摘要不得持有全局状态锁。
- 正常对话的事件提取和摘要任务必须在单一后台队列中按对话顺序执行。
- Qt 控件只能在 GUI 主线程修改。
- 应用关闭时不得销毁仍在运行的 `ChatWorker` QThread。

## 持久化与隐私

`data/persona.json` 是静态角色设定，可进入版本库。其他 `data/` 内容是某一个用户的本地运行状态，不应提交。`config/settings.json` 包含 API Key，也必须保持本地化。
