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
    due_date = request.form.get('due_date') # 获取前端选择的截止日期
    
    if task_content:
        # 自动获取当前日期（格式：2026-09-21）
        created_at = datetime.now().strftime("%Y-%m-%d") 
        
        conn = get_db()
        # 插入三个新字段
        conn.execute('INSERT INTO tasks (task, created_at, due_date) VALUES (?, ?, ?)', 
                     (task_content, created_at, due_date))
        conn.commit()
        conn.close()
        
    return redirect('/')

@app.route('/complete/<int:task_id>')
def complete(task_id):
    conn = get_db()
    conn.execute('UPDATE tasks SET done = 1 WHERE id = ?', (task_id,))
    conn.commit()
    conn.close()
    return redirect('/')

@app.route('/delete/<int:task_id>')
def delete(task_id):
    conn = get_db()
    conn.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
    conn.commit()
    conn.close()
    return redirect('/')

if __name__ == '__main__':
    app.run(debug=True, port=5001)