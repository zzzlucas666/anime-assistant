"""Optional Qt OpenGL canvas for rendering a Cubism model."""

from PySide6.QtCore import QTimer

from anime_assistant.infrastructure.logging import get_logger


logger = get_logger(__name__)

try:
    from PySide6.QtOpenGLWidgets import QOpenGLWidget
    from OpenGL.GL import glViewport
    import live2d.v3 as live2d

    LIVE2D_AVAILABLE = True
except ImportError as exc:
    QOpenGLWidget = object
    live2d = None
    LIVE2D_AVAILABLE = False
    logger.info(
        "未检测到 live2d-py / PyOpenGL，将不显示角色立绘（不影响聊天功能）：%s",
        exc,
    )


if LIVE2D_AVAILABLE:
    class Live2DWidget(QOpenGLWidget):
        """Continuously render a Live2D model in a Qt OpenGL widget."""

        FRAME_INTERVAL_MS = 33

        def __init__(self, model_path):
            super().__init__()
            self.model_path = model_path
            self.model = None
            self.load_failed = False
            self.character_controller = None

        def set_character_controller(self, controller):
            self.character_controller = controller

        def initializeGL(self):
            try:
                live2d.init()
                live2d.glInit()
                self.model = live2d.LAppModel()
                self.model.LoadModelJson(self.model_path)
                self.model.Resize(self.width(), self.height())
                if self.character_controller:
                    self.character_controller.refresh_current_expression()
                logger.info("Live2D 模型加载成功：%s", self.model_path)
            except Exception as exc:
                logger.error("Live2D 模型加载失败，立绘区域将保持空白：%s", exc)
                self.load_failed = True
                self.model = None

            self._frame_timer = QTimer(self)
            self._frame_timer.timeout.connect(self.update)
            self._frame_timer.start(self.FRAME_INTERVAL_MS)

        def resizeGL(self, width, height):
            glViewport(0, 0, width, height)
            if self.model:
                self.model.Resize(width, height)

        def paintGL(self):
            live2d.clearBuffer()
            if self.model:
                self.model.Update()
                if self.character_controller:
                    self.character_controller.tick()
                self.model.Draw()

        def set_mouth_open(self, value):
            if self.model:
                self._set_parameter(
                    "ParamMouthOpenY",
                    max(0.0, min(1.0, float(value))),
                )

        def set_parameters(self, parameters):
            if not self.model or not isinstance(parameters, dict):
                return
            for param_id, value in parameters.items():
                try:
                    self._set_parameter(param_id, float(value))
                except (TypeError, ValueError):
                    logger.debug("Live2D 参数值不是数字，已跳过：%s=%s", param_id, value)

        def set_expression(self, expression_name):
            if not self.model or not expression_name:
                return
            for method_name in ("SetExpression", "setExpression"):
                method = getattr(self.model, method_name, None)
                if callable(method):
                    try:
                        method(expression_name)
                        return
                    except Exception as exc:
                        logger.debug(
                            "Live2D 表情切换失败 %s(%s)：%s",
                            method_name,
                            expression_name,
                            exc,
                        )

        def start_motion(self, motion_group, index=0, priority=3):
            if not self.model or not motion_group:
                return
            method = getattr(self.model, "StartMotion", None)
            if callable(method):
                try:
                    method(motion_group, index, priority)
                except Exception as exc:
                    logger.debug(
                        "Live2D 动作触发失败 StartMotion(%s)：%s",
                        motion_group,
                        exc,
                    )

        def _set_parameter(self, param_id, value):
            candidates = (
                ("SetParameterValue", (param_id, value)),
                ("SetParameterValue", (param_id, value, 1.0)),
                ("SetParameterValueById", (param_id, value)),
                ("SetParameterValueById", (param_id, value, 1.0)),
                ("AddParameterValue", (param_id, value)),
                ("AddParameterValue", (param_id, value, 1.0)),
                ("AddParameterValueById", (param_id, value)),
                ("AddParameterValueById", (param_id, value, 1.0)),
            )
            for method_name, args in candidates:
                method = getattr(self.model, method_name, None)
                if not callable(method):
                    continue
                try:
                    method(*args)
                    return True
                except Exception:
                    continue
            return False

        def closeEvent(self, event):
            if hasattr(self, "_frame_timer"):
                self._frame_timer.stop()
            super().closeEvent(event)
else:
    Live2DWidget = None
