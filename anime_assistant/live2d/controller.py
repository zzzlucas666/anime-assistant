"""角色表现控制层：把对话状态翻译成 Live2D 表现指令。"""

from collections import deque
import math
import random
import time


INITIAL_FRAME_DELTA_SECONDS = 1 / 30
MAX_SPEECH_SEGMENTS = 320

# MIO 使用的是 Cubism 标准面部参数。这里的默认值也用于情绪淡出，避免从
# happy 切回 neutral 后，上一轮写入的笑眼、脸红等参数残留在模型上。
PARAMETER_DEFAULTS = {
    "ParamAngleX": 0.0,
    "ParamAngleY": 0.0,
    "ParamAngleZ": 0.0,
    "ParamBodyAngleX": 0.0,
    "ParamBodyAngleY": 0.0,
    "ParamBodyAngleZ": 0.0,
    "ParamEyeLOpen": 1.0,
    "ParamEyeROpen": 1.0,
    "ParamEyeLSmile": 0.0,
    "ParamEyeRSmile": 0.0,
    "ParamEyeBallX": 0.0,
    "ParamEyeBallY": 0.0,
    "ParamBrowLY": 0.0,
    "ParamBrowRY": 0.0,
    "ParamBrowLX": 0.0,
    "ParamBrowRX": 0.0,
    "ParamBrowLAngle": 0.0,
    "ParamBrowRAngle": 0.0,
    "ParamBrowLForm": 0.0,
    "ParamBrowRForm": 0.0,
    "ParamMouthForm": 0.0,
    "ParamMouthOpenY": 0.0,
    "ParamCheek": 0.0,
    "ParamBreath": 0.5,
}

PARAMETER_LIMITS = {
    "ParamAngleX": (-30.0, 30.0),
    "ParamAngleY": (-30.0, 30.0),
    "ParamAngleZ": (-30.0, 30.0),
    "ParamBodyAngleX": (-10.0, 10.0),
    "ParamBodyAngleY": (-10.0, 10.0),
    "ParamBodyAngleZ": (-10.0, 10.0),
    "ParamEyeLOpen": (0.0, 1.0),
    "ParamEyeROpen": (0.0, 1.0),
    "ParamEyeLSmile": (0.0, 1.0),
    "ParamEyeRSmile": (0.0, 1.0),
    "ParamEyeBallX": (-1.0, 1.0),
    "ParamEyeBallY": (-1.0, 1.0),
    "ParamMouthForm": (-1.0, 1.0),
    "ParamMouthOpenY": (0.0, 1.0),
    "ParamCheek": (0.0, 1.0),
    "ParamBreath": (0.0, 1.0),
}

PROCEDURAL_PARAMETERS = {
    "ParamAngleX",
    "ParamAngleY",
    "ParamAngleZ",
    "ParamBodyAngleX",
    "ParamEyeLOpen",
    "ParamEyeROpen",
    "ParamEyeBallX",
    "ParamEyeBallY",
    "ParamBrowLY",
    "ParamBrowRY",
    "ParamCheek",
    "ParamBreath",
}

MODIFIER_PARAMETER_MAP = {
    "worried": {
        "ParamEyeLOpen": 0.9,
        "ParamEyeROpen": 0.9,
        "ParamBrowLY": -0.1,
        "ParamBrowRY": -0.1,
        "ParamMouthForm": -0.08,
        "ParamAngleY": -1.2,
    },
    "touched": {
        "ParamEyeLSmile": 0.22,
        "ParamEyeRSmile": 0.22,
        "ParamMouthForm": 0.18,
        "ParamCheek": 0.22,
    },
    "curious": {
        "ParamEyeLOpen": 1.0,
        "ParamEyeROpen": 1.0,
        "ParamBrowLY": 0.06,
        "ParamBrowRY": 0.04,
        "ParamAngleX": 2.4,
        "ParamAngleZ": 1.4,
    },
    "surprised": {
        "ParamEyeLOpen": 1.0,
        "ParamEyeROpen": 1.0,
        "ParamBrowLY": 0.12,
        "ParamBrowRY": 0.12,
        "ParamMouthOpenY": 0.08,
    },
    "annoyed": {
        "ParamEyeLOpen": 0.88,
        "ParamEyeROpen": 0.88,
        "ParamBrowLY": -0.06,
        "ParamBrowRY": -0.06,
        "ParamBrowLAngle": -0.08,
        "ParamBrowRAngle": 0.08,
        "ParamMouthForm": -0.12,
        "ParamAngleX": 1.8,
    },
}

FATIGUE_PARAMETER_MAP = {
    "ParamEyeLOpen": 0.66,
    "ParamEyeROpen": 0.66,
    "ParamBrowLY": -0.06,
    "ParamBrowRY": -0.06,
    "ParamMouthForm": -0.1,
    "ParamAngleY": -2.0,
}


class CharacterController:
    """独立于 GUI 的角色表现控制器，也作为后续 TTS 嘴型的接入点。"""

    def __init__(
        self,
        live2d_widget=None,
        expression_map=None,
        motion_map=None,
        parameter_map=None,
        expression_intensity=1.0,
        waiting_motion_intensity=1.0,
        waiting_gaze_intensity=1.0,
        waiting_motion_speed=1.4,
        available_expressions=None,
        available_motion_groups=None,
        available_parameters=None,
        rng=None,
    ):
        self.live2d_widget = live2d_widget
        self.expression_map = expression_map or {}
        self.motion_map = motion_map or {}
        self.parameter_map = parameter_map or {}
        self.expression_intensity = max(0.0, float(expression_intensity))
        self.waiting_motion_intensity = max(
            0.0, min(2.0, float(waiting_motion_intensity))
        )
        self.waiting_gaze_intensity = max(
            0.0, min(2.0, float(waiting_gaze_intensity))
        )
        self.waiting_motion_speed = max(
            0.5, min(2.0, float(waiting_motion_speed))
        )
        self.available_expressions = set(available_expressions or [])
        self.available_motion_groups = set(available_motion_groups or [])
        self.available_parameters = set(available_parameters or [])
        self._rng = rng or random.Random()

        self.is_speaking = False
        self._last_emotion = None
        self._last_emotion_signature = None
        self._emotion_strength = 1.0
        self._modifier = "none"
        self._modifier_strength = 0.0
        self._fatigue_strength = 0.0
        self._active_parameters = {}
        self._emotion_targets = {}
        self._current_parameters = {}
        self._last_tick_at = 0.0

        now = time.monotonic()
        self._created_at = now
        self._speaking_started_at = 0.0
        self._last_chunk_at = 0.0
        self._speaking_blend = 0.0
        self._speech_segments = deque()
        self._speech_segment_remaining = 0.0
        self._speech_mouth_target = 0.0
        self._mouth_open = 0.0
        self._reply_input_finished = True
        self._audio_mouth_active = False
        self._audio_mouth_target = 0.0
        self.is_preparing_speech = False
        self._waiting_motion_preview = False
        self._preparing_blend = 0.0
        self._waiting_motion_phase = 0.0

        self._blink_started_at = None
        self._next_blink_at = now + self._rng.uniform(2.5, 5.5)
        self._gaze_x = 0.0
        self._gaze_y = 0.0
        self._gaze_target_x = 0.0
        self._gaze_target_y = 0.0
        self._next_gaze_at = now + self._rng.uniform(1.0, 2.5)
        self._emphasis_kind = None
        self._emphasis_until = 0.0
        self._manual_parameters = {}

    def set_live2d_widget(self, live2d_widget):
        self.live2d_widget = live2d_widget
        self.refresh_current_expression()

    def on_emotion_changed(self, emotion):
        mood = (emotion or {}).get("mood", "neutral")
        default_strength = 0.0 if mood == "neutral" else 1.0
        try:
            strength = max(0.0, min(1.0, float((emotion or {}).get("mood_strength", default_strength))))
        except (TypeError, ValueError):
            strength = default_strength
        modifier = (emotion or {}).get("modifier", "none")
        try:
            modifier_strength = max(0.0, min(1.0, float((emotion or {}).get("modifier_strength", 0.0))))
        except (TypeError, ValueError):
            modifier_strength = 0.0
        try:
            fatigue_strength = max(0.0, min(1.0, float((emotion or {}).get("fatigue_strength", 0.0))))
        except (TypeError, ValueError):
            fatigue_strength = 0.0

        signature = (
            mood,
            round(strength, 3),
            modifier,
            round(modifier_strength, 3),
            round(fatigue_strength, 3),
        )
        if signature == self._last_emotion_signature:
            return

        mood_changed = mood != self._last_emotion
        self._last_emotion = mood
        self._last_emotion_signature = signature
        self._emotion_strength = strength
        self._modifier = modifier
        self._modifier_strength = modifier_strength
        self._fatigue_strength = fatigue_strength
        if mood_changed:
            self._apply_expression(mood)
            self._apply_motion(mood)
        self._apply_parameters(mood)

    def refresh_current_expression(self):
        """模型完成初始化后重放当前情绪目标。"""
        if self._last_emotion:
            self._apply_expression(self._last_emotion)
            self._apply_motion(self._last_emotion)
            self._apply_parameters(self._last_emotion)

    def on_reply_started(self):
        self._audio_mouth_active = False
        self._audio_mouth_target = 0.0
        self.is_speaking = True
        self._reply_input_finished = False
        now = time.monotonic()
        self._speaking_started_at = now
        self._last_chunk_at = now
        self._speech_segments.clear()
        self._speech_segment_remaining = 0.0
        self._speech_mouth_target = 0.0

        # 开口前先把视线收回用户方向，避免一边看向别处一边开始说话。
        self._gaze_target_x = self._rng.uniform(-0.08, 0.08)
        self._gaze_target_y = self._rng.uniform(-0.03, 0.08)
        self._next_gaze_at = now + self._rng.uniform(1.6, 2.8)

    def on_reply_chunk(self, chunk):
        if not chunk:
            return
        if not self.is_speaking:
            self.on_reply_started()

        now = time.monotonic()
        self._last_chunk_at = now
        self._queue_speech_text(chunk)

        # 标点触发短暂的表演层，不改变持久 mood，也不需要额外 AI 请求。
        if any(mark in chunk for mark in "!?！？"):
            if any(mark in chunk for mark in "!！"):
                self._emphasis_kind = "excited"
                self._emphasis_until = now + 0.65
            else:
                self._emphasis_kind = "question"
                self._emphasis_until = now + 0.9
        elif any(mark in chunk for mark in "~～"):
            self._emphasis_kind = "playful"
            self._emphasis_until = now + 0.8

    def on_reply_finished(self):
        # 文本流结束不等于嘴型立即结束。保留尚未播放的音节，队列耗尽后
        # _advance_speech_mouth 会自动收尾；这能避免 AI 返回很快时只张几下嘴。
        self._reply_input_finished = True
        if not self._speech_segments and self._speech_segment_remaining <= 0:
            self.is_speaking = False
            self._speech_mouth_target = 0.0

    def on_audio_started(self):
        """真实语音开始播放；音频响度暂时接管文字节奏嘴型。"""
        self.is_preparing_speech = False
        self._audio_mouth_active = True
        self._audio_mouth_target = 0.0
        self.is_speaking = True
        self._speech_segments.clear()
        self._speech_segment_remaining = 0.0
        self._speech_mouth_target = 0.0
        now = time.monotonic()
        self._speaking_started_at = now
        self._gaze_target_x = self._rng.uniform(-0.08, 0.08)
        self._gaze_target_y = self._rng.uniform(-0.03, 0.08)

    def on_audio_amplitude(self, value):
        """更新当前音频窗口的归一化响度。"""
        if not self._audio_mouth_active:
            return
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = 0.0
        self._audio_mouth_target = max(0.0, min(1.0, value))

    def on_audio_finished(self):
        """所有排队语音播放完毕，让嘴型自然平滑闭合。"""
        self._audio_mouth_active = False
        self._audio_mouth_target = 0.0
        self.is_speaking = False

    def on_speech_preparing(self):
        """完整文字已生成、TTS 正在准备时进入有生命感的安静待机。"""
        self.is_preparing_speech = True
        self._audio_mouth_active = False
        self._audio_mouth_target = 0.0
        self.is_speaking = False
        self._speech_segments.clear()
        self._speech_segment_remaining = 0.0
        self._speech_mouth_target = 0.0
        now = time.monotonic()
        # 尽快选取第一个思考视线目标，但仍由帧平滑器逐渐移动过去。
        self._next_gaze_at = min(self._next_gaze_at, now + 0.18)

    def on_speech_preparing_finished(self):
        """TTS 失败或没有可播放内容时退出等待动作。"""
        self.is_preparing_speech = False

    def set_waiting_motion_intensity(self, value):
        """实时调整等待语音时的头部与物理头发动作强度。"""
        try:
            value = float(value)
        except (TypeError, ValueError):
            return self.waiting_motion_intensity
        self.waiting_motion_intensity = max(0.0, min(2.0, value))
        return self.waiting_motion_intensity

    def set_waiting_motion_preview(self, enabled):
        """调参窗口使用的待机动作预览，不改变真实 TTS 状态。"""
        self._waiting_motion_preview = bool(enabled)
        if enabled:
            now = time.monotonic()
            self._next_gaze_at = min(self._next_gaze_at, now + 0.18)

    def set_waiting_gaze_intensity(self, value):
        """实时调整等待语音时的视线游移幅度。"""
        try:
            value = float(value)
        except (TypeError, ValueError):
            return self.waiting_gaze_intensity
        self.waiting_gaze_intensity = max(0.0, min(2.0, value))
        now = time.monotonic()
        self._next_gaze_at = now
        if self.waiting_gaze_intensity == 0.0:
            self._gaze_target_x = 0.0
            self._gaze_target_y = 0.0
        return self.waiting_gaze_intensity

    def set_waiting_motion_speed(self, value):
        """实时调整待机头部、身体、眉毛和视线切换速度。"""
        try:
            value = float(value)
        except (TypeError, ValueError):
            return self.waiting_motion_speed
        self.waiting_motion_speed = max(0.5, min(2.0, value))
        return self.waiting_motion_speed

    def preview_parameters(self, mood, parameters):
        """实时预览一组未缩放的情绪参数，供调试滑块使用。"""
        preview = {}
        for param_id, value in (parameters or {}).items():
            if not self._supports_parameter(param_id):
                continue
            scaled = self._scale_parameter_value(mood, param_id, value, strength=1.0)
            preview[param_id] = self._clamp_parameter(param_id, scaled)
        self._manual_parameters = preview

    def clear_parameter_preview(self):
        self._manual_parameters = {}

    def update_parameter_preset(self, mood, parameters):
        """更新一个情绪预设；若它正在生效，立即刷新目标参数。"""
        if not isinstance(parameters, dict):
            return
        self.parameter_map[mood] = dict(parameters)
        if mood == self._last_emotion:
            self._apply_parameters(mood)

    def tick(self):
        """每帧更新平滑表情、眨眼、视线、呼吸和文本节奏嘴型。"""
        if not self.live2d_widget:
            return

        now = time.monotonic()
        if self._last_tick_at:
            dt = min(0.1, max(1 / 240, now - self._last_tick_at))
        else:
            dt = INITIAL_FRAME_DELTA_SECONDS
        self._last_tick_at = now

        speaking_target = 1.0 if self.is_speaking else 0.0
        self._speaking_blend = self._smooth_value(
            self._speaking_blend, speaking_target, 7.0, dt
        )
        waiting_motion_active = (
            self.is_preparing_speech or self._waiting_motion_preview
        )
        preparing_target = 1.0 if waiting_motion_active else 0.0
        preparing_speed = 2.1 if preparing_target > self._preparing_blend else 2.6
        self._preparing_blend = self._smooth_value(
            self._preparing_blend, preparing_target, preparing_speed, dt
        )
        # 独立累积相位，拖动速度滑块时只改变后续推进速度，不会因使用
        # monotonic 绝对时间乘倍率而突然跳到另一个动作相位。
        self._waiting_motion_phase += dt * self.waiting_motion_speed

        desired = self._build_desired_parameters(now, dt)
        rest_mouth_open = self._clamp_parameter(
            "ParamMouthOpenY", desired.pop("ParamMouthOpenY", 0.0)
        )
        output = {}
        for param_id, target in desired.items():
            if not self._supports_parameter(param_id):
                continue
            current = self._current_parameters.get(
                param_id, PARAMETER_DEFAULTS.get(param_id, 0.0)
            )
            current = self._smooth_value(
                current, self._clamp_parameter(param_id, target),
                self._parameter_speed(param_id), dt,
            )
            current = self._clamp_parameter(param_id, current)
            self._current_parameters[param_id] = current
            output[param_id] = current

        if output:
            self._call_widget("set_parameters", output)

        speech_mouth = (
            self._audio_mouth_target
            if self._audio_mouth_active
            else self._advance_speech_mouth(dt, now)
        )
        # 静态开合决定嘴唇的休息形状；说话嘴型在剩余空间内叠加，既不会
        # 突然跳回闭嘴，也不会超过模型的 0～1 范围。
        mouth_target = rest_mouth_open + speech_mouth * (1.0 - rest_mouth_open)
        mouth_speed = 24.0 if mouth_target > self._mouth_open else 18.0
        self._mouth_open = self._smooth_value(
            self._mouth_open, mouth_target, mouth_speed, dt
        )
        self._call_widget("set_mouth_open", self._mouth_open)

    def _build_desired_parameters(self, now, dt):
        managed = set(PROCEDURAL_PARAMETERS)
        managed.update(PARAMETER_DEFAULTS)
        managed.update(self._emotion_targets)
        desired = {
            param_id: self._emotion_targets.get(
                param_id, PARAMETER_DEFAULTS.get(param_id, 0.0)
            )
            for param_id in managed
        }

        blink = self._blink_factor(now)
        desired["ParamEyeLOpen"] = desired.get("ParamEyeLOpen", 1.0) * blink
        desired["ParamEyeROpen"] = desired.get("ParamEyeROpen", 1.0) * blink

        self._update_gaze(now, dt)
        desired["ParamEyeBallX"] = self._gaze_x
        desired["ParamEyeBallY"] = self._gaze_y

        # 不同频率的呼吸、头部和身体小幅变化，可避免整体像一张静态贴图。
        # 启动后的前两秒逐渐引入微动，让物理系统先稳定下来，避免刚显示时突跳。
        motion_blend = min(1.0, max(0.0, (now - self._created_at) / 2.0))
        desired["ParamBreath"] = 0.5 + 0.38 * math.sin(now * math.tau / 4.2)
        desired["ParamAngleX"] += motion_blend * 0.25 * math.sin(now * 0.62)
        desired["ParamAngleY"] += (
            motion_blend * self._speaking_blend * 0.55 * math.sin(now * 1.65)
        )
        desired["ParamAngleZ"] += (
            motion_blend * self._speaking_blend * 0.25 * math.sin(now * 0.85)
        )
        desired["ParamBodyAngleX"] += motion_blend * 0.25 * math.sin(now * 0.48)

        # 等待 TTS 时采用低频、错相位的连续曲线。所有幅度先经过 preparing
        # blend 缓慢淡入，避免状态切换时头部突跳；头部/身体的连续转动也会
        # 自然带动模型物理系统中的头发，而不是直接抖动发丝参数。
        # 调参窗口的静态参数先落地，待机动作再以相对偏移叠加，确保拖动
        # “待机摆头强度”时能实时看到头部和物理头发运动。
        desired.update(self._manual_parameters)

        if self._waiting_motion_preview:
            # 调参窗口中仍保留静态视线值作为中心点，再叠加待机游移，
            # 这样拖动视线强度滑块时能立即看到真实效果。
            desired["ParamEyeBallX"] = self._clamp_parameter(
                "ParamEyeBallX",
                self._manual_parameters.get("ParamEyeBallX", 0.0) + self._gaze_x,
            )
            desired["ParamEyeBallY"] = self._clamp_parameter(
                "ParamEyeBallY",
                self._manual_parameters.get("ParamEyeBallY", 0.0) + self._gaze_y,
            )

        preparing = (
            motion_blend
            * self._preparing_blend
            * self.waiting_motion_intensity
        )
        waiting_time = self._waiting_motion_phase
        desired["ParamAngleX"] += preparing * (
            7.2 * math.sin(waiting_time * 0.46)
            + 1.35 * math.sin(waiting_time * 0.21 + 1.1)
            + 0.62 * math.sin(waiting_time * 0.82 + 0.45)
        )
        desired["ParamAngleY"] += preparing * 1.65 * math.sin(waiting_time * 0.34 + 0.7)
        desired["ParamAngleZ"] += preparing * (
            2.35 * math.sin(waiting_time * 0.31 + 2.0)
            + 0.48 * math.sin(waiting_time * 0.68 + 0.2)
        )
        desired["ParamBodyAngleX"] += preparing * 1.55 * math.sin(waiting_time * 0.31 + 1.6)
        desired["ParamBodyAngleY"] += preparing * 0.48 * math.sin(waiting_time * 0.23 + 0.4)
        desired["ParamBrowLY"] += preparing * (
            0.045 * math.sin(waiting_time * 0.72)
            + 0.018 * math.sin(waiting_time * 0.29)
        )
        desired["ParamBrowRY"] += preparing * (
            0.042 * math.sin(waiting_time * 0.72 + 0.35)
            + 0.016 * math.sin(waiting_time * 0.31)
        )

        if now < self._emphasis_until:
            self._apply_emphasis(desired)
        else:
            self._emphasis_kind = None

        return desired

    def _blink_factor(self, now):
        if self._blink_started_at is None and now >= self._next_blink_at:
            self._blink_started_at = now

        if self._blink_started_at is None:
            return 1.0

        duration = 0.26 if self._last_emotion == "tired" else 0.18
        progress = (now - self._blink_started_at) / duration
        if progress >= 1.0:
            self._blink_started_at = None
            interval = (
                self._rng.uniform(2.2, 4.6)
                if self._last_emotion == "tired"
                else self._rng.uniform(2.8, 6.0)
            )
            self._next_blink_at = now + interval
            return 1.0

        return max(0.0, 1.0 - math.sin(math.pi * max(0.0, progress)))

    def _update_gaze(self, now, dt):
        if now >= self._next_gaze_at:
            if self.is_preparing_speech or self._waiting_motion_preview:
                gaze_scale = self.waiting_gaze_intensity
                self._gaze_target_x = self._rng.uniform(-0.42, 0.42) * gaze_scale
                self._gaze_target_y = self._rng.uniform(-0.18, 0.22) * gaze_scale
                delay = self._rng.uniform(1.2, 2.6) / self.waiting_motion_speed
            elif self.is_speaking:
                self._gaze_target_x = self._rng.uniform(-0.18, 0.18)
                self._gaze_target_y = self._rng.uniform(-0.08, 0.12)
                delay = self._rng.uniform(1.5, 3.0)
            else:
                self._gaze_target_x = self._rng.uniform(-0.3, 0.3)
                self._gaze_target_y = self._rng.uniform(-0.16, 0.16)
                delay = self._rng.uniform(2.0, 4.5)
            self._next_gaze_at = now + delay

        gaze_speed = (
            1.8 * math.sqrt(self.waiting_motion_speed)
            if self.is_preparing_speech or self._waiting_motion_preview
            else 3.0
        )
        self._gaze_x = self._smooth_value(
            self._gaze_x, self._gaze_target_x, gaze_speed, dt
        )
        self._gaze_y = self._smooth_value(
            self._gaze_y, self._gaze_target_y, gaze_speed, dt
        )

    def _apply_emphasis(self, desired):
        if self._emphasis_kind == "excited":
            desired["ParamEyeLOpen"] += 0.12
            desired["ParamBrowLY"] += 0.2
            desired["ParamBrowRY"] += 0.2
            desired["ParamAngleY"] += 1.5
        elif self._emphasis_kind == "question":
            desired["ParamAngleZ"] += 3.5
            desired["ParamBrowLY"] += 0.18
            desired["ParamBrowRY"] -= 0.08
        elif self._emphasis_kind == "playful":
            desired["ParamAngleZ"] -= 2.5
            desired["ParamCheek"] += 0.18

    def _queue_speech_text(self, chunk):
        for char in chunk:
            if char in "，,、;；:":
                segments = ((self._rng.uniform(0.14, 0.22), 0.0),)
            elif char in "。.!！?？\n":
                segments = ((self._rng.uniform(0.28, 0.42), 0.0),)
            elif char.isspace():
                segments = ((0.06, 0.0),)
            else:
                # 一个字符拆成张开和回落两个阶段。平均约每秒 5～7 个汉字，
                # 30 FPS 下每个字有数帧变化，不会只看到连续几次大开合。
                segments = (
                    (
                        self._rng.uniform(0.085, 0.13),
                        self._rng.uniform(0.32, 0.86),
                    ),
                    (self._rng.uniform(0.045, 0.075), self._rng.uniform(0.02, 0.12)),
                )

            for segment in segments:
                self._speech_segments.append(segment)
                while len(self._speech_segments) > MAX_SPEECH_SEGMENTS:
                    self._speech_segments.popleft()

    def _advance_speech_mouth(self, dt, now):
        if not self.is_speaking:
            return 0.0

        remaining_dt = dt
        while remaining_dt > 0:
            if self._speech_segment_remaining <= 0:
                if not self._speech_segments:
                    if self._reply_input_finished:
                        self.is_speaking = False
                        self._speech_mouth_target = 0.0
                        return 0.0
                    silence = max(0.0, now - self._last_chunk_at)
                    return 0.12 if silence < 0.12 else 0.0
                duration, target = self._speech_segments.popleft()
                self._speech_segment_remaining = duration
                self._speech_mouth_target = target

            consumed = min(remaining_dt, self._speech_segment_remaining)
            self._speech_segment_remaining -= consumed
            remaining_dt -= consumed

        return self._speech_mouth_target

    def _apply_expression(self, mood):
        expression = self.expression_map.get(mood)
        if not expression:
            return
        if self.available_expressions and expression not in self.available_expressions:
            return
        self._call_widget("set_expression", expression)

    def _apply_motion(self, mood):
        motion_group = self.motion_map.get(mood)
        if not motion_group:
            return
        if self.available_motion_groups and motion_group not in self.available_motion_groups:
            return
        self._call_widget("start_motion", motion_group)

    def _apply_parameters(self, mood):
        params = self.parameter_map.get(mood) or {}
        if not isinstance(params, dict):
            return

        filtered = {}
        for param_id, value in params.items():
            if not self._supports_parameter(param_id):
                continue
            filtered[param_id] = self._scale_parameter_value(
                mood, param_id, value, strength=self._emotion_strength
            )

        modifier_params = MODIFIER_PARAMETER_MAP.get(self._modifier) or {}
        self._add_parameter_overlay(
            filtered,
            modifier_params,
            self._modifier_strength,
        )
        if mood != "tired":
            self._add_parameter_overlay(
                filtered,
                FATIGUE_PARAMETER_MAP,
                self._fatigue_strength,
            )

        self._emotion_targets = filtered
        # 保留旧属性含义，避免外部诊断代码或测试依赖它。
        self._active_parameters = filtered.copy()

    def _add_parameter_overlay(self, parameters, overlay, strength):
        if strength <= 0:
            return
        for param_id, target_value in overlay.items():
            if not self._supports_parameter(param_id):
                continue
            neutral_value = PARAMETER_DEFAULTS.get(param_id, 0.0)
            current_value = parameters.get(param_id, neutral_value)
            parameters[param_id] = current_value + (
                float(target_value) - neutral_value
            ) * self.expression_intensity * strength

    def _scale_parameter_value(self, mood, param_id, value, strength=None):
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            return value
        if mood == "neutral":
            return numeric_value

        if strength is None:
            strength = self._emotion_strength if mood == self._last_emotion else 1.0
        strength = max(0.0, min(1.0, float(strength)))

        # 表情强度必须从参数的中性值向外放大。比如 EyeOpen 的中性值是 1，
        # sad=0.65 应该随强度升高而更闭；直接做 0.65 * 1.25 反而会更睁开。
        neutral_value = PARAMETER_DEFAULTS.get(param_id, 0.0)
        return neutral_value + (
            numeric_value - neutral_value
        ) * self.expression_intensity * strength

    def _supports_parameter(self, param_id):
        return not self.available_parameters or param_id in self.available_parameters

    @staticmethod
    def _smooth_value(current, target, speed, dt):
        alpha = 1.0 - math.exp(-max(0.0, speed) * max(0.0, dt))
        return current + (target - current) * alpha

    @staticmethod
    def _parameter_speed(param_id):
        if param_id in {"ParamEyeLOpen", "ParamEyeROpen"}:
            return 32.0
        if param_id.startswith("ParamAngle") or param_id.startswith("ParamBodyAngle"):
            return 5.0
        if param_id in {"ParamEyeBallX", "ParamEyeBallY", "ParamBreath"}:
            return 6.0
        return 9.0

    @staticmethod
    def _clamp_parameter(param_id, value):
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            return value
        lower, upper = PARAMETER_LIMITS.get(param_id, (-1.0, 1.0))
        return max(lower, min(upper, numeric_value))

    def _call_widget(self, method_name, *args):
        target = self.live2d_widget
        if not target:
            return
        method = getattr(target, method_name, None)
        if callable(method):
            method(*args)
