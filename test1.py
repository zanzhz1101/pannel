#coding=UTF-8
import socket
import threading
import time
import sqlite3
from queue import Queue
import datetime
import tkinter as tk
from tkinter import messagebox
import re

# 处理接收到的数据
def handle_data(data, db_queue):
    try:
        cleaned_data = ''.join(filter(lambda x: x.isdigit() or x.isspace(), data))
        groups = cleaned_data.split()

        if len(groups) == 8 and groups[1] != '0' and groups[7] in ('0', '1'):
            timestamp = datetime.datetime.now()  # 使用当前时间作为时间戳
            device_id, capacity, temperature, cycles, battery, health, current, aging = map(int, groups)
            current -= 5000

            # 将数据存入数据库队列
            db_queue.put((timestamp, device_id, capacity, temperature, cycles, battery, health, current, aging))
    except Exception as e:
        print(f"Error handling data: {str(e)}")
    

# 数据库操作线程
def db_worker(db_queue):
    conn = sqlite3.connect('data.db', check_same_thread=False)
    cursor = conn.cursor()

    # 修改表结构以添加device_id列
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS status (
            device_id INTEGER PRIMARY KEY,
            timestamp DATETIME,
            capacity INTEGER,
            temperature INTEGER,
            cycles INTEGER,
            battery INTEGER,
            health INTEGER,
            current INTEGER,
            aging INTEGER
        )
    ''')
    
    # 创建data表用于存储历史信息
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS data (
            id INTEGER PRIMARY KEY,
            timestamp DATETIME,
            device_id INTEGER,
            capacity INTEGER,
            temperature INTEGER,
            cycles INTEGER,
            battery INTEGER,
            health INTEGER,
            current INTEGER,
            aging INTEGER
        )
    ''')
    
    conn.commit()

    while True:
        try:
            datetime, device_id, capacity, temperature, cycles, battery, health, current, aging = db_queue.get()

            # 插入数据到status表
            cursor.execute('''
                INSERT OR REPLACE INTO status (device_id, timestamp, capacity, temperature, cycles, battery, health, current, aging)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (device_id, datetime, capacity, temperature, cycles, battery, health, current, aging))
            
            # 插入数据到data表
            cursor.execute('''
                INSERT INTO data (timestamp, device_id, capacity, temperature, cycles, battery, health, current, aging)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (datetime, device_id, capacity, temperature, cycles, battery, health, current, aging))
            
            conn.commit()
            db_queue.task_done()
        except Exception as e:
            print(f"Error inserting data into the database: {str(e)}")

# 监听端口线程
def listen_port(port, db_queue):
    host = '0.0.0.0'

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((host, port))
    server.listen(5)
    print(f"Listening on port {port}")

    while True:
        try:
            client_socket, addr = server.accept()
            print(f"Accepted connection from {addr[0]}:{addr[1]}")

            # 不断循环接收数据，直到连接关闭
            while True:
                data = client_socket.recv(1024)
                if not data:
                    break

                data = data.decode('iso-8859-1', errors='ignore')
                # 处理接收到的数据
                handle_data(data, db_queue)

            print(f"Connection from {addr[0]}:{addr[1]} closed")
            print(data)
        except Exception as e:
            print(f"Error accepting connection or handling data: {str(e)}")

# 主程序
def main():
    port_range = range(1, 65)
    db_queue = Queue()

    # 启动数据库操作线程
    db_thread = threading.Thread(target=db_worker, args=(db_queue,))
    db_thread.start()

    # 启动监听端口线程
    for port in port_range:
        port_thread = threading.Thread(target=listen_port, args=(port, db_queue))
        port_thread.start()

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("程序界面")

        # 创建左侧的16个按钮（1-16组）
        self.left_button_frame = tk.Frame(root)
        self.left_button_frame.pack(side=tk.LEFT, padx=10, pady=10)

        self.left_buttons = []
        # 添加一个变量self.group，记录当前选择的组号
        self.group = 1

        for i in range(1, 17):
            # 计算按钮所在的行和列
            row = (i - 1) % 8
            column = (i - 1) // 8

            button = tk.Button(self.left_button_frame, text="组{}".format(i), width=8, height=2,
                               command=lambda i=i: self.on_group_button_click(i))
            self.left_buttons.append(button)
            button.grid(row=row, column=column, padx=5, pady=5)

        # 创建中间的96个格子，并初始化颜色为白色
        self.grid_frame = tk.Frame(root)
        self.grid_frame.pack(side=tk.LEFT, padx=10, pady=10)

        self.cells = []
        for i in range(8):
            for j in range(12):
                cell = tk.Label(self.grid_frame, width=10, height=3, relief=tk.RIDGE, borderwidth=1, text="")
                self.cells.append(cell)
                cell.grid(row=i, column=j, padx=5, pady=5)

        # 数据库连接和定时刷新
        self.db_connection = sqlite3.connect("data.db")
        self.refresh_data()


    def on_group_button_click(self, group):
        cursor = self.db_connection.cursor()
        print(group)
        cursor.execute("SELECT device_id, timestamp, capacity, temperature, cycles, battery, health, current, aging FROM status WHERE device_id BETWEEN ? AND ?", ((group - 1) * 100, group * 100 - 1))
        data = cursor.fetchall()
        cursor.close()

        # 更新self.group为传入的参数group
        self.group = group

        # 在循环之前，使用一个嵌套循环来对所有的格子调用configure方法
        for i in range(8):
            for j in range(12):
                self.cells[i * 12 + j].configure(bg="white", text="", command=None)

        for row in data:
            device_id, timestamp, capacity, temperature, cycles, battery, health, current, aging = row
            device_number = int(device_id) % 100
            cell_index = device_number - 1  # 格子索引从0开始
            datetime_pattern = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d{6})?"
            
            # 判断设备号是否属于当前选择的组
            if (device_id - 1) // 100 + 1 == self.group:
                # 计算时间差
                # time_diff = int(time.time()) - int(datetime.datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S").timestamp())
                if re.match(datetime_pattern, timestamp):
                    try:
                        time_diff = int(time.time()) - int(datetime.datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S.%f").timestamp())
                    except ValueError:
                        # 处理转换错误，设置 time_diff 为 300
                        time_diff = 300
                else:
                    # 不符合格式，设置 time_diff 为 300
                    time_diff = 300
                # 判断时间差是否大于15，如果是则显示白色，否则根据其他条件判断设备状态
                self.cells[cell_index].configure(
                    text=f"设备{device_number}\n温度:{temperature}\n电流:{current}")

                if time_diff > 15:
                    self.cells[cell_index].configure(bg="white")
                    self.cells[cell_index].configure(text="")
                    self.cells[cell_index].unbind("<Button-1>")
                elif aging == 1:
                    self.cells[cell_index].configure(bg="green")
                elif temperature > 65 or health < 95 or current > 4000 or current < -4000:
                    self.cells[cell_index].configure(bg="red")
                elif current > 0:
                    self.cells[cell_index].configure(bg="orange")
                elif current < 0:
                    self.cells[cell_index].configure(bg="blue")
                else:
                    self.cells[cell_index].configure(bg="white")



                # 为每个格子绑定点击事件
                self.cells[cell_index].bind("<Button-1>", lambda event, row=row: self.show_device_details(row))
            else:
                # 如果不属于当前选择的组，则不显示设备状态
                self.cells[cell_index].configure(bg="white")
                self.cells[cell_index].configure(text="")
                self.cells[cell_index].unbind("<Button-1>")


    def show_device_details(self, device_details):
        # 创建弹出窗口显示设备详细信息
        details_window = tk.Toplevel(self.root)
        details_window.title("设备详细信息")
        
        device_id, timestamp, capacity, temperature, cycles, battery, health, current, aging = device_details
        device_number = int(device_id) % 100

        details_label = tk.Label(details_window, text=f"设备号: {device_number}\n容量: {capacity}\n温度: {temperature}\n循环次数: {cycles}\n电量: {battery}\n健康度: {health}\n电流: {current}\n老化状态: {aging}")
        details_label.pack(padx=10, pady=10)

    def refresh_data(self):
        # 只调用一次on_group_button_click方法，传入self.group作为参数
        self.on_group_button_click(self.group)

        # 每隔5秒刷新一次数据
        self.root.after(5000, self.refresh_data)



if __name__ == '__main__':
    main()
    root = tk.Tk()
    app = App(root)
    root.mainloop()
