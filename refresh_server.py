#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
李家村看板 —— 本地刷新服务
让前端「刷新键」等价于：点一下就跑完"拉取最新所有数据"的全流程。

流程（每次刷新）：
  ① fetch_yonyou.sh         -> 自动登录用友云，抓取「门店毛利明细」到 yonyou_raw.tsv
  ② fetch_sales_analysis.sh -> 自动抓取「销售分析」报表并导入 xlsx
  ③ calc_data.py            -> 复算业绩/品类/洞察 -> data.json（不含渠道挂账）
  ④ build_data.py           -> 从 xlsx 抽取全部指标 + 渠道挂账(qudao) -> /tmp/_full.json
  ⑤ merge                   -> 把 qudao 合并进 data.json（保留复算口径的业绩/洞察）
  ⑥ build.py               -> 重建 index.html（内嵌最新 data.json）
  ⑦ git push               -> 推线上 GitHub Pages（失败不影响本地结果）

启动：
  python3 refresh_server.py
前端访问： http://localhost:8765/refresh  （触发并轮询 /status，完成后取 /data）
"""
import os, sys, json, subprocess, threading, datetime, time
from http.server import BaseHTTPRequestHandler, HTTPServer

BASE = os.path.dirname(os.path.abspath(__file__))
XLSX = "/Users/mac/Desktop/李家村销售/李家村8月任务进度.xlsx"
PORT = 8765
PY = sys.executable

_lock = threading.Lock()
_running = False
_state = {"status": "idle", "msg": "刷新服务已启动，等待刷新", "at": None, "steps": []}


def _set(status, msg):
    _state["status"] = status
    _state["msg"] = msg
    _state["at"] = datetime.datetime.now().strftime("%H:%M:%S")


def run(cmd, timeout=600):
    """跑一个子命令，返回 CompletedProcess（捕获输出）。"""
    env = dict(os.environ)
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        env.pop(k, None)
    return subprocess.run(cmd, cwd=BASE, capture_output=True, text=True,
                          timeout=timeout, env=env)


MERGE_CODE = (
    "import json\n"
    "a=json.load(open('data.json',encoding='utf-8'))\n"
    "b=json.load(open('/tmp/_full.json',encoding='utf-8'))\n"
    "a['qudao']=b.get('qudao')\n"
    "json.dump(a,open('data.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)\n"
    "print('merged qudao:', bool(a.get('qudao')))\n"
)


def pipeline():
    global _running
    with _lock:
        if _running:
            return
        _running = True
    steps = []
    try:
        # ① 用友 XS 明细
        _set("running", "① 抓取用友云「门店毛利明细」…")
        r = run(["bash", "fetch_yonyou.sh", os.path.join(BASE, "yonyou_raw.tsv")])
        steps.append(("用友明细抓取", r.returncode == 0, _tail(r)))
        # ② 销售分析导入
        _set("running", "② 抓取用友云「销售分析」并导入表格…")
        r = run(["bash", "fetch_sales_analysis.sh"])
        steps.append(("销售分析导入", r.returncode == 0, _tail(r)))
        # ③ 复算业绩
        _set("running", "③ 复算业绩 → data.json…")
        r = run([PY, "calc_data.py", "yonyou_raw.tsv", "-o", "data.json"])
        steps.append(("业绩复算", r.returncode == 0, _tail(r)))
        # ④ 抽渠道挂账 + 全部表格指标
        _set("running", "④ 抽取渠道挂账(qudao)等全部指标…")
        r = run([PY, "build_data.py", XLSX, "/tmp/_full.json"])
        ok = r.returncode == 0
        steps.append(("指标抽取", ok, _tail(r)))
        if ok:
            run([PY, "-c", MERGE_CODE])
        # ⑤ 重建看板
        _set("running", "⑤ 重建看板 index.html…")
        r = run([PY, "build.py"])
        steps.append(("看板重建", r.returncode == 0, _tail(r)))
        # ⑥ 推线上（先提交本次重建的产物，再推送）
        _set("running", "⑥ 提交并推送线上副本…")
        msg = "自动刷新 " + datetime.datetime.now().strftime("%m-%d %H:%M")
        r = run(["bash", "-c",
                 "git add -A && git commit -q -m '%s' && git push origin main" % msg])
        steps.append(("推送线上", r.returncode == 0, _tail(r)))

        _state["steps"] = [
            {"name": n, "ok": ok, "log": log[-200:]} for n, ok, log in steps
        ]
        ft = json.load(open(os.path.join(BASE, "data.json"), encoding="utf-8")) \
            .get("meta", {}).get("fetchTime", "")
        _set("done", "刷新完成 · " + ft)
    except subprocess.TimeoutExpired:
        _set("error", "某一步超时（>10分钟），请检查网络或用友登录态")
    except Exception as e:
        _set("error", str(e)[:300])
    finally:
        _running = False


def _tail(r):
    s = (r.stderr or "") + (r.stdout or "")
    return s.strip()[-300:]


class H(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")

    def _json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self._cors()
        self.end_headers()
        self.wfile.write(b)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/refresh"):
            with _lock:
                if _running:
                    return self._json({"accepted": True, "already": True,
                                       "msg": "已有刷新任务进行中"})
                threading.Thread(target=pipeline, daemon=True).start()
                time.sleep(0.1)
            return self._json({"accepted": True})
        if path == "/status":
            return self._json(_state)
        if path == "/data":
            try:
                d = json.load(open(os.path.join(BASE, "data.json"), encoding="utf-8"))
                return self._json(d)
            except Exception as e:
                return self._json({"error": str(e)}, 500)
        return self._json({"error": "unknown path"}, 404)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print(f"🐝 看板刷新服务启动： http://localhost:{PORT}/refresh")
    HTTPServer(("127.0.0.1", PORT), H).serve_forever()
