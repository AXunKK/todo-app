import socket
import threading

import webview
from werkzeug.serving import make_server

from app import app

# ==配置项==
HOST = "127.0.0.1"
PORT = 5001


# ==服务器管理==
def start_server():
    try:
        # 尝试绑定固定端口 5001
        # threaded=True 允许 Werkzeug 开启多线程处理并发请求
        return make_server(HOST, PORT, app, threaded=True)
    except OSError:
        # 若 5001 端口已被占用（如存在未退出的调试实例），
        # 则传入端口 0，让操作系统自动分配一个可用的随机端口
        return make_server(HOST, 0, app, threaded=True)


# ==异常处理==
def show_error(message):
    # 构造一段极简的 HTML，用于在桌面窗口中展示启动失败的错误信息
    page = (
        "<html><body style='font-family:sans-serif;padding:32px'>"
        f"<h2>启动失败</h2><p>{message}</p>"
        "</body></html>"
    )
    # 创建并启动一个用于展示错误信息的 pywebview 窗口
    webview.create_window("启动失败", html=page, width=560, height=260)
    webview.start()


# ==主程序入口==
def main():
    try:
        # ==实例化 WSGI 服务器对象（此时还未开始监听请求）==
        server = start_server()
    except OSError as exc:
        # 极端情况：连随机端口都无法绑定（如系统网络栈异常）
        show_error(exc)
        return 1

    # ==启动服务器==
    # 因为 serve_forever() 是阻塞循环，必须放入后台线程运行；
    # daemon=True 确保主程序（GUI）退出时，该线程会自动结束，不会阻止进程退出
    threading.Thread(target=server.serve_forever, daemon=True).start()

    # ==创建桌面窗口==
    # server.server_port 获取实际绑定的端口（可能是 5001 或随机分配的端口）
    # webview 窗口加载本地 HTTP 地址，相当于内置了一个浏览器
    webview.create_window(
        "我的待办清单",
        url=f"http://{HOST}:{server.server_port}",
        width=960,
        height=760,
        min_size=(640, 520),
    )
    
    # ==启动 GUI 事件循环==
    # 此方法会阻塞主线程，直到用户关闭桌面窗口
    webview.start()

    # ==清理资源==
    # 窗口关闭后，通知后台的 WSGI 服务器停止监听并退出 serve_forever 循环
    server.shutdown()
    return 0


if __name__ == "__main__":
    main()