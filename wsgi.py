#!/usr/bin/env python3
"""Gunicorn WSGI 入口 - 带 Ngrok 隧道自动启动"""
from app import app
import os, threading, time, webbrowser

def start_ngrok():
    """在 Gunicorn worker 内部启动 ngrok 隧道"""
    time.sleep(2)  # 等待服务器就绪
    try:
        from pyngrok import ngrok, conf
        ngrok_bin = "/home/sandbox/.openclaw/workspace/repo/bin/ngrok"
        conf.get_default().ngrok_path = ngrok_bin
        
        # 设置 authtoken
        ngrok.set_auth_token("3DdQQpk1aV3R34ozc5Lt6O1Re5m_6xqf6nYGa3JkWTRBwiQZE")
        
        # 启动隧道
        tunnel = ngrok.connect(5000, "http")
        url = tunnel.public_url
        
        # 写 URL 到文件
        with open("/tmp/ngrok_url.txt", "w") as f:
            f.write(url)
        
        print(f"\n{'='*60}")
        print(f"  ✅ Ngrok 隧道已启动")
        print(f"  🌐 访问地址: {url}")
        print(f"  👤 账号: admin / admin123")
        print(f"{'='*60}\n")
        
        # 保持线程运行
        while True:
            time.sleep(30)
    except Exception as e:
        print(f"\n⚠️ Ngrok 启动失败: {e}")
        # 重试一次
        time.sleep(5)
        try:
            from pyngrok import ngrok, conf
            tunnel = ngrok.connect(5000, "http")
            url = tunnel.public_url
            with open("/tmp/ngrok_url.txt", "w") as f:
                f.write(url)
            print(f"\n✅ Ngrok 重试成功: {url}\n")
        except Exception as e2:
            print(f"\n❌ Ngrok 重试也失败: {e2}\n")

# 后台线程启动 ngrok
t = threading.Thread(target=start_ngrok, daemon=True)
t.start()

if __name__ == "__main__":
    app.run()
