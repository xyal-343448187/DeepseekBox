import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import json
import requests
import sqlite3
from datetime import datetime
import queue

# 数据库操作队列
db_queue = queue.Queue()


def db_worker():
    local_storage = threading.local()

    def get_conn():
        if not hasattr(local_storage, "conn"):
            local_storage.conn = sqlite3.connect(
                'conversations.db',
                check_same_thread=False
            )
            local_storage.conn.execute("PRAGMA journal_mode=WAL")
        return local_storage.conn

    while True:
        task = db_queue.get()
        if task is None:
            if hasattr(local_storage, "conn"):
                local_storage.conn.close()
            break
        try:
            func, args, kwargs = task
            conn = get_conn()
            cursor = conn.cursor()
            result = func(cursor, *args, **kwargs)
            conn.commit()
            if kwargs.get('callback'):
                kwargs['callback'](result)
        except Exception as e:
            print(f"Database error: {str(e)}")
        finally:
            db_queue.task_done()


threading.Thread(target=db_worker, daemon=True).start()


class DatabaseHandler:
    @staticmethod
    def create_tables(cursor):
        try:
            cursor.execute('''CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                created_at DATETIME
            )''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                role TEXT,
                content TEXT,
                created_at DATETIME,
                FOREIGN KEY(session_id) REFERENCES sessions(id)
            )''')
        except sqlite3.Error as e:
            print(f"Create table error: {str(e)}")

    @staticmethod
    def create_session(cursor, title, callback=None):
        try:
            cursor.execute('INSERT INTO sessions (title, created_at) VALUES (?, ?)',
                           (title, datetime.now()))
            if callback:
                tk.Tk().after(0, lambda: callback(cursor.lastrowid))
            return cursor.lastrowid
        except sqlite3.Error as e:
            print(f"Create session error: {str(e)}")

    @staticmethod
    def add_message(cursor, session_id, role, content):
        try:
            cursor.execute('''INSERT INTO messages 
                           (session_id, role, content, created_at)
                           VALUES (?, ?, ?, ?)''',
                           (session_id, role, content, datetime.now()))
        except sqlite3.Error as e:
            print(f"Add message error: {str(e)}")

    @staticmethod
    def get_sessions(cursor, callback=None):
        try:
            cursor.execute('SELECT id, title, created_at FROM sessions ORDER BY created_at DESC')
            result = cursor.fetchall()
            if callback:
                tk.Tk().after(0, lambda: callback(result))
            return result
        except sqlite3.Error as e:
            print(f"Get sessions error: {str(e)}")

    @staticmethod
    def get_messages(cursor, session_id, callback=None):
        try:
            cursor.execute('''SELECT role, content FROM messages 
                           WHERE session_id = ? ORDER BY created_at''', (session_id,))
            result = cursor.fetchall()
            if callback:
                tk.Tk().after(0, lambda: callback(result))
            return result
        except sqlite3.Error as e:
            print(f"Get messages error: {str(e)}")


class DeepSeekChatApp:
    def __init__(self, root):
        self.root = root
        self.root.title("DeepSeek-R1 深度思考助手")
        self.root.geometry("1200x800")

        # 初始化数据库
        db_queue.put((DatabaseHandler.create_tables, [], {}))
        self.current_session = None
        self.message_history = []

        # 初始化组件
        self.create_widgets()
        self.running = False
        self.load_sessions()

    def create_widgets(self):
        """创建界面组件"""
        main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True)

        # 左侧会话列表
        left_frame = ttk.Frame(main_paned, width=250)
        main_paned.add(left_frame, weight=0)

        self.session_tree = ttk.Treeview(left_frame, columns=('time'), show='tree headings')
        self.session_tree.heading('#0', text='历史对话', anchor=tk.W)
        self.session_tree.column('#0', width=200)
        self.session_tree.heading('time', text='创建时间')
        self.session_tree.column('time', width=100)
        self.session_tree.bind('<<TreeviewSelect>>', self.on_session_select)

        scrollbar = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=self.session_tree.yview)
        self.session_tree.configure(yscrollcommand=scrollbar.set)

        self.session_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 右侧聊天区域
        right_frame = ttk.Frame(main_paned)
        main_paned.add(right_frame, weight=1)

        # 消息显示区域
        self.chat_display = scrolledtext.ScrolledText(
            right_frame,
            wrap=tk.WORD,
            state='disabled',
            font=('微软雅黑', 11),
            bg='#FFFFFF',
            padx=10,
            pady=10
        )
        self.chat_display.pack(fill=tk.BOTH, expand=True)

        # 输入区域
        input_frame = ttk.Frame(right_frame)
        input_frame.pack(fill=tk.X, pady=10)

        self.input_text = tk.Text(input_frame, height=4, wrap=tk.WORD, font=('微软雅黑', 11))
        self.input_text.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        self.send_btn = ttk.Button(input_frame, text="发送", command=self.toggle_chat)
        self.send_btn.pack(side=tk.RIGHT, padx=5)

        # 配置面板
        config_frame = ttk.LabelFrame(right_frame, text="API配置", padding=10)
        config_frame.pack(fill=tk.X, pady=5)

        ttk.Label(config_frame, text="API密钥：").grid(row=0, column=0, sticky=tk.W)
        self.api_key_entry = ttk.Entry(config_frame, width=50)
        self.api_key_entry.grid(row=0, column=1, padx=5, sticky=tk.EW)

        ttk.Label(config_frame, text="最大Token数：").grid(row=1, column=0, sticky=tk.W)
        self.max_tokens_spin = ttk.Spinbox(config_frame, from_=100, to=4096, width=10)
        self.max_tokens_spin.set(4096)
        self.max_tokens_spin.grid(row=1, column=1, padx=5, sticky=tk.W)

        ttk.Label(config_frame, text="随机性：").grid(row=2, column=0, sticky=tk.W)
        self.temp_scale = ttk.Scale(config_frame, from_=0, to=1, length=200)
        self.temp_scale.set(0.6)
        self.temp_scale.grid(row=2, column=1, padx=5, sticky=tk.W)

        # 设置列权重
        config_frame.columnconfigure(1, weight=1)

    def load_sessions(self):
        """加载历史会话"""

        def update_treeview(sessions):
            for item in self.session_tree.get_children():
                self.session_tree.delete(item)
            for session in sessions:
                self.session_tree.insert('', 'end',
                                         iid=session[0],
                                         text=session[1],
                                         values=(session[2],))

        db_queue.put((
            DatabaseHandler.get_sessions,
            [],
            {'callback': lambda r: self.root.after(0, update_treeview, r)}
        ))

    def on_session_select(self, event):
        """加载选中会话的详细内容"""
        selected = self.session_tree.selection()
        if not selected:
            return

        session_id = int(selected[0])

        def update_chat(messages):
            self.current_session = session_id
            self.chat_display.config(state='normal')
            self.chat_display.delete(1.0, tk.END)
            for role, content in messages:
                self._append_message(role, content)
            self.chat_display.config(state='disabled')

        db_queue.put((
            DatabaseHandler.get_messages,
            [session_id],
            {'callback': lambda r: self.root.after(0, update_chat, r)}
        ))

    def _append_message(self, role, content):
        """追加消息到显示区域"""
        tag = 'assistant' if role == 'assistant' else 'user'
        self.chat_display.tag_config(tag,
                                     foreground='#2A5CAA' if role == 'assistant' else '#333333',
                                     font=('微软雅黑', 11, 'bold'))

        self.chat_display.config(state='normal')
        self.chat_display.insert(tk.END, f"{'助手' if role == 'assistant' else '你'}：\n", tag)
        self.chat_display.insert(tk.END, content + "\n\n", 'content')
        self.chat_display.see(tk.END)
        self.chat_display.config(state='disabled')

    def toggle_chat(self):
        """启动/停止对话"""
        if self.running:
            self.running = False
            self.send_btn.config(text="发送")
        else:
            user_input = self.input_text.get("1.0", tk.END).strip()
            if not user_input:
                messagebox.showwarning("提示", "请输入对话内容")
                return

            if not self.current_session:
                self._create_new_session(user_input)
            else:
                self._process_user_input(user_input)

    def _create_new_session(self, user_input):
        """创建新会话"""

        def callback(session_id):
            self.current_session = session_id
            self.load_sessions()
            self.session_tree.selection_set(str(session_id))
            self._process_user_input(user_input)

        db_queue.put((
            DatabaseHandler.create_session,
            [user_input[:20]],
            {'callback': callback}
        ))

    def _process_user_input(self, user_input):
        """处理用户输入"""
        self.add_message_to_db('user', user_input)
        self._append_message('user', user_input)
        self.input_text.delete(1.0, tk.END)

        self.running = True
        self.send_btn.config(text="停止")
        threading.Thread(target=self._call_deepseek_api, daemon=True).start()

    def add_message_to_db(self, role, content):
        if self.current_session:
            db_queue.put((
                DatabaseHandler.add_message,
                [self.current_session, role, content],
                {}
            ))

    def _call_deepseek_api(self):
        """调用DeepSeek API"""

        def get_messages_callback(messages):
            try:
                messages = [
                               {"role": "system", "content": "你是一个善于深度思考的助手，请详细展示推理过程"}
                           ] + [
                               {"role": msg[0], "content": msg[1]}
                               for msg in messages
                           ]

                response = requests.post(
                    url="https://maas-cn-southwest-2.modelarts-maas.com/v1/infers/8a062fd4-7367-4ab4-a936-5eeb8fb821c4/v1/chat/completions",
                    headers={
                        'Content-Type': 'application/json',
                        'Authorization': f'Bearer {self.api_key_entry.get()}'
                    },
                    json={
                        "model": "DeepSeek-R1",
                        "max_tokens": int(self.max_tokens_spin.get()),
                        "messages": messages,
                        "stream": True,
                        "temperature": float(self.temp_scale.get())
                    },
                    stream=True
                )

                full_response = []
                for line in response.iter_lines():
                    if not self.running:
                        break

                    if line:
                        decoded = line.decode().lstrip('data: ').strip()
                        if decoded == "[DONE]":
                            break

                        try:
                            chunk = json.loads(decoded)
                            delta = chunk['choices'][0]['delta']
                            content = delta.get("content", "")
                            reasoning = delta.get("reasoning_content", "")

                            if content:
                                full_response.append(content)
                                self._stream_append(content)

                            if reasoning:
                                self._stream_append(f"\n[推理过程] {reasoning}\n", is_reasoning=True)

                        except Exception as e:
                            continue

                if full_response:
                    self.add_message_to_db('assistant', ''.join(full_response))

            except Exception as e:
                self._stream_append(f"\n[错误] {str(e)}", is_error=True)
            finally:
                self.running = False
                self.send_btn.config(text="发送")
                self.root.event_generate("<<RefreshUI>>")

        # 通过队列获取消息历史
        db_queue.put((
            DatabaseHandler.get_messages,
            [self.current_session],
            {'callback': lambda r: self.root.after(0, get_messages_callback, r)}
        ))

    def _stream_append(self, content, is_reasoning=False, is_error=False):
        """流式输出内容"""
        self.chat_display.config(state='normal')
        tag = 'error' if is_error else 'reasoning' if is_reasoning else 'content'
        self.chat_display.tag_config(tag,
                                     foreground='#FF0000' if is_error else '#666666' if is_reasoning else '#000000')

        self.chat_display.insert(tk.END, content, tag)
        self.chat_display.see(tk.END)
        self.chat_display.config(state='disabled')
        self.root.update_idletasks()


def on_closing():
    db_queue.put(None)
    root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = DeepSeekChatApp(root)
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()