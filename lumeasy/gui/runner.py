"""在背景開 worker 行程、讀它的事件檔、卡住時整棵行程樹關掉重來。

只會關掉「自己開的」worker 和它底下的 Lumerical(taskkill /T 從 worker 往下砍),
不會碰授權服務或其他程式開的 Lumerical。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from lumeasy import lumenv


def worker_cmd(job_path):
    if getattr(sys, "frozen", False):
        return sys.executable, ["--worker", job_path]
    exe = sys.executable
    if exe.lower().endswith("pythonw.exe"):
        cand = exe[:-len("pythonw.exe")] + "python.exe"
        if os.path.exists(cand):
            exe = cand
    return exe, ["-m", "lumeasy", "--worker", job_path]


def kill_tree(pid):
    if not pid:
        return
    try:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=30)
    except Exception:  # noqa: BLE001
        pass


class Runner(QObject):
    event = Signal(dict)
    finished = Signal(bool, dict)     # (成功?, 結果)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.proc = None
        self.timer = QTimer(self)
        self.timer.setInterval(300)
        self.timer.timeout.connect(self._poll)
        self.job = None
        self.events_path = None
        self.pos = 0
        self.stage = None
        self.stage_t = 0
        self.retries = 0
        self.result = None
        self.error = None
        self.open_timeout = 300

    def busy(self):
        return self.proc is not None

    def start(self, job: dict, open_timeout=300, retries=1):
        jobs = os.path.join(lumenv.APPDATA, "jobs")
        os.makedirs(jobs, exist_ok=True)
        self._cleanup_old(jobs)
        jid = time.strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:6]
        self.events_path = os.path.join(jobs, jid + "_events.jsonl")
        job = dict(job, events=self.events_path)
        path = os.path.join(jobs, jid + "_job.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(job, f, ensure_ascii=False)
        self.job, self.job_path = job, path
        self.open_timeout, self.retries = open_timeout, retries
        self._launch()

    def _launch(self):
        self.pos, self.stage, self.stage_t = 0, "launch", time.time()
        self.result = self.error = None
        open(self.events_path, "a").close()
        self.proc = QProcess(self)
        exe, args = worker_cmd(self.job_path)
        self.proc.setProgram(exe)
        self.proc.setArguments(args)
        self.proc.setWorkingDirectory(os.path.dirname(os.path.dirname(os.path.abspath(__file__))) if not getattr(sys, "frozen", False) else os.path.dirname(sys.executable))
        from PySide6.QtCore import QProcessEnvironment
        env = QProcessEnvironment()
        for k, v in lumenv.clean_env(dict(os.environ)).items():
            env.insert(k, v)
        if not getattr(sys, "frozen", False):
            root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            env.insert("PYTHONPATH", root + os.pathsep + env.value("PYTHONPATH", ""))
        self.proc.setProcessEnvironment(env)
        out = self.events_path.replace("_events.jsonl", "_stdout.txt")
        self.proc.setStandardOutputFile(out, QProcess.Append)
        self.proc.setStandardErrorFile(out, QProcess.Append)
        self.proc.finished.connect(self._done)
        self.proc.start()
        self.timer.start()

    def stop(self):
        if self.proc is not None:
            kill_tree(self.proc.processId())
            self.error = self.error or "已手動停止"

    def _poll(self):
        try:
            with open(self.events_path, encoding="utf-8") as f:
                f.seek(self.pos)
                chunk = f.read()
                self.pos = f.tell()
        except OSError:
            chunk = ""
        for line in chunk.splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e["t"] == "stage":
                self.stage, self.stage_t = e["name"], time.time()
            elif e["t"] == "done":
                self.result = e.get("result", {})
            elif e["t"] == "error":
                self.error = e.get("msg", "")
            self.event.emit(e)
        # 看門狗:開 Lumerical 超過時間還沒連上 → 砍掉自己的行程樹重來
        if self.stage in ("open", "launch") and time.time() - self.stage_t > self.open_timeout and self.proc is not None:
            self.event.emit({"t": "warn", "msg": f"Lumerical {self.open_timeout} 秒沒有回應(常見於當天第一次開或午夜前後),"
                                                 f"關掉這次開的 Lumerical 重來…"})
            self.stage = "killed"
            self._retry = self.retries > 0
            kill_tree(self.proc.processId())

    _retry = False

    def _done(self, code, status):
        self._poll()
        self.timer.stop()
        self.proc = None
        if self._retry:
            self._retry = False
            self.retries -= 1
            self._launch()
            return
        ok = self.result is not None and not self.error
        if not ok and not self.error:
            self.error = f"背景程式意外結束(代碼 {code})"
        self.finished.emit(ok, self.result if ok else {"error": self.error})

    @staticmethod
    def _cleanup_old(d, keep_days=7):
        now = time.time()
        for f in os.listdir(d):
            p = os.path.join(d, f)
            try:
                if now - os.path.getmtime(p) > keep_days * 86400:
                    os.remove(p)
            except OSError:
                pass
