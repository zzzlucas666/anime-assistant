"""
Live2D 加载验证脚本 —— 独立跑，不接入项目任何其他逻辑。

目的：确认 live2d-py 能不能正确读取 MIO.model3.json，并把模型渲染出来。
跑通这一步之后，才把 Live2D 画布正式接进 main_gui.py。

运行前准备：
    1. pip install live2d-py PySide6 PyOpenGL
    2. 把这五个文件放进同一个文件夹结构（保持原有的相对引用关系不要动）：
       MIO.model3.json
       MIO.moc3
       MIO.physics3.json
       MIO.cdi3.json
       MIO.1024/texture_00.png   (贴图文件夹要跟 model3.json 同级)
    3. 启动时把 model3.json 路径作为第一个命令行参数传入，
       或设置 LIVE2D_MODEL_PATH 环境变量

这份脚本的代码结构参考了 live2d-py 官方仓库和社区反馈的真实可用示例
（GitHub issue #98），而不是凭空猜的写法，尽量降低"文档过时/API对不上"的风险。
但因为我这边没有真实的显示器/OpenGL环境，没法在这里替你实际跑一遍，
你需要在自己电脑上运行，把控制台输出和窗口截图发给我，方便一起排查。
"""

import sys
import os
import json

# OpenGL 渲染后端切换，用于诊断排除法："desktop" / "software" / "angle"
OPENGL_BACKEND = "desktop"

from OpenGL.GL import glViewport
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtOpenGLWidgets import QOpenGLWidget

import live2d.v3 as live2d


def check_referenced_files(model_json_path):
    """
    在调用任何原生代码之前，先用纯Python检查 model3.json 里引用的
    moc3/physics3/cdi3/贴图文件是否都真实存在。

    这么做的原因：如果某个引用文件缺失或文件名对不上，Cubism原生SDK
    在读取时经常不会走"安全报错"的路径，而是直接崩溃（我们上一次遇到的
    "没有任何Python报错、程序却直接退出"就很可能是这个原因）。
    提前用Python检查一遍，能把这种情况变成一条清晰的报错，而不是静默崩溃。
    """
    base_dir = os.path.dirname(model_json_path)
    with open(model_json_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    refs = config.get("FileReferences", {})
    files_to_check = []

    if refs.get("Moc"):
        files_to_check.append(("Moc", refs["Moc"]))
    if refs.get("Physics"):
        files_to_check.append(("Physics", refs["Physics"]))
    if refs.get("DisplayInfo"):
        files_to_check.append(("DisplayInfo", refs["DisplayInfo"]))
    for tex in refs.get("Textures", []):
        files_to_check.append(("Texture", tex))

    all_ok = True
    print("── 文件完整性检查 ──")
    for label, rel_path in files_to_check:
        full_path = os.path.join(base_dir, rel_path)
        exists = os.path.exists(full_path)
        status = "✅" if exists else "❌ 缺失"
        print(f"  [{label}] {full_path}  {status}")
        if not exists:
            all_ok = False
    print("────────────────────")
    return all_ok


class Live2DTestWidget(QOpenGLWidget):
    def __init__(self, model_path):
        super().__init__()
        self.model_path = model_path
        self.model = None

    def initializeGL(self):
        print("[步骤1] 进入 initializeGL"); sys.stdout.flush()

        try:
            # live2d-py 需要在 OpenGL 上下文创建之后才能初始化，
            # 所以 live2d.init() / glInit() 必须放在 initializeGL 里，
            # 不能放在窗口显示之前调用。
            live2d.init()
            print("[步骤2] live2d.init() 完成"); sys.stdout.flush()

            # 之前一直写成 live2d.glewInit()，这个方法名是错的（旧版参考代码
            # 里的写法），正确名字是 live2d.glInit()。之前这行异常因为在
            # Qt虚函数回调里没被try/except接住，被静默吞掉了，表现得像是
            # "原生崩溃"，其实只是个普通的 AttributeError。
            live2d.glInit()
            print("[步骤3] live2d.glInit() 完成"); sys.stdout.flush()

            self.model = live2d.LAppModel()
            print("[步骤4] LAppModel() 实例创建完成"); sys.stdout.flush()

            self.model.LoadModelJson(self.model_path)
            print("[步骤5] LoadModelJson() 完成"); sys.stdout.flush()

            self.model.Resize(self.width(), self.height())
            print("[步骤6] Resize() 完成"); sys.stdout.flush()

            print("✅ 模型加载成功！")
            print(f"   Part 数量: {self.model.GetPartCount()}")
        except Exception as e:
            print(f"❌ 加载失败（Python可捕获的异常）：{e}")
            import traceback
            traceback.print_exc()
            QApplication.instance().quit()

    def resizeGL(self, w, h):
        glViewport(0, 0, w, h)
        if self.model:
            self.model.Resize(w, h)

    def paintGL(self):
        live2d.clearBuffer()
        if self.model:
            self.model.Update()
            self.model.Draw()


class TestWindow(QMainWindow):
    def __init__(self, model_path):
        super().__init__()
        self.setWindowTitle("Live2D 加载验证 - MIO")
        self.resize(600, 800)

        self.widget = Live2DTestWidget(model_path)
        self.setCentralWidget(self.widget)

        # 60FPS 左右的刷新定时器，触发重绘
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.widget.update)
        self.timer.start(16)

    def closeEvent(self, event):
        self.timer.stop()
        live2d.dispose()
        event.accept()


def main():
    model_json_path = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("LIVE2D_MODEL_PATH")
    if not model_json_path or not os.path.isfile(model_json_path):
        print("❌ 请通过命令行参数或 LIVE2D_MODEL_PATH 环境变量提供有效的 model3.json")
        sys.exit(1)

    # 先做文件完整性检查，把"缺文件导致原生崩溃"这种情况
    # 变成一条清晰的Python报错，而不是让程序静默退出。
    if not check_referenced_files(model_json_path):
        print("❌ 上面标了❌的文件缺失，请检查文件是否都放对了位置。")
        sys.exit(1)

    # 打开 live2d-py 的详细原生日志（如果这个版本支持的话）。
    # 不同版本的 live2d-py 这个API名字可能不一样，用 hasattr 保护一下，
    # 避免因为这行可选的诊断日志把整个测试脚本卡死——它不是核心流程。
    if hasattr(live2d, "setLogEnable"):
        live2d.setLogEnable(True)
    else:
        print("（提示：当前版本没有 setLogEnable，跳过详细日志开关，不影响后续测试）")

    # 显式指定 OpenGL 上下文格式，必须在创建 QApplication 之前设置。
    #
    # 关键修复：请求 OpenGL 2.1，而不是 3.3 Compatibility。
    # 原因：glewInit() 内部会调用已经过时的 glGetString(GL_EXTENSIONS)，
    # 这个函数在 "Core Profile"（现代OpenGL模式）下会返回NULL，
    # 老版本GLEW代码没有对此做防御，直接崩溃——这是一个很经典的已知问题。
    # 之前请求"3.3 Compatibility"理论上能避免，但部分显卡驱动对这个请求
    # 的遵守程度不一致，实际可能还是给了Core Profile。
    # OpenGL 2.1 诞生时"Profile"概念还不存在，几乎所有Windows驱动都会
    # 稳定给出兼容模式上下文，从根源上绕开这个不确定性。
    fmt = QSurfaceFormat()
    fmt.setVersion(2, 1)
    QSurfaceFormat.setDefaultFormat(fmt)

    # 渲染后端切换：如果 "desktop" 模式还是崩溃，改成 "software" 试试，
    # 用来判断是不是显卡驱动/硬件OpenGL支持的问题（软件渲染会慢很多，
    # 但兼容性最好，纯粹用来做诊断排除法）。
    if OPENGL_BACKEND == "desktop":
        QApplication.setAttribute(Qt.AA_UseDesktopOpenGL, True)
    elif OPENGL_BACKEND == "software":
        QApplication.setAttribute(Qt.AA_UseSoftwareOpenGL, True)
    # "angle"（默认不设置任何属性）则完全不干预，用Qt在这台机器上的默认行为

    app = QApplication(sys.argv)
    window = TestWindow(model_json_path)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
