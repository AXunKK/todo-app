import webview
import threading
import time
from app import app

def start_flask():
    # 注意：这里要把 debug 关掉，并且关掉 reloader，否则打包后会无限重启
    app.run(host='127.0.0.1', port=5001, debug=False, use_reloader=False)

if __name__ == '__main__':
    # 1. 把 Flask 跑在后台线程里
    t = threading.Thread(target=start_flask)
    t.daemon = True
    t.start()

    # 2. 等 Flask 准备就绪（稍微等1秒）
    time.sleep(1)

    # 3. 创建一个原生的桌面窗口
    window = webview.create_window(
        title='我的待办清单', 
        url='http://127.0.0.1:5001',
        width=900, 
        height=700,
        resizable=True
    )
    
    # 4. 启动窗口
    webview.start()