import os
import secrets
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, abort, jsonify, redirect, render_template, request, url_for

# ==全局常量配置==
MAX_TASK_LENGTH = 500
PRIORITIES = ("高", "中", "低")
STATUS_FILTERS = ("all", "todo", "done")
# 定义所有会修改数据的 HTTP 方法，用于后续统一进行安全拦截
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# ==应用初始化与打包兼容==
if getattr(sys, "frozen", False):
    # 兼容 PyInstaller 等打包工具：打包后资源被解压到临时目录 sys._MEIPASS
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    app = Flask(
        __name__,
        template_folder=str(base / "templates"),
        static_folder=str(base / "static"),
    )
else:
    # 源码运行环境，Flask 默认在当前目录下寻找 templates 和 static
    app = Flask(__name__)

app.config.update(
    MAX_CONTENT_LENGTH=32 * 1024, # 限制请求体最大为 32KB，防止超大请求耗尽内存
    CSRF_TOKEN=secrets.token_urlsafe(32), # 启动时生成强随机 CSRF 防伪令牌
)

# ==数据库路径与连接管理==
def db_path():
    # 路径优先级：环境变量覆盖 > 打包后的用户目录 > 源码运行时的当前目录
    override = os.environ.get("TODO_APP_DB")
    if override:
        path = Path(override).expanduser().resolve()
    elif getattr(sys, "frozen", False):
        path = Path.home() / "TodoAppData" / "database.db"
    else:
        path = Path(__file__).resolve().parent / "database.db"
    
    # 确保父目录存在，若不存在则自动创建
    path.parent.mkdir(parents=True, exist_ok=True)
    return path

def connect_db(path=None):
    # 连接 SQLite 数据库，设置 5 秒超时
    conn = sqlite3.connect(str(path or db_path()), timeout=5)
    # 使得查询结果可以通过键名访问（如 row["name"]），而非仅依赖索引
    conn.row_factory = sqlite3.Row
    # 当数据库被锁时，最多等待 5000 毫秒，避免直接抛出 database is locked 错误
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn

@contextmanager
def db():
    # 上下文管理器，确保数据库事务的原子性（提交/回滚）与连接释放
    conn = connect_db()
    try:
        yield conn
        conn.commit() # 业务逻辑正常执行完毕，提交事务
    except Exception:
        conn.rollback() # 发生异常，回滚未提交的修改
        raise
    finally:
        conn.close() # 无论成功与否，强制关闭连接

# ==数据库初始化与迁移==
def init_db(path=None):
    conn = connect_db(path)
    try:
        # 创建任务表，包含状态与优先级的 CHECK 约束，防止脏数据写入
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY,
                task TEXT NOT NULL,
                done INTEGER NOT NULL DEFAULT 0 CHECK (done IN (0, 1)),
                created_at TEXT NOT NULL,
                due_date TEXT,
                priority TEXT NOT NULL DEFAULT '中'
                    CHECK (priority IN ('高', '中', '低'))
            )
            """
        )

        # 读取当前表结构的所有列名，用于旧版本数据库迁移
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(tasks)")}
        if "id" not in cols:
            raise RuntimeError("tasks 表缺少 id 列，无法自动迁移")
        
        # 动态补充旧版本缺失的列（ALTER TABLE）
        if "task" not in cols:
            conn.execute("ALTER TABLE tasks ADD COLUMN task TEXT NOT NULL DEFAULT ''")
        if "done" not in cols:
            conn.execute("ALTER TABLE tasks ADD COLUMN done INTEGER NOT NULL DEFAULT 0")
        if "created_at" not in cols:
            conn.execute("ALTER TABLE tasks ADD COLUMN created_at TEXT")
        if "due_date" not in cols:
            conn.execute("ALTER TABLE tasks ADD COLUMN due_date TEXT")
        if "priority" not in cols:
            conn.execute("ALTER TABLE tasks ADD COLUMN priority TEXT NOT NULL DEFAULT '中'")

        # 清洗历史脏数据，使其符合业务约束
        conn.execute("UPDATE tasks SET task = trim(task) WHERE task IS NOT NULL")
        conn.execute("UPDATE tasks SET done = 0 WHERE done NOT IN (0, 1)")
        conn.execute(
            "UPDATE tasks SET priority = '中' WHERE priority NOT IN ('高', '中', '低')"
        )
        
        # 创建索引，提升按完成状态和截止日期查询的性能
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_done ON tasks(done)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date)")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

# ==通用工具函数==
def wants_json():
    # 判断客户端是否期望 JSON 响应（用于兼容 AJAX 请求和传统的表单提交）
    if request.headers.get("X-Requested-With") == "fetch":
        return True
    return request.accept_mimetypes.best == "application/json"

def safe_next_url():
    # 防止开放重定向攻击：校验 next 参数必须是安全的站内相对路径
    target = request.form.get("next", "")
    parsed = urlsplit(target)
    # 条件：不能有协议头（http://），不能有域名（//evil.com），必须以单斜杠 / 开头
    if (
        target
        and not parsed.scheme
        and not parsed.netloc
        and parsed.path.startswith("/")
        and not parsed.path.startswith("//")
    ):
        return target
    return url_for("index") # 若不合法，则安全回退到首页

def error_response(message, status_code):
    # 统一错误响应格式，根据客户端需求返回 JSON 或纯文本
    if wants_json():
        return jsonify({"status": "error", "message": message}), status_code
    return message, status_code

def valid_date(value):
    # 校验日期字符串格式必须严格为 YYYY-MM-DD
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False

def escape_like(value):
    # 转义 SQL LIKE 查询中的通配符（%、_、\），防止用户输入的搜索词改变 SQL 匹配逻辑
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

# ==安全钩子 (Request Hooks)==
@app.before_request
def check_write():
    # 仅拦截修改数据的写请求 (POST/PUT/PATCH/DELETE)
    if request.method not in WRITE_METHODS:
        return None

    # 1. 校验 Origin 头：防止跨站请求伪造 (CSRF)
    origin = request.headers.get("Origin")
    if origin and origin.rstrip("/") != request.host_url.rstrip("/"):
        abort(403)

    # 2. 校验 CSRF Token：使用常量时间比较，防止时序攻击
    token = (
        request.headers.get("X-CSRF-Token")
        or request.form.get("_csrf_token")
        or ""
    )
    if not token or not secrets.compare_digest(token, app.config["CSRF_TOKEN"]):
        abort(403)
    return None

@app.after_request
def security_headers(response):
    # 注入 Content-Security-Policy (CSP)，严格限制资源加载源，防范 XSS
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "object-src 'none'; "
        "base-uri 'none'; "
        "frame-ancestors 'none'"
    )
    # 禁止浏览器 MIME 类型嗅探
    response.headers["X-Content-Type-Options"] = "nosniff"
    # 控制 Referer 请求头的发送策略，防止敏感信息泄露
    response.headers["Referrer-Policy"] = "no-referrer"
    return response

@app.context_processor
def csrf():
    # 全局注入模板变量，允许在 HTML 中直接使用 {{ csrf_token }}
    return {"csrf_token": app.config["CSRF_TOKEN"]}

# ==视图路由 (Routes)==
@app.route("/")
def index():
    # 参数解析与合法性清洗
    filter_date = request.args.get("filter_date", "").strip()
    if filter_date and not valid_date(filter_date):
        filter_date = ""

    status = request.args.get("status", "todo")
    if status not in STATUS_FILTERS:
        status = "todo"

    search = request.args.get("search", "").strip()

    # 动态构建 SQL 语句，使用参数化查询 (?) 防止 SQL 注入
    sql = "SELECT * FROM tasks WHERE 1 = 1"
    params = []
    if status == "todo":
        sql += " AND done = 0"
    elif status == "done":
        sql += " AND done = 1"
    if filter_date:
        sql += " AND due_date = ?"
        params.append(filter_date)
    if search:
        sql += " AND task LIKE ? ESCAPE '\\'"
        params.append(f"%{escape_like(search)}%")
    
    # 排序规则：未完成排前面，同状态下新建的任务排前面
    sql += " ORDER BY done ASC, id DESC"

    with db() as conn:
        tasks = conn.execute(sql, params).fetchall()
        # 统计全局已完成任务数（不受当前列表筛选影响，供清空按钮使用）
        done_count = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE done = 1"
        ).fetchone()[0]

    # 获取当前完整 URL（去除末尾的 ?），用作表单的 next 参数
    return_to = request.full_path.rstrip("?") or "/"
    
    # 渲染 HTML 模板并传递上下文数据
    return render_template(
        "index.html",
        tasks=tasks,
        filter_date=filter_date,
        status=status,
        search_query=search,
        completed_count=done_count,
        return_to=return_to,
    )

@app.post("/add")
def add():
    # 获取表单数据并去除首尾空白
    content = (request.form.get("task") or "").strip()
    due = (request.form.get("due_date") or "").strip()
    priority = (request.form.get("priority") or "中").strip()

    # 后端严格校验（不能仅依赖前端 HTML 的 required）
    if not content:
        return error_response("任务内容不能为空", 400)
    if len(content) > MAX_TASK_LENGTH:
        return error_response(f"任务内容不能超过 {MAX_TASK_LENGTH} 个字符", 400)
    if priority not in PRIORITIES:
        return error_response("优先级不合法", 400)
    if due and not valid_date(due):
        return error_response("截止日期格式不合法", 400)

    # 记录创建日期
    created = datetime.now().strftime("%Y-%m-%d")
    with db() as conn:
        cur = conn.execute(
            """
            INSERT INTO tasks (task, created_at, due_date, priority)
            VALUES (?, ?, ?, ?)
            """,
            (content, created, due or None, priority), # 空字符串转为 None 存入数据库
        )
        new_id = cur.lastrowid # 获取自增主键

    # 如果是 AJAX 请求，返回 201 Created 及新增的数据
    if wants_json():
        return (
            jsonify(
                {
                    "status": "success",
                    "id": new_id,
                    "task": content,
                    "created_at": created,
                    "due_date": due or None,
                    "priority": priority,
                }
            ),
            201,
        )
    # 传统表单提交，重定向回来源页面
    return redirect(safe_next_url())

def set_done(task_id, done):
    # 复用逻辑：更新任务完成状态
    with db() as conn:
        cur = conn.execute(
            "UPDATE tasks SET done = ? WHERE id = ?", (done, task_id)
        )
        # rowcount 为 0 表示未找到对应 ID 的任务
        if cur.rowcount == 0:
            return error_response("任务不存在", 404)

    if wants_json():
        return jsonify({"status": "success"})
    return redirect(safe_next_url())

@app.post("/complete/<int:task_id>")
def complete(task_id):
    # 标记为已完成 (done=1)
    return set_done(task_id, 1)

@app.post("/undo/<int:task_id>")
def undo(task_id):
    # 撤销完成 (done=0)
    return set_done(task_id, 0)

@app.post("/delete/<int:task_id>")
def delete(task_id):
    # 删除单条任务
    with db() as conn:
        cur = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        if cur.rowcount == 0:
            return error_response("任务不存在", 404)

    if wants_json():
        return jsonify({"status": "success"})
    return redirect(safe_next_url())

@app.post("/clear_completed")
def clear_completed():
    # 批量删除所有已完成的任务
    with db() as conn:
        deleted = conn.execute("DELETE FROM tasks WHERE done = 1").rowcount

    if wants_json():
        return jsonify({"status": "success", "deleted": deleted})
    return redirect(safe_next_url())

# ==启动执行==
# 在模块导入或启动时，先执行数据库初始化，确保表和索引就绪
init_db()

if __name__ == "__main__":
    # 仅允许本机访问，关闭调试模式以确保安全
    app.run(host="127.0.0.1", port=5001, debug=False)