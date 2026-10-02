from flask import Flask, render_template, request, redirect, jsonify
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect

app = Flask(__name__)

def get_db():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    # 1. 获取前端传过来的参数（如果没有，提供默认值）
    filter_date = request.args.get('filter_date', '') # 日期筛选
    status = request.args.get('status', 'todo')       # 状态筛选，默认看“未完成(todo)”
    
    conn = get_db()
    
    # 2. 动态拼接 SQL 查询（这是后端开发非常核心的技术）
    # 这样写可以兼容各种条件的组合
    query = 'SELECT * FROM tasks WHERE 1=1'
    params = []
    
    # 处理状态筛选
    if status == 'todo':
        query += ' AND done = 0'
    elif status == 'done':
        query += ' AND done = 1'
    # status == 'all' 时，什么都不加，代表查询全部
    
    # 处理日期筛选
    if filter_date:
        query += ' AND due_date = ?'
        params.append(filter_date)
        
    query += ' ORDER BY id DESC' # 最新的任务排在最上面
    
    # 执行查询
    tasks = conn.execute(query, params).fetchall()
    conn.close()
    
    # 3. 把参数传回给前端，方便前端保持页面状态
    return render_template('index.html', tasks=tasks, filter_date=filter_date, status=status)

@app.route('/add', methods=['POST'])
def add():
    task_content = request.form.get('task')
    due_date = request.form.get('due_date')
    
    if task_content:
        created_at = datetime.now().strftime("%Y-%m-%d")
        
        if not due_date:
            due_date = created_at
            
        conn = get_db()
        cursor = conn.execute('INSERT INTO tasks (task, created_at, due_date) VALUES (?, ?, ?)', 
                     (task_content, created_at, due_date))
        new_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return jsonify({
            "status": "success",
            "id": new_id,
            "task": task_content,
            "created_at": created_at,
            "due_date": due_date 
        })
        
    return jsonify({"status": "error", "message": "任务内容不能为空"})

# 标记任务完成
@app.route('/complete/<int:task_id>')
def complete(task_id):
    conn = get_db()
    conn.execute('UPDATE tasks SET done = 1 WHERE id = ?', (task_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})

# 撤销任务完成（把状态改回未完成）
@app.route('/undo/<int:task_id>')
def undo(task_id):
    conn = get_db()
    # 将对应 ID 的任务标记为未完成 (done=0)
    conn.execute('UPDATE tasks SET done = 0 WHERE id = ?', (task_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})

# 删除任务
@app.route('/delete/<int:task_id>')
def delete(task_id):
    conn = get_db()
    conn.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})

if __name__ == '__main__':
    app.run(debug=True, port=5001)