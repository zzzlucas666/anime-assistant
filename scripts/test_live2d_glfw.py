"""
用 GLFW（而不是Qt）创建OpenGL窗口的独立测试。

目的：目前所有测试都是通过 Qt 的 QOpenGLWidget 创建OpenGL环境的，
换一个完全不同的、更"原生直给"的窗口库（GLFW）来试，
可以判断问题是不是出在"Qt创建OpenGL上下文的具体方式"跟
live2d-py 内部 glewInit() 的兼容性上。

运行前先装 glfw：
    pip install glfw
"""

import sys
import os

import glfw
from OpenGL.GL import glViewport, glClearColor, glClear, GL_COLOR_BUFFER_BIT
import live2d.v3 as live2d


def main():
    model_json_path = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("LIVE2D_MODEL_PATH")
    if not model_json_path or not os.path.isfile(model_json_path):
        print("❌ 请通过命令行参数或 LIVE2D_MODEL_PATH 环境变量提供有效的 model3.json")
        sys.exit(1)

    if not glfw.init():
        print("❌ GLFW 初始化失败")
        sys.exit(1)
    print("[步骤A] glfw.init() 完成")

    # 明确请求一个兼容模式的上下文（不是Core Profile）
    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 2)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 1)

    window = glfw.create_window(600, 800, "GLFW + Live2D 测试", None, None)
    if not window:
        print("❌ 创建GLFW窗口失败")
        glfw.terminate()
        sys.exit(1)
    print("[步骤B] glfw 窗口创建完成")

    glfw.make_context_current(window)
    print("[步骤C] OpenGL 上下文已绑定为当前上下文")

    live2d.init()
    print("[步骤D] live2d.init() 完成")

    try:
        live2d.glInit()
        print("[步骤E] live2d.glInit() 完成")
    except Exception as e:
        print(f"❌ live2d.glInit() 调用失败：{e}")
        glfw.terminate()
        sys.exit(1)

    model = live2d.LAppModel()
    model.LoadModelJson(model_json_path)
    model.Resize(600, 800)
    print("✅ 模型加载成功！")

    while not glfw.window_should_close(window):
        glClearColor(0.1, 0.1, 0.1, 1.0)
        glClear(GL_COLOR_BUFFER_BIT)

        model.Update()
        model.Draw()

        glfw.swap_buffers(window)
        glfw.poll_events()

    live2d.dispose()
    glfw.terminate()


if __name__ == "__main__":
    main()
