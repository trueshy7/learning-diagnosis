"""从联合工程启动C、D、B。先安装根目录requirements.txt。"""
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
SERVICES=[('C','member-c-rag','rag_service.main:app',8001),('D','member-d-agents','diagnosis_service.main:app',8002),('B','member-b-backend','backend_service.main:app',8000)]

def wait_health(port,process):
    for _ in range(100):
        if process.poll() is not None:raise RuntimeError(f'{port}服务启动失败，见上方日志')
        try:
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(f'http://127.0.0.1:{port}/health',timeout=.5) as response:
                if response.status==200:return
        except (OSError,TimeoutError):pass
        time.sleep(.1)
    raise RuntimeError(f'{port}服务未能在期限内就绪')

def main():
    for _,_,_,port in SERVICES:
        with socket.socket() as sock:
            try:sock.bind(('127.0.0.1',port))
            except OSError:raise SystemExit(f'端口{port}已被占用，请检查已有服务。')
    env={**os.environ,'RAG_MODE':'http','RAG_BASE_URL':'http://127.0.0.1:8001','AGENTS_MODE':'http','AGENTS_URL':'http://127.0.0.1:8002','RAG_URL':'http://127.0.0.1:8001'}
    children=[]
    try:
        for name,folder,module,port in SERVICES:
            process=subprocess.Popen([sys.executable,'-m','uvicorn',module,'--host','127.0.0.1','--port',str(port)],cwd=ROOT/folder,env=env)
            children.append(process);wait_health(port,process);print(f'{name}服务就绪：http://127.0.0.1:{port}',flush=True)
        print('可在另一个终端启动A。按Ctrl+C停止这三个服务。',flush=True)
        while all(p.poll() is None for p in children):time.sleep(.5)
        if any(p.poll() is not None for p in children):raise RuntimeError('有服务提前退出，请查看日志')
    except KeyboardInterrupt:pass
    finally:
        for process in children:
            if process.poll() is None:process.terminate()
        for process in children:
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait()

if __name__=='__main__':main()
