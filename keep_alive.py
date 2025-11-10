from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    # 這是 UptimeRobot 會看到的頁面
    return "I'm alive!"


def run():
    # 讓網站在 0.0.0.0 (所有 IP) 的 8080 埠口運作
    app.run(host='0.0.0.0', port=8080)


def keep_alive():
    # 在一個新的執行緒 (Thread) 中啟動網站
    # 這樣它才不會卡住 Discord 機器人的主程式
    t = Thread(target=run)
    t.start()