# Day17 开发日志

Day17 开发日志
Day17 - Character Controller & Presentation Layer

今天新增 CharacterController，正式将角色表现层（Presentation Layer）从 GUI 和 Live2D 中独立出来，为后续接入 TTS、表情驱动、动作系统等功能打下基础。

一、CharacterController

新增：

character_controller.py

CharacterController 位于 Runtime 与 Live2D 之间。

它负责：

情绪驱动
说话状态管理
嘴型控制
表情切换

而不直接依赖具体 Live2D API。

真正做到：

Runtime
    ↓
CharacterController
    ↓
Live2D Widget

让 Runtime 不再关心角色具体如何表现。

二、表现层与业务逻辑解耦

CharacterController 不再直接参与：

Memory
Emotion
Relationship
Initiative

它只负责：

把 Runtime 的状态转换成角色的表现状态。

实现了：

Emotion → Expression
Speaking → Mouth Animation

后续如果更换 Live2D SDK 或接入其他角色渲染方式，只需修改表现层即可，不影响核心逻辑。

三、情绪驱动表情

新增：

Emotion
↓
Expression

根据当前 Mood 自动切换角色表情。

目前支持：

Happy
Sad
Shy
Tired
Neutral

后续可以继续扩展更多角色状态。

四、说话状态控制

新增：

回复开始
回复结束
流式回复 Chunk 更新

CharacterController 根据流式输出自动维护：

is_speaking

让角色能够知道：

什么时候开始说话
什么时候结束说话

为后续：

TTS
嘴型同步
动画播放

提供统一入口。

五、Live2D 嘴型动画

新增：

Tick 驱动机制。

每帧根据：

当前是否说话
Chunk 更新时间

动态计算 Mouth Open。

目前采用：

sin()

模拟嘴型开合。

同时：

如果流式输出暂停。

嘴巴不会立即闭合，而是：

逐渐衰减。

动画更加自然。

六、未来扩展能力

CharacterController 已预留统一接口。

未来可直接扩展：

TTS 嘴型同步
Blink（眨眼）
Idle Animation
Head Tracking
Eye Tracking
Motion 播放
Gesture 系统

无需修改 Runtime。

今日成果

完成：

CharacterController
 Presentation Layer 抽象
 Emotion → Expression 映射
 Speaking State 管理
 Live2D 嘴型控制
 Tick 驱动动画
GUI 与 Live2D 进一步解耦
下一步计划

下一阶段将继续完善角色表现层：

TTS 接入
真实口型同步
Live2D 动作（Motion）
眨眼与待机动画
Planner 与 CharacterController 联动
Day17 总结

今天最大的成果，是新增了 CharacterController，正式建立了 Runtime 与 Live2D 之间的表现层抽象。

角色的表情、嘴型和说话状态不再由 GUI 或 Live2D Widget 直接管理，而是统一交由 CharacterController 控制，实现了业务逻辑与角色表现的彻底解耦。这不仅提升了系统架构的可维护性，也为后续接入 TTS、动作系统以及更丰富的角色演出能力奠定了基础。
