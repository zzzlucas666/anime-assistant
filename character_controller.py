"""角色表现控制层：把对话状态翻译成 Live2D 表现指令。"""

import math
import time


PARAMETER_REFRESH_INTERVAL_SECONDS = 1 / 30


class CharacterController:
    """独立于 GUI 的角色表现控制器，后续 TTS 嘴型也会接在这里。"""

    def __init__(
        self,
        live2d_widget=None,
        expression_map=None,
        motion_map=None,
        parameter_map=None,
        expression_intensity=1.0,
        available_expressions=None,
        available_motion_groups=None,
        available_parameters=None,
    ):
        self.live2d_widget = live2d_widget
        self.expression_map = expression_map or {}
        self.motion_map = motion_map or {}
        self.parameter_map = parameter_map or {}
        self.expression_intensity = max(0.0, float(expression_intensity))
        self.available_expressions = set(available_expressions or [])
        self.available_motion_groups = set(available_motion_groups or [])
        self.available_parameters = set(available_parameters or [])
        self.is_speaking = False
        self._last_emotion = None
        self._active_parameters = {}
        self._last_parameter_refresh_at = 0.0
        self._speaking_started_at = 0.0
        self._last_chunk_at = 0.0

    def set_live2d_widget(self, live2d_widget):
        self.live2d_widget = live2d_widget
        self.refresh_current_expression()

    def on_emotion_changed(self, emotion):
        mood = (emotion or {}).get("mood", "neutral")
        if mood == self._last_emotion:
            return

        self._last_emotion = mood
        self._apply_expression(mood)
        self._apply_motion(mood)
        self._apply_parameters(mood)

    def refresh_current_expression(self):
        """
        Live2D 模型可能晚于 GUI 状态栏完成初始化。

        这里用于模型刚加载完成后重放一次当前情绪，避免启动时已经读到了
        emotion_state.json，但参数还没来得及写进模型。
        """
        if self._last_emotion:
            self._apply_expression(self._last_emotion)
            self._apply_motion(self._last_emotion)
            self._apply_parameters(self._last_emotion)

    def on_reply_started(self):
        self.is_speaking = True
        now = time.monotonic()
        self._speaking_started_at = now
        self._last_chunk_at = now

    def on_reply_chunk(self, chunk):
        if chunk:
            if not self.is_speaking:
                self.on_reply_started()
            self._last_chunk_at = time.monotonic()

    def on_reply_finished(self):
        self.is_speaking = False
        self._call_widget("set_mouth_open", 0.0)

    def tick(self):
        """每帧调用一次。当前先做非 TTS 的简单嘴型，之后可换成音量驱动。"""
        if not self.live2d_widget:
            return

        # model.Update() 可能会重置部分参数，但每帧写一串参数比较吃主线程。
        # 控制到约 30Hz，视觉上够稳定，也能减少 Python -> Live2D 原生调用次数。
        now = time.monotonic()
        if self._active_parameters and now - self._last_parameter_refresh_at >= PARAMETER_REFRESH_INTERVAL_SECONDS:
            self._call_widget("set_parameters", self._active_parameters)
            self._last_parameter_refresh_at = now

        if not self.is_speaking:
            self._call_widget("set_mouth_open", 0.0)
            return

        # 如果流式文本短暂停顿，嘴型逐渐收小，而不是突然闭合。
        silence = max(0.0, now - self._last_chunk_at)
        activity = max(0.0, 1.0 - silence / 0.8)

        elapsed = now - self._speaking_started_at
        open_value = (0.25 + 0.55 * abs(math.sin(elapsed * 18.0))) * activity
        self._call_widget("set_mouth_open", open_value)

    def _apply_expression(self, mood):
        expression = self.expression_map.get(mood)
        if not expression:
            return

        # 如果提前读到了模型表情列表，就用它保护一下，避免配置写错时报一堆无意义错误。
        if self.available_expressions and expression not in self.available_expressions:
            return

        self._call_widget("set_expression", expression)

    def _apply_motion(self, mood):
        motion_group = self.motion_map.get(mood)
        if not motion_group:
            return

        # 动作以 group 为单位触发；没有声明这个 group 时直接跳过。
        if self.available_motion_groups and motion_group not in self.available_motion_groups:
            return

        self._call_widget("start_motion", motion_group)

    def _apply_parameters(self, mood):
        params = self.parameter_map.get(mood) or {}
        if not isinstance(params, dict):
            return

        filtered = {}
        for param_id, value in params.items():
            if self.available_parameters and param_id not in self.available_parameters:
                continue
            filtered[param_id] = self._scale_parameter_value(mood, value)

        self._active_parameters = filtered
        if self._active_parameters:
            self._call_widget("set_parameters", self._active_parameters)

    def _scale_parameter_value(self, mood, value):
        """
        用统一强度系数放大/缩小表情效果。

        neutral 必须保持原值，避免“恢复中性”时也被强度系数影响。
        """
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            return value

        if mood == "neutral":
            return numeric_value

        return numeric_value * self.expression_intensity

    def _call_widget(self, method_name, *args):
        target = self.live2d_widget
        if not target:
            return
        method = getattr(target, method_name, None)
        if callable(method):
            method(*args)
