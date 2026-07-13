# 开发日志 - day18

今天主要围绕 GUI 响应速度、Live2D 表现层和意图识别做了一轮优化。

## 1. Live2D 表现层整理

新增了 `character_controller.py`，用于管理角色表现状态，包括回复时的嘴型、情绪变化时的参数表情，以及未来接入 TTS / 原生 expression 的扩展入口。

新增了 `live2d_model_utils.py`，用于读取 Live2D `model3.json` 和 `cdi3.json`，获取模型可用参数、表情和动作组信息。

## 2. Live2D 性能优化

将 Live2D 渲染频率从约 60FPS 降到约 30FPS，降低 GUI 主线程压力。

同时将情绪参数写入频率限制到约 30Hz，避免每帧频繁调用 Python 到 Live2D 原生接口。

## 3. 流式回复渲染优化

GUI 中 AI 回复 chunk 不再每次都触发完整 HTML 重绘，而是节流到约 30FPS。这样可以减少流式输出时 GUI 卡顿，也降低 Live2D 和聊天文本渲染互相抢主线程的情况。

## 4. 意图识别优化

`detect_intent()` 改为三层策略：

- 明确句式使用本地规则直接判定
- 模糊特殊意图交给 AI 兜底
- 普通聊天直接走 chat

这样在保留一定灵活性的同时，减少普通聊天前的一次 AI 意图识别请求。

## 5. 资料提取优化

`profile_extractor` 不再每轮都调用，只在用户明显表达资料更新时触发，例如“我喜欢”“我讨厌”“我叫”“叫我”等句式。

## 6. 轻量表情系统增强

增强了参数版情绪表情的默认值，让 happy / sad / shy / tired 的效果更明显。

新增 `live2d_expression_intensity` 配置项，用于整体调节表情强度。

## 后续计划

- 制作 Live2D 原生 `.exp3.json` 表情文件
- 拆分 `main_gui.py` 中的 `Live2DWidget`
- 制作 Live2D 参数测试面板
- 继续优化 `finalize_turn()` 的后台收尾流程
- 为 TTS 和 WebSocket 预留事件总线
