"""
GUI 入口 —— PySide6 实现的"终端风格"聊天窗口（深色背景、等宽字体、对话气泡）。

运行方式：
    pip install PySide6
    python main_gui.py

跟 main.py（纯控制台版本）的关系：
    main.py 保留不动，仍然可以用控制台方式跑。这个文件是新增的桌面GUI入口，
    两者共用同一套 ConversationOrchestrator / InitiativeEngine 业务逻辑，
    只是"怎么呈现"不一样——这正是之前做 Orchestrator 重构时带来的好处：
    业务逻辑跟呈现层早就解耦了，换一种界面不需要碰底层逻辑。

为什么用 Qt 信号/槽对接后台线程：
    AI调用、InitiativeEngine 的后台检查都跑在非GUI线程，但界面控件只能在
    主线程更新。Qt的信号机制天生是线程安全的"跨线程消息传递"，用它来对接
    是标准做法，不需要自己处理锁或者轮询。

为以后接 Live2D / TTS 留的位置：
    这个窗口骨架以后可以在右侧或者背景加一块 OpenGL 画布渲染 Live2D 模型
    （用 live2d-py，它明确支持嵌入 PySide6 窗口），AI回复文本流式产出的同时
    可以同步调用 TTS 播放、驱动 Live2D 嘴型动作——具体怎么接，到时候再设计，
    现在先把"文字聊天在GUI里能正常跑"这一层先做稳。

这一版加入的视觉效果：
    - 对话气泡样式（用户靠右、Mio靠左，各自带背景色块）
    - 流式输出时的打字机光标闪烁效果
    - 发送后到第一个字返回之前的"Mio 正在输入..."动态提示
    - 顶部状态栏：实时显示当前心情/好感度/熟悉度

实现说明：
    聊天记录现在用"整体重新渲染"的方式实现（每次有新内容就重新拼出完整HTML
    再调用 setHtml），而不是之前版本的"逐段追加"。这是因为气泡对齐 + 光标闪烁
    都需要"修改最后一条消息的显示内容"，追加模式做不到这一点，整体重渲染虽然
    看起来"重"，但对于聊天这种文本量级（最多几十KB），性能完全够用。
"""

import sys
import html
import threading
import datetime

from PySide6.QtCore import Qt, QThread, Signal, QObject, QTimer
from PySide6.QtGui import QFont, QTextCursor, QKeyEvent, QSurfaceFormat
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLineEdit, QPushButton, QLabel
)

from context_manager import ContextManager
from config_loader import load_config
from ai.chat import generate_greeting
from memory_manager import load_memory
from emotion_manager import load_emotion
from profile_manager import load_profile
from relationship_manager import load_relationship
from orchestrator import ConversationOrchestrator
from initiative_engine import InitiativeEngine
from logger_utils import get_logger

logger = get_logger(__name__)

# Live2D 相关依赖是可选的：装了 live2d-py + PyOpenGL 就显示角色立绘，
# 没装也完全不影响聊天功能正常使用（优雅降级，而不是强制要求所有人
# 都装这些额外依赖才能跑GUI）。
try:
    from PySide6.QtOpenGLWidgets import QOpenGLWidget
    from OpenGL.GL import glViewport
    import live2d.v3 as live2d
    LIVE2D_AVAILABLE = True
except ImportError as e:
    LIVE2D_AVAILABLE = False
    logger.info("未检测到 live2d-py / PyOpenGL，将不显示角色立绘（不影响聊天功能）：%s", e)

# ⚠️ 改成你本机实际的模型路径。留空字符串则不显示立绘。
MODEL_JSON_PATH = r"C:\mio\mio\MIO.model3.json"

# 主动聊天的可调参数，跟 main.py 保持一致
CHECK_INTERVAL_MINUTES = 5
IDLE_THRESHOLD_MINUTES = 30
PROACTIVE_MIN_INTERVAL_MINUTES = 120
PROACTIVE_MAX_PER_DAY = 3

# 配色：跳出"黑客终端绿"的俗套，改用低饱和度的暖灰底 + 鼠尾草绿/暖棕调，更显克制精致
BG_COLOR = "#0d0d0f"
PANEL_COLOR = "#17171b"
FG_COLOR = "#e8e6e3"
USER_COLOR = "#d4a373"
MIO_COLOR = "#07ed2e"
SYSTEM_COLOR = "#6b6b70"
ERROR_COLOR = "#e07a7a"
BORDER_COLOR = "#26262b"

# 字体：优先用 Cascadia Code / JetBrains Mono 这类专为代码/终端设计的字体，
# 比系统默认的 Consolas 更有设计感；如果本机没装，会自动退回到 Consolas。
# Cascadia Code 随 Windows Terminal / VS Code 安装，大概率已经有；
# JetBrains Mono 需要自行下载安装：https://www.jetbrains.com/lp/mono/
FONT_FAMILY = "'Cascadia Code', 'JetBrains Mono', Consolas, 'Courier New', monospace"

# 心情 -> 状态栏显示用的图标和文字
MOOD_DISPLAY = {
    "happy": ("😊", "开心"),
    "sad": ("😢", "低落"),
    "shy": ("🙈", "害羞"),
    "tired": ("😪", "疲惫"),
    "neutral": ("🙂", "平静"),
}

CURSOR_BLINK_INTERVAL_MS = 500
TYPING_DOT_INTERVAL_MS = 450


class ChatWorker(QThread):
    """
    在后台线程跑完整的一轮对话（prepare_turn -> stream_reply -> finalize_turn），
    通过信号把结果安全地传回GUI主线程，避免长时间的AI调用卡住界面。
    """

    chunk_received = Signal(str)
    turn_finished = Signal()
    error_occurred = Signal(str)

    def __init__(self, orchestrator, user_message):
        super().__init__()
        self.orchestrator = orchestrator
        self.user_message = user_message

    def run(self):
        try:
            prepared = self.orchestrator.prepare_turn(self.user_message)
            raw_reply = ""
            for chunk in self.orchestrator.stream_reply(prepared):
                raw_reply += chunk
                self.chunk_received.emit(chunk)
            self.orchestrator.finalize_turn(prepared, raw_reply)
        except Exception as e:
            logger.error("GUI对话处理出错：%s", e)
            self.error_occurred.emit(str(e))
        finally:
            self.turn_finished.emit()


class ProactiveBridge(QObject):
    """
    一个轻量的 QObject，专门用来承接 InitiativeEngine 后台线程发来的主动消息。
    InitiativeEngine 本身是普通的 threading.Thread，不是 Qt 线程，
    但只要调用的是 QObject 的信号 emit()，Qt 会自动把它安全地路由到
    这个 QObject 所属线程（这里是GUI主线程）的槽函数里执行，不需要自己加锁。
    """
    message_received = Signal(str)


if LIVE2D_AVAILABLE:
    class Live2DWidget(QOpenGLWidget):
        """
        渲染 Live2D 角色立绘的画布。

        加载逻辑是从独立验证脚本（test_live2d_load.py）里migrate过来的，
        经过了非常仔细的排查才确认可用：关键是 live2d.glInit()（不是
        live2d.glewInit()，那是个不存在的方法名，调用会抛AttributeError；
        这个异常在Qt虚函数回调里如果不用try/except接住，会被静默吞掉，
        表现得像是原生崩溃，实际只是个普通的Python异常）。
        """

        FRAME_INTERVAL_MS = 16  # 约60FPS的重绘间隔

        def __init__(self, model_path):
            super().__init__()
            self.model_path = model_path
            self.model = None
            self.load_failed = False

        def initializeGL(self):
            try:
                live2d.init()
                live2d.glInit()

                self.model = live2d.LAppModel()
                self.model.LoadModelJson(self.model_path)
                self.model.Resize(self.width(), self.height())
                logger.info("Live2D 模型加载成功：%s", self.model_path)
            except Exception as e:
                logger.error("Live2D 模型加载失败，立绘区域将保持空白：%s", e)
                self.load_failed = True
                self.model = None

            # 启动持续重绘的定时器，驱动呼吸/物理摆动等待机动画
            self._frame_timer = QTimer(self)
            self._frame_timer.timeout.connect(self.update)
            self._frame_timer.start(self.FRAME_INTERVAL_MS)

        def resizeGL(self, w, h):
            glViewport(0, 0, w, h)
            if self.model:
                self.model.Resize(w, h)

        def paintGL(self):
            live2d.clearBuffer()
            if self.model:
                self.model.Update()
                self.model.Draw()

        def closeEvent(self, event):
            if hasattr(self, "_frame_timer"):
                self._frame_timer.stop()
            super().closeEvent(event)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.config = load_config()
        conversation_history = load_memory()
        emotion = load_emotion()
        profile = load_profile()
        relationship = load_relationship()
        self.context = ContextManager(self.config, emotion, profile, relationship)

        # emotion / relationship 这两个字典会被 update_emotion / update_relationship
        # 原地修改（不是重新赋值新对象），所以这里保留的引用会一直反映最新状态，
        # 状态栏直接读这两个引用就行，不需要额外的同步机制。
        self.emotion = emotion
        self.relationship = relationship

        self.state_lock = threading.Lock()

        self.orchestrator = ConversationOrchestrator(
            self.config, self.context, conversation_history, emotion, profile, relationship,
            lock=self.state_lock
        )

        self.proactive_bridge = ProactiveBridge()
        self.proactive_bridge.message_received.connect(self._on_proactive_message)

        self.initiative_engine = InitiativeEngine(
            self.config, self.context, conversation_history, emotion, profile, relationship,
            lock=self.state_lock,
            check_interval_minutes=CHECK_INTERVAL_MINUTES,
            idle_threshold_minutes=IDLE_THRESHOLD_MINUTES,
            proactive_min_interval_minutes=PROACTIVE_MIN_INTERVAL_MINUTES,
            proactive_max_per_day=PROACTIVE_MAX_PER_DAY,
            # 关键：传入一个会 emit 信号的回调，而不是让它直接 print。
            # GUI模式下不再需要 prompt_toolkit 的 patch_stdout 技巧，
            # 因为信号/槽机制天生就不会跟用户输入冲突。
            on_message=self.proactive_bridge.message_received.emit
        )

        self._worker = None  # 当前正在跑的 ChatWorker，发送下一条前要确认它已结束

        # 聊天记录的"数据模型"：每条是 {"role": "user"/"mio"/"system", "text": "..."}
        # 渲染时统一从这份数据重新生成HTML，而不是直接操作富文本控件的中间状态。
        self.messages = []

        # 流式接收中的状态
        self.is_streaming = False
        self.streaming_buffer = ""
        self.streaming_start_time = ""
        self.cursor_visible = True

        # "正在输入"提示的状态
        self.is_typing = False
        self.typing_dot_count = 1

        self._build_ui()
        self._start_timers()
        self._start_background_thread()
        self._show_greeting()
        self._update_status_bar()

    # ------------------------------------------------------------------
    # 界面搭建
    # ------------------------------------------------------------------

    def _build_ui(self):
        self.setWindowTitle(f"{self.config.get('assistant_name', 'Anime Assistant')}")
        self.resize(1040, 640) if (LIVE2D_AVAILABLE and MODEL_JSON_PATH) else self.resize(760, 600)

        central = QWidget()
        self.setCentralWidget(central)

        # 顶层用左右分栏：左边聊天面板，右边Live2D立绘（如果可用的话）。
        # 没装live2d-py或者没配置模型路径时，直接不创建右侧画布，
        # 布局自动退化成原来的单栏聊天窗口，不影响正常使用。
        outer_layout = QHBoxLayout(central)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        chat_panel = QWidget()
        layout = QVBoxLayout(chat_panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # 状态栏：真正的多栏布局，而不是拼一整条字符串。
        # 每一栏独立控制间距、字号、颜色层级（数值比标签稍微突出一点）。
        status_row = QHBoxLayout()
        status_row.setSpacing(24)

        self.status_mood_label = QLabel()
        self.status_energy_label = QLabel()
        self.status_affection_label = QLabel()
        self.status_familiarity_label = QLabel()

        for lbl in (
            self.status_mood_label, self.status_energy_label,
            self.status_affection_label, self.status_familiarity_label
        ):
            lbl.setFont(QFont(FONT_FAMILY, 10))
            lbl.setTextFormat(Qt.RichText)
            status_row.addWidget(lbl)

        status_row.addStretch(1)
        layout.addLayout(status_row)

        self.chat_log = QTextEdit()
        self.chat_log.setReadOnly(True)
        self.chat_log.setFont(QFont(FONT_FAMILY, 11))
        layout.addWidget(self.chat_log)

        input_row = QHBoxLayout()
        self.input_line = QLineEdit()
        self.input_line.setFont(QFont(FONT_FAMILY, 11))
        self.input_line.setPlaceholderText("输入消息，回车发送（输入 exit 退出）")
        self.input_line.returnPressed.connect(self._on_send)
        input_row.addWidget(self.input_line)

        self.send_button = QPushButton("发送")
        self.send_button.clicked.connect(self._on_send)
        input_row.addWidget(self.send_button)

        layout.addLayout(input_row)

        outer_layout.addWidget(chat_panel, stretch=3)

        # Live2D 立绘画布：只在依赖装好且配置了模型路径时才创建，
        # 加载失败也不会影响聊天面板正常工作（Live2DWidget内部有try/except兜底）。
        self.live2d_widget = None
        if LIVE2D_AVAILABLE and MODEL_JSON_PATH:
            self.live2d_widget = Live2DWidget(MODEL_JSON_PATH)
            self.live2d_widget.setMinimumWidth(280)
            outer_layout.addWidget(self.live2d_widget, stretch=2)

        self._apply_terminal_style()

    def _apply_terminal_style(self):
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {BG_COLOR};
            }}
            QLabel {{
                color: {SYSTEM_COLOR};
                padding: 2px 4px;
            }}
            QTextEdit {{
                background-color: {BG_COLOR};
                color: {FG_COLOR};
                border: 1px solid {BORDER_COLOR};
                border-radius: 4px;
                padding: 8px;
            }}
            QLineEdit {{
                background-color: {PANEL_COLOR};
                color: {FG_COLOR};
                border: 1px solid {BORDER_COLOR};
                border-radius: 4px;
                padding: 6px;
            }}
            QPushButton {{
                background-color: {PANEL_COLOR};
                color: {MIO_COLOR};
                border: 1px solid {BORDER_COLOR};
                border-radius: 4px;
                padding: 6px 16px;
            }}
            QPushButton:hover {{
                border-color: {MIO_COLOR};
            }}
        """)

    def _start_timers(self):
        # 光标闪烁：只在流式输出时才会触发重渲染，平时空转不影响性能
        self.cursor_timer = QTimer(self)
        self.cursor_timer.timeout.connect(self._on_cursor_tick)
        self.cursor_timer.start(CURSOR_BLINK_INTERVAL_MS)

        # "正在输入"的省略号动态效果
        self.typing_timer = QTimer(self)
        self.typing_timer.timeout.connect(self._on_typing_tick)
        self.typing_timer.start(TYPING_DOT_INTERVAL_MS)

    # ------------------------------------------------------------------
    # 状态栏
    # ------------------------------------------------------------------

    def _update_status_bar(self):
        mood = self.emotion.get("mood", "neutral")
        energy = self.emotion.get("energy", 0)
        icon, mood_text = MOOD_DISPLAY.get(mood, ("🙂", mood))

        affection = self.relationship.get("affection", 0)
        familiarity = self.relationship.get("familiarity", 0)

        # 标签用 SYSTEM_COLOR 弱化，数值用 FG_COLOR 强调，做出层级感，
        # 比之前"一整条同色字符串"更接近专业面板的排版方式。
        self.status_mood_label.setText(
            f'{icon} <span style="color:{SYSTEM_COLOR};">心情</span> '
            f'<span style="color:{FG_COLOR};">{mood_text}</span>'
        )
        self.status_energy_label.setText(
            f'<span style="color:{SYSTEM_COLOR};">精力</span> '
            f'<span style="color:{FG_COLOR};">{int(energy)}</span>'
        )
        self.status_affection_label.setText(
            f'<span style="color:{SYSTEM_COLOR};">好感度</span> '
            f'<span style="color:{USER_COLOR};">{int(affection)}</span>'
        )
        self.status_familiarity_label.setText(
            f'<span style="color:{SYSTEM_COLOR};">熟悉度</span> '
            f'<span style="color:{MIO_COLOR};">{int(familiarity)}</span>'
        )

    # ------------------------------------------------------------------
    # 渲染：整个聊天记录统一从 self.messages + 流式/输入状态重新生成
    # ------------------------------------------------------------------

    def _render(self):
        parts = ["<table width='100%' cellspacing='10' cellpadding='0'>"]

        for msg in self.messages:
            parts.append(self._render_message_row(msg["role"], msg["text"], timestamp=msg.get("time")))

        if self.is_streaming:
            cursor = "▌" if self.cursor_visible else "&nbsp;"
            text = html.escape(self.streaming_buffer) + cursor
            parts.append(self._render_message_row(
                "mio", text, escape=False, timestamp=self.streaming_start_time
            ))
        elif self.is_typing:
            dots = "." * self.typing_dot_count
            parts.append(
                f"<tr><td align='left'>"
                f"<span style='color:{SYSTEM_COLOR};'><i>Mio 正在输入{dots}</i></span>"
                f"</td></tr>"
            )

        parts.append("</table>")
        self.chat_log.setHtml("".join(parts))

        scrollbar = self.chat_log.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _new_message(self, role, text):
        """统一生成带时间戳的消息字典，供 self.messages 存储和渲染使用"""
        return {
            "role": role,
            "text": text,
            "time": datetime.datetime.now().strftime("%H:%M")
        }

    def _render_message_row(self, role, text, escape=True, timestamp=None):
        display_text = html.escape(text) if escape else text
        time_html = (
            f"<span style='color:{SYSTEM_COLOR}; font-size:9px;'> {timestamp}</span>"
            if timestamp else ""
        )

        if role == "user":
            return (
                f"<tr><td align='right'>"
                f"<span style='color:{USER_COLOR};'>{display_text}</span>{time_html}"
                f"</td></tr>"
            )
        elif role == "mio":
            return (
                f"<tr><td align='left'>"
                f"<span style='color:{MIO_COLOR};'><b>Mio</b></span>{time_html}<br>"
                f"<span style='color:{MIO_COLOR};'>{display_text}</span>"
                f"</td></tr>"
            )
        else:  # system
            return (
                f"<tr><td align='center'>"
                f"<span style='color:{SYSTEM_COLOR}; font-size:10px;'>{display_text}</span>"
                f"</td></tr>"
            )

    def _show_greeting(self):
        greeting = generate_greeting(self.context.get_context())
        self.messages.append(self._new_message("system", f"{self.config.get('assistant_name', 'Mio')} 已启动"))
        self.messages.append(self._new_message("mio", greeting))
        self._render()

    # ------------------------------------------------------------------
    # 发送消息 / 接收流式回复
    # ------------------------------------------------------------------

    def _on_send(self):
        text = self.input_line.text().strip()
        if not text:
            return

        if self._worker is not None and self._worker.isRunning():
            # 上一轮还没处理完，先不让用户连续发送，避免并发调用 orchestrator
            return

        if text.lower() in ("exit", "quit"):
            self.close()
            return

        self.input_line.clear()
        self.messages.append(self._new_message("user", text))

        self.is_typing = True
        self.typing_dot_count = 1
        self._render()

        self.input_line.setEnabled(False)
        self.send_button.setEnabled(False)

        self._worker = ChatWorker(self.orchestrator, text)
        self._worker.chunk_received.connect(self._on_chunk_received)
        self._worker.error_occurred.connect(self._on_worker_error)
        self._worker.turn_finished.connect(self._on_turn_finished)
        self._worker.start()

    def _on_chunk_received(self, chunk):
        if self.is_typing:
            # 第一个字到了，"正在输入"提示退场，切换成真正的流式气泡
            self.is_typing = False
            self.is_streaming = True
            self.streaming_buffer = ""
            self.streaming_start_time = datetime.datetime.now().strftime("%H:%M")

        self.streaming_buffer += chunk
        self._render()

    def _on_turn_finished(self):
        # 把流式过程中的临时气泡固化成正式的一条消息
        if self.streaming_buffer:
            self.messages.append(self._new_message("mio", self.streaming_buffer))

        self.is_streaming = False
        self.is_typing = False
        self.streaming_buffer = ""

        self._render()
        self._update_status_bar()

        self.input_line.setEnabled(True)
        self.send_button.setEnabled(True)
        self.input_line.setFocus()

    def _on_worker_error(self, error_text):
        logger.error("聊天处理失败：%s", error_text)
        self.is_streaming = False
        self.is_typing = False
        self.streaming_buffer = ""
        self.messages.append(self._new_message("system", "（出了点问题，请稍后再试）"))
        self._render()

    def _on_proactive_message(self, message):
        """
        InitiativeEngine 通过信号传来的主动消息，运行在GUI主线程，
        可以安全地直接操作界面控件。
        """
        self.messages.append(self._new_message("system", "Mio 突然找你说话"))
        self.messages.append(self._new_message("mio", message))
        self._render()
        self._update_status_bar()

    # ------------------------------------------------------------------
    # 定时器回调：光标闪烁 / 正在输入的省略号动画
    # ------------------------------------------------------------------

    def _on_cursor_tick(self):
        if not self.is_streaming:
            return
        self.cursor_visible = not self.cursor_visible
        self._render()

    def _on_typing_tick(self):
        if not self.is_typing:
            return
        self.typing_dot_count = (self.typing_dot_count % 3) + 1
        self._render()

    # ------------------------------------------------------------------
    # 后台线程 + 关闭收尾
    # ------------------------------------------------------------------

    def _start_background_thread(self):
        self._background_thread = threading.Thread(
            target=self.initiative_engine.run_loop, daemon=True
        )
        self._background_thread.start()

    def closeEvent(self, event):
        self.cursor_timer.stop()
        self.typing_timer.stop()
        if self.live2d_widget is not None and hasattr(self.live2d_widget, "_frame_timer"):
            self.live2d_widget._frame_timer.stop()
        self.initiative_engine.stop()
        self.orchestrator.shutdown()
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(2000)
        super().closeEvent(event)


def main():
    if LIVE2D_AVAILABLE and MODEL_JSON_PATH:
        # 显式请求 OpenGL 2.1（不涉及Profile概念），这是经过反复排查后
        # 确认在这套环境下最稳妥的配置，必须在 QApplication 创建之前设置。
        fmt = QSurfaceFormat()
        fmt.setVersion(2, 1)
        QSurfaceFormat.setDefaultFormat(fmt)

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()