import sqlite3
from flask import Flask, render_template, request, redirect

app = Flask(__name__)

# 获取数据库连接
def get_db():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row  # 让查询结果像字典一样好取值
    return conn

# 首页路由
@app.route('/')
def index():
    conn = get_db()
    # 查询所有未完成的任务
    tasks = conn.execute('SELECT * FROM tasks WHERE done = 0').fetchall()
    conn.close()
    # 把数据传给网页模板
    return render_template('index.html', tasks=tasks)

@app.route('/add', methods=['POST'])
def add():
    # 1. 获取前端表单输入的任务内容
    task_content = request.form.get('task')
    
    if task_content:
        # 2. 连接数据库并插入数据
        conn = get_db()
        conn.execute('INSERT INTO tasks (task) VALUES (?)', (task_content,))
        conn.commit()
        conn.close()
        
    # 3. 添加完成后，重新跳回首页
    return redirect('/')

# 标记任务完成
@app.route('/complete/<int:task_id>')
def complete(task_id):
    conn = get_db()
    # 将对应 ID 的任务标记为已完成 (done=1)
    conn.execute('UPDATE tasks SET done = 1 WHERE id = ?', (task_id,))
    conn.commit()
    conn.close()
    return redirect('/')

# 删除任务
@app.route('/delete/<int:task_id>')
def delete(task_id):
    conn = get_db()
    # 从数据库中彻底删除对应 ID 的任务
    conn.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
    conn.commit()
    conn.close()
    return redirect('/')

if __name__ == '__main__':
    app.run(debug=True, port=5001)