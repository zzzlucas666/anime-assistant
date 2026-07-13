"""Live2D 参数实时预览与情绪预设调试窗口。"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from character_controller import PARAMETER_DEFAULTS


MOOD_LABELS = {
    "neutral": "平静",
    "happy": "开心",
    "sad": "低落",
    "shy": "害羞",
    "tired": "疲惫",
}

# (参数 ID, 中文名称, 最小值, 最大值, 步长)
PARAMETER_SPECS = (
    ("ParamEyeLOpen", "左眼开合", 0.0, 1.0, 0.01),
    ("ParamEyeROpen", "右眼开合", 0.0, 1.0, 0.01),
    ("ParamEyeLSmile", "左眼笑意", 0.0, 1.0, 0.01),
    ("ParamEyeRSmile", "右眼笑意", 0.0, 1.0, 0.01),
    ("ParamEyeBallX", "视线左右", -1.0, 1.0, 0.01),
    ("ParamEyeBallY", "视线上下", -1.0, 1.0, 0.01),
    ("ParamBrowLY", "左眉上下", -1.0, 1.0, 0.01),
    ("ParamBrowRY", "右眉上下", -1.0, 1.0, 0.01),
    ("ParamBrowLAngle", "左眉角度", -1.0, 1.0, 0.01),
    ("ParamBrowRAngle", "右眉角度", -1.0, 1.0, 0.01),
    ("ParamBrowLForm", "左眉形状", -1.0, 1.0, 0.01),
    ("ParamBrowRForm", "右眉形状", -1.0, 1.0, 0.01),
    ("ParamMouthForm", "嘴唇形状", -1.0, 1.0, 0.01),
    ("ParamMouthOpenY", "嘴唇静态开合", 0.0, 1.0, 0.01),
    ("ParamCheek", "脸红", 0.0, 1.0, 0.01),
    ("ParamAngleX", "头部左右", -15.0, 15.0, 0.1),
    ("ParamAngleY", "头部上下", -15.0, 15.0, 0.1),
    ("ParamAngleZ", "头部倾斜", -15.0, 15.0, 0.1),
    ("ParamBodyAngleX", "身体左右", -8.0, 8.0, 0.1),
)


class Live2DParameterTuner(QDialog):
    def __init__(
        self,
        controller,
        parameter_map,
        recommended_map,
        current_mood="neutral",
        save_callback=None,
        waiting_motion_intensity=1.0,
        save_waiting_motion_callback=None,
        waiting_gaze_intensity=1.0,
        save_waiting_gaze_callback=None,
        waiting_motion_speed=1.4,
        save_waiting_motion_speed_callback=None,
        parent=None,
    ):
        super().__init__(parent)
        self.controller = controller
        self.parameter_map = {
            mood: dict(values) for mood, values in (parameter_map or {}).items()
            if isinstance(values, dict)
        }
        self.recommended_map = recommended_map or {}
        self.save_callback = save_callback
        self.save_waiting_motion_callback = save_waiting_motion_callback
        self.save_waiting_gaze_callback = save_waiting_gaze_callback
        self.save_waiting_motion_speed_callback = save_waiting_motion_speed_callback
        self.saved_waiting_motion_intensity = max(
            0.0, min(2.0, float(waiting_motion_intensity))
        )
        self.saved_waiting_gaze_intensity = max(
            0.0, min(2.0, float(waiting_gaze_intensity))
        )
        self.saved_waiting_motion_speed = max(
            0.5, min(2.0, float(waiting_motion_speed))
        )
        self.sliders = {}
        self.value_labels = {}
        self.spec_by_id = {spec[0]: spec for spec in PARAMETER_SPECS}

        self.setWindowTitle("Live2D 表情参数调试")
        self.resize(590, 720)
        self._build_ui(current_mood)
        self.controller.set_waiting_motion_intensity(
            self.saved_waiting_motion_intensity
        )
        self.controller.set_waiting_gaze_intensity(
            self.saved_waiting_gaze_intensity
        )
        self.controller.set_waiting_motion_speed(
            self.saved_waiting_motion_speed
        )
        self.controller.set_waiting_motion_preview(True)
        self._load_selected_mood()

    def _build_ui(self, current_mood):
        root = QVBoxLayout(self)

        header = QHBoxLayout()
        header.addWidget(QLabel("正在调整："))
        self.mood_combo = QComboBox()
        for mood, label in MOOD_LABELS.items():
            self.mood_combo.addItem(label, mood)
        index = self.mood_combo.findData(current_mood)
        self.mood_combo.setCurrentIndex(max(0, index))
        self.mood_combo.currentIndexChanged.connect(self._load_selected_mood)
        header.addWidget(self.mood_combo)
        header.addStretch(1)
        root.addLayout(header)

        hint = QLabel(
            "拖动滑块会立即预览。保存后写入本地 settings.json；关闭窗口会退出手动预览。"
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        waiting_row = QHBoxLayout()
        waiting_row.addWidget(QLabel("待机摆头/头发强度"))
        self.waiting_motion_slider = QSlider(Qt.Horizontal)
        self.waiting_motion_slider.setRange(0, 200)
        self.waiting_motion_slider.setValue(
            round(self.saved_waiting_motion_intensity * 100)
        )
        self.waiting_motion_slider.valueChanged.connect(
            self._on_waiting_motion_changed
        )
        self.waiting_motion_value_label = QLabel(
            f"{self.saved_waiting_motion_intensity:.2f}×"
        )
        self.waiting_motion_value_label.setMinimumWidth(52)
        save_waiting_button = QPushButton("保存待机强度")
        save_waiting_button.clicked.connect(self._save_waiting_motion)
        waiting_row.addWidget(self.waiting_motion_slider, 1)
        waiting_row.addWidget(self.waiting_motion_value_label)
        waiting_row.addWidget(save_waiting_button)
        root.addLayout(waiting_row)

        gaze_row = QHBoxLayout()
        gaze_row.addWidget(QLabel("待机视线游移强度"))
        self.waiting_gaze_slider = QSlider(Qt.Horizontal)
        self.waiting_gaze_slider.setRange(0, 200)
        self.waiting_gaze_slider.setValue(
            round(self.saved_waiting_gaze_intensity * 100)
        )
        self.waiting_gaze_slider.valueChanged.connect(
            self._on_waiting_gaze_changed
        )
        self.waiting_gaze_value_label = QLabel(
            f"{self.saved_waiting_gaze_intensity:.2f}×"
        )
        self.waiting_gaze_value_label.setMinimumWidth(52)
        save_gaze_button = QPushButton("保存视线强度")
        save_gaze_button.clicked.connect(self._save_waiting_gaze)
        gaze_row.addWidget(self.waiting_gaze_slider, 1)
        gaze_row.addWidget(self.waiting_gaze_value_label)
        gaze_row.addWidget(save_gaze_button)
        root.addLayout(gaze_row)

        speed_row = QHBoxLayout()
        speed_row.addWidget(QLabel("待机动作速度"))
        self.waiting_motion_speed_slider = QSlider(Qt.Horizontal)
        self.waiting_motion_speed_slider.setRange(50, 200)
        self.waiting_motion_speed_slider.setValue(
            round(self.saved_waiting_motion_speed * 100)
        )
        self.waiting_motion_speed_slider.valueChanged.connect(
            self._on_waiting_motion_speed_changed
        )
        self.waiting_motion_speed_value_label = QLabel(
            f"{self.saved_waiting_motion_speed:.2f}×"
        )
        self.waiting_motion_speed_value_label.setMinimumWidth(52)
        save_speed_button = QPushButton("保存动作速度")
        save_speed_button.clicked.connect(self._save_waiting_motion_speed)
        speed_row.addWidget(self.waiting_motion_speed_slider, 1)
        speed_row.addWidget(self.waiting_motion_speed_value_label)
        speed_row.addWidget(save_speed_button)
        root.addLayout(speed_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        grid = QGridLayout(content)
        grid.setColumnStretch(1, 1)

        for row, (param_id, label, minimum, maximum, step) in enumerate(PARAMETER_SPECS):
            name = QLabel(f"{label}\n{param_id}")
            slider = QSlider(Qt.Horizontal)
            slider.setMinimum(round(minimum / step))
            slider.setMaximum(round(maximum / step))
            slider.valueChanged.connect(self._on_slider_changed)
            value_label = QLabel("0.00")
            value_label.setMinimumWidth(52)
            value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

            self.sliders[param_id] = slider
            self.value_labels[param_id] = value_label
            grid.addWidget(name, row, 0)
            grid.addWidget(slider, row, 1)
            grid.addWidget(value_label, row, 2)

        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        self.status_label = QLabel("")
        root.addWidget(self.status_label)

        buttons = QHBoxLayout()
        recommended_button = QPushButton("恢复推荐值")
        recommended_button.clicked.connect(self._load_recommended_values)
        neutral_button = QPushButton("全部归中")
        neutral_button.clicked.connect(self._load_neutral_values)
        save_button = QPushButton("保存当前情绪")
        save_button.clicked.connect(self._save_current_mood)
        close_button = QPushButton("关闭")
        close_button.clicked.connect(self.accept)

        buttons.addWidget(recommended_button)
        buttons.addWidget(neutral_button)
        buttons.addStretch(1)
        buttons.addWidget(save_button)
        buttons.addWidget(close_button)
        root.addLayout(buttons)

    def _selected_mood(self):
        return self.mood_combo.currentData() or "neutral"

    def _preset_values(self, source, mood):
        values = source.get(mood, {}) if isinstance(source, dict) else {}
        return {
            param_id: values.get(param_id, PARAMETER_DEFAULTS.get(param_id, 0.0))
            for param_id in self.sliders
        }

    def _load_selected_mood(self, *_):
        self._set_slider_values(
            self._preset_values(self.parameter_map, self._selected_mood())
        )
        self.status_label.setText("正在实时预览，尚未保存。")

    def _load_recommended_values(self):
        self._set_slider_values(
            self._preset_values(self.recommended_map, self._selected_mood())
        )
        self.status_label.setText("已恢复推荐值，点击保存后才会写入配置。")

    def _load_neutral_values(self):
        self._set_slider_values({
            param_id: PARAMETER_DEFAULTS.get(param_id, 0.0)
            for param_id in self.sliders
        })
        self.status_label.setText("已全部归中，点击保存后才会写入配置。")

    def _set_slider_values(self, values):
        for param_id, slider in self.sliders.items():
            _, _, minimum, maximum, step = self.spec_by_id[param_id]
            value = float(values.get(param_id, PARAMETER_DEFAULTS.get(param_id, 0.0)))
            value = max(minimum, min(maximum, value))
            slider.blockSignals(True)
            slider.setValue(round(value / step))
            slider.blockSignals(False)
            self.value_labels[param_id].setText(f"{value:.2f}")
        self._preview()

    def _current_values(self):
        result = {}
        for param_id, slider in self.sliders.items():
            step = self.spec_by_id[param_id][4]
            result[param_id] = round(slider.value() * step, 4)
        return result

    def _on_slider_changed(self, *_):
        for param_id, slider in self.sliders.items():
            step = self.spec_by_id[param_id][4]
            self.value_labels[param_id].setText(f"{slider.value() * step:.2f}")
        self.status_label.setText("正在实时预览，尚未保存。")
        self._preview()

    def _preview(self):
        self.controller.preview_parameters(
            self._selected_mood(), self._current_values()
        )

    def _save_current_mood(self):
        mood = self._selected_mood()
        values = self._current_values()
        saved = bool(self.save_callback and self.save_callback(mood, values))
        if saved:
            self.parameter_map[mood] = dict(values)
            self.controller.update_parameter_preset(mood, values)
            self.status_label.setText(f"“{MOOD_LABELS[mood]}”预设已保存。")
        else:
            self.status_label.setText("保存失败，请查看日志。")

    def _on_waiting_motion_changed(self, slider_value):
        intensity = slider_value / 100.0
        applied = self.controller.set_waiting_motion_intensity(intensity)
        self.waiting_motion_value_label.setText(f"{applied:.2f}×")
        self.status_label.setText("正在实时预览待机动作，尚未保存。")

    def _save_waiting_motion(self):
        intensity = self.waiting_motion_slider.value() / 100.0
        saved = bool(
            self.save_waiting_motion_callback
            and self.save_waiting_motion_callback(intensity)
        )
        if saved:
            self.saved_waiting_motion_intensity = intensity
            self.controller.set_waiting_motion_intensity(intensity)
            self.status_label.setText(
                f"待机摆头/头发强度已保存为 {intensity:.2f}×。"
            )
        else:
            self.status_label.setText("待机动作强度保存失败，请查看日志。")

    def _on_waiting_gaze_changed(self, slider_value):
        intensity = slider_value / 100.0
        applied = self.controller.set_waiting_gaze_intensity(intensity)
        self.waiting_gaze_value_label.setText(f"{applied:.2f}×")
        self.status_label.setText("正在实时预览待机视线，尚未保存。")

    def _save_waiting_gaze(self):
        intensity = self.waiting_gaze_slider.value() / 100.0
        saved = bool(
            self.save_waiting_gaze_callback
            and self.save_waiting_gaze_callback(intensity)
        )
        if saved:
            self.saved_waiting_gaze_intensity = intensity
            self.controller.set_waiting_gaze_intensity(intensity)
            self.status_label.setText(
                f"待机视线游移强度已保存为 {intensity:.2f}×。"
            )
        else:
            self.status_label.setText("待机视线强度保存失败，请查看日志。")

    def _on_waiting_motion_speed_changed(self, slider_value):
        speed = slider_value / 100.0
        applied = self.controller.set_waiting_motion_speed(speed)
        self.waiting_motion_speed_value_label.setText(f"{applied:.2f}×")
        self.status_label.setText("正在实时预览待机动作速度，尚未保存。")

    def _save_waiting_motion_speed(self):
        speed = self.waiting_motion_speed_slider.value() / 100.0
        saved = bool(
            self.save_waiting_motion_speed_callback
            and self.save_waiting_motion_speed_callback(speed)
        )
        if saved:
            self.saved_waiting_motion_speed = speed
            self.controller.set_waiting_motion_speed(speed)
            self.status_label.setText(
                f"待机动作速度已保存为 {speed:.2f}×。"
            )
        else:
            self.status_label.setText("待机动作速度保存失败，请查看日志。")

    def _finish_waiting_motion_preview(self):
        self.controller.set_waiting_motion_preview(False)
        self.controller.set_waiting_motion_intensity(
            self.saved_waiting_motion_intensity
        )
        self.controller.set_waiting_gaze_intensity(
            self.saved_waiting_gaze_intensity
        )
        self.controller.set_waiting_motion_speed(
            self.saved_waiting_motion_speed
        )

    def done(self, result):
        self.controller.clear_parameter_preview()
        self._finish_waiting_motion_preview()
        super().done(result)

    def closeEvent(self, event):
        self.controller.clear_parameter_preview()
        self._finish_waiting_motion_preview()
        super().closeEvent(event)
