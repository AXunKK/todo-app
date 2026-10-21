import os
import sys
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, jsonify

# 1. 动态判断环境（解决打包后找不到模板和静态文件的问题）
if getattr(sys, 'frozen', False):
    template_folder = os.path.join(sys._MEIPASS, 'templates')
    static_folder = os.path.join(sys._MEIPASS, 'static')
    app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)
else:
    app = Flask(__name__)

# 2. 获取数据库路径（解决打包后找不到数据库的问题）
def get_db_path():
    if getattr(sys, 'frozen', False):
        app_data_dir = os.path.join(os.path.expanduser('~'), 'TodoAppData')
        os.makedirs(app_data_dir, exist_ok=True)
        return os.path.join(app_data_dir, 'database.db')
    else:
        return 'database.db'

# 3. 获取数据库连接
def get_db():
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn

# 4. 初始化数据库并自动建表
def init_db():
    conn = get_db()
    conn.execute('CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY, task TEXT, created_at TEXT, due_date TEXT, done INTEGER DEFAULT 0)')
    conn.commit()
    conn.close()

# 执行一次初始化
init_db()

# ================= 以下是你的业务逻辑路由 =================

@app.route('/')
def index():
    # 1. 接收所有筛选参数
    filter_date = request.args.get('filter_date', '')
    status = request.args.get('status', 'todo')
    search_query = request.args.get('search', '').strip() # 新增：接收搜索词，去掉两边空格
    
    conn = get_db()
    query = 'SELECT * FROM tasks WHERE 1=1'
    params = []
    
    # 处理状态筛选
    if status == 'todo':
        query += ' AND done = 0'
    elif status == 'done':
        query += ' AND done = 1'
    
    # 处理日期筛选
    if filter_date:
        query += ' AND due_date = ?'
        params.append(filter_date)
        
    # 处理搜索筛选
    if search_query:
        query += ' AND task LIKE ?'
        params.append(f'%{search_query}%') # 模糊查询，只要包含这个词就能搜出来
        
    query += ' ORDER BY id DESC' 
    
    tasks = conn.execute(query, params).fetchall()
    conn.close()
    
    # 把 search_query 也传回前端，保持搜索框的状态
    return render_template('index.html', tasks=tasks, filter_date=filter_date, status=status, search_query=search_query)

@app.route('/add', methods=['POST'])
def add():
    task_content = request.form.get('task')
    due_date = request.form.get('due_date')
    priority = request.form.get('priority', '中') # 新增：接收优先级，默认为中
    
    if task_content:
        created_at = datetime.now().strftime("%Y-%m-%d")
        
        if not due_date:
            due_date = created_at
            
        conn = get_db()
        cursor = conn.execute('INSERT INTO tasks (task, created_at, due_date, priority) VALUES (?, ?, ?, ?)', 
                     (task_content, created_at, due_date, priority)) # 插入优先级
        new_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return jsonify({
            "status": "success",
            "id": new_id,
            "task": task_content,
            "created_at": created_at,
            "due_date": due_date,
            "priority": priority # 返回给前端
        })
        
    return jsonify({"status": "error", "message": "任务内容不能为空"})

@app.route('/complete/<int:task_id>')
def complete(task_id):
    conn = get_db()
    conn.execute('UPDATE tasks SET done = 1 WHERE id = ?', (task_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})

@app.route('/undo/<int:task_id>')
def undo(task_id):
    conn = get_db()
    conn.execute('UPDATE tasks SET done = 0 WHERE id = ?', (task_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})

@app.route('/delete/<int:task_id>')
def delete(task_id):
    conn = get_db()
    conn.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})

# 一键清空已完成任务
@app.route('/clear_completed', methods=['POST'])
def clear_completed():
    conn = get_db()
    # 直接删除所有 done = 1 的数据
    conn.execute('DELETE FROM tasks WHERE done = 1')
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})

if __name__ == '__main__':
    app.run(debug=True, port=5001)