"""在獨立行程裡和 Lumerical 溝通(介面會監看它,卡住時可以整棵行程樹關掉重來)。

每一個工作都開一個全新的 Lumerical session,做完就關:
同一個 session 重複建模 / 執行很容易卡死。
只用 lumapi;不碰授權、不碰授權伺服器。
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import sys
import threading
import time
import traceback

import numpy as np


class Events:
    def __init__(self, path):
        self.path = path
        self.f = open(path, "a", encoding="utf-8")
        self.lines = []

    def emit(self, t, **kw):
        kw["t"] = t
        kw["time"] = time.time()
        self.f.write(json.dumps(kw, ensure_ascii=False, default=str) + "\n")
        self.f.flush()
        if t in ("log", "warn", "error"):
            self.lines.append(f"[{dt.datetime.now():%H:%M:%S}] {t.upper():5s} {kw.get('msg', '')}")

    def log(self, msg):
        self.emit("log", msg=msg)

    def warn(self, msg):
        self.emit("warn", msg=msg)

    def stage(self, name, msg=""):
        self.emit("stage", name=name, msg=msg)
        if msg:
            self.log(msg)

    def progress(self, pct, msg=""):
        self.emit("progress", pct=pct, msg=msg)


BAD = re.compile(r'[\\/:*?"<>|]')


def safe_name(s: str) -> str:
    s = BAD.sub("_", s.strip()) or "simulation"
    return s.rstrip(". ")


def target_path(folder: str, name: str, ext: str, overwrite: bool) -> str:
    p = os.path.join(folder, name + ext)
    if overwrite or not os.path.exists(p):
        return p
    i = 1
    while os.path.exists(os.path.join(folder, f"{name}_{i:02d}{ext}")):
        i += 1
    return os.path.join(folder, f"{name}_{i:02d}{ext}")


def open_session(ev, root, hide=True):
    from lumeasy import lumenv
    ev.stage("open", f"開啟 Lumerical({lumenv.version_label(root)})…")
    lumapi = lumenv.load_lumapi(root)
    t0 = time.time()
    fdtd = lumapi.FDTD(hide=hide)
    ev.stage("opened", f"Lumerical 已連線({time.time() - t0:.1f} 秒)")
    return fdtd


def run_script(ev, fdtd, script):
    n = len(script.stmts)
    t0 = time.time()
    for i, s in enumerate(script.stmts):
        try:
            fdtd.eval(s.code)
        except Exception as e:  # noqa: BLE001
            msg = str(e).strip().strip("'")
            if s.optional:
                ev.warn(f"{s.label}:這台 Lumerical 不支援「{s.code[:80]}」,已略過({msg})")
                continue
            raise RuntimeError(f"建模失敗於【{s.label}】\n指令:{s.code[:300]}\nLumerical 回應:{msg}") from None
        if i % 25 == 0 or i == n - 1:
            ev.progress(100.0 * (i + 1) / n, f"建模 {i + 1}/{n}")
    ev.log(f"建模指令 {n} 行全部完成({time.time() - t0:.1f} 秒)")


def verify(ev, fdtd, script):
    bad, n = [], 0
    for obj, prop, want in script.checks[:400]:
        try:
            got = float(np.real(fdtd.getnamed(obj, prop)))
        except Exception as e:  # noqa: BLE001
            bad.append(f"{obj}.{prop} 讀不回來({str(e)[:60]})")
            continue
        n += 1
        if abs(got - want) > 1e-13 + 1e-6 * abs(want):
            bad.append(f"{obj}.{prop}:想要 {want * 1e9:.4g} nm,Lumerical 裡是 {got * 1e9:.4g} nm")
    if bad:
        for b in bad[:20]:
            ev.warn("幾何核對:" + b)
    else:
        ev.log(f"幾何核對:讀回 {n} 個位置 / 尺寸,全部和設定一致")
    return bad


class LogTail(threading.Thread):
    """跟著引擎 log 回報進度(run() 是阻塞的,只能從旁邊看)。"""

    def __init__(self, ev, path):
        super().__init__(daemon=True)
        self.ev, self.path, self.stop = ev, path, False

    def run(self):
        from lumeasy.results import PROG
        pos, last = 0, -1.0
        while not self.stop:
            try:
                with open(self.path, encoding="utf-8", errors="replace") as f:
                    f.seek(pos)
                    chunk = f.read()
                    pos = f.tell()
                for line in chunk.splitlines():
                    m = PROG.search(line)
                    if m:
                        pct = float(m.group(1))
                        if pct - last >= 0.5:
                            last = pct
                            self.ev.progress(pct, f"模擬 {pct:.1f}%,剩約 {m.group(2)},Auto Shutoff {float(m.group(3)):.2g}")
                    elif "Simulation size in gridpoints" in line or "host available memory" in line:
                        self.ev.log("引擎:" + line.strip())
                    elif "diverg" in line.lower() or "sufficient memory" in line.lower():
                        self.ev.warn("引擎:" + line.strip())
            except OSError:
                pass
            time.sleep(1.0)


def _clean_work(root, hours=24):
    """清掉之前被中斷的工作留下的暫存資料夾(超過一天、裡面沒有 .fsp 的)。
    有 .fsp 的不刪:那可能是中斷前唯一一份模擬結果。"""
    now = time.time()
    for d in os.listdir(root):
        p = os.path.join(root, d)
        try:
            if not (d.startswith(("job_", "export_")) and os.path.isdir(p) and now - os.path.getmtime(p) > hours * 3600):
                continue
            if any(f.lower().endswith(".fsp") for f in os.listdir(p)):
                continue
            shutil.rmtree(p, ignore_errors=True)
        except OSError:
            pass


def job_build(ev, job, run: bool):
    from lumeasy import lsf, lumenv, model as M
    from lumeasy import results as R
    p = M.upgrade(job["project"])
    root = lumenv.resolve_root(p["project"].get("lumerical_dir", ""))
    folder = p["project"].get("folder") or ""
    if not folder:
        raise RuntimeError("還沒選存放資料夾")
    os.makedirs(folder, exist_ok=True)
    name = safe_name(p["project"]["name"])
    runcfg = p["run"]
    fsp = target_path(folder, name, ".fsp", bool(runcfg.get("overwrite")))
    base = os.path.splitext(os.path.basename(fsp))[0]
    job["_log_file"] = os.path.join(folder, base + "_lumeasy_log.txt")
    use_work = not lumenv.is_ascii(fsp)
    if use_work:
        _clean_work(lumenv.work_dir())
        wd = os.path.join(lumenv.work_dir(), dt.datetime.now().strftime("job_%Y%m%d_%H%M%S"))
        os.makedirs(wd, exist_ok=True)
        fsp_run = os.path.join(wd, "model.fsp")
        ev.log(f"路徑有中文 / 非英數字元:先在 {wd} 建模與執行,完成後複製到 {folder}(Lumerical 讀寫中文路徑有時會卡住)")
    else:
        fsp_run = fsp
    # 先產生腳本(有錯就不用開 Lumerical)
    script = lsf.generate(p, fsp_run)
    for w in script.warnings:
        ev.warn(w)
    lsf_text = lsf.generate(p, fsp).text(
        f"LumEasy 產生的 Lumerical 腳本({dt.datetime.now():%Y-%m-%d %H:%M})\n"
        f"專案:{p['project']['name']}  維度:{p['project']['dimension']}\n"
        "可以直接在 Lumerical FDTD 的 Script 視窗執行,重建同一個模型。")
    lsf_path = os.path.join(folder, base + ".lsf")
    with open(lsf_path, "w", encoding="utf-8") as f:
        f.write(lsf_text)
    with open(os.path.join(folder, base + "_project.json"), "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False, indent=1)
    ev.log(f"腳本已存:{lsf_path}")
    fdtd = open_session(ev, root, hide=True)
    result = {"fsp": fsp, "lsf": lsf_path, "files": [], "root": root}
    try:
        ev.stage("build", "開始建模…")
        run_script(ev, fdtd, script)
        result["geometry_mismatch"] = verify(ev, fdtd, script)
        ev.log(f"模型已存檔:{fsp_run}")
        if run:
            nproc = int(runcfg.get("processes") or 0)
            if nproc > 0:
                try:
                    fdtd.eval(f'setresource("FDTD",1,"processes",{nproc});')
                    ev.log(f"使用 {nproc} 個 CPU 行程")
                except Exception as e:  # noqa: BLE001
                    ev.warn(f"設定 CPU 行程數失敗({e}),用 Lumerical 目前的設定")
            ev.stage("run", "開始模擬(進度會顯示在下面)…")
            logp = R.engine_log_path(fsp_run)
            tail = LogTail(ev, logp)
            tail.start()
            t0 = time.time()
            fdtd.run()
            tail.stop = True
            ev.log(f"模擬結束({(time.time() - t0) / 60:.1f} 分)")
            fdtd.save()   # 先存一份有結果的檔,擷取出錯也不用重跑
            diag = R.check_engine_log(fsp_run, float(p["region"].get("shutoff") or 1e-5))
            result["engine"] = diag
            for m in diag["messages"]:
                (ev.warn if diag["status"] != "ok" else ev.log)("引擎檢查:" + m)
            ev.log(f"引擎狀態:{diag['status']}  網格:{diag.get('gridpoints', '?')}")
            ev.stage("extract", "取出監視器資料…")
            wanted = [m["name"] for m in p["monitors"] if m.get("enabled", True) and m["kind"] != "movie"]
            data = R.extract(fdtd, wanted, M.is2d(p), log=ev.log)
            for w in R.check_power(data):
                ev.warn(w)
            out_dir = os.path.join(folder, base + "_results")
            files = R.save_all(data, out_dir, base, runcfg.get("formats") or [], runcfg.get("field_wl", "center"),
                               p["project"].get("unit", "nm"), M.is2d(p),
                               summary_extra={"engine": diag, "project": p["project"]["name"]}, log=ev.log,
                               plot_cfg={m["name"]: {"field": bool(m.get("plot_field", True)),
                                                     "spectrum": bool(m.get("plot_spectrum", True))}
                                         for m in p["monitors"]})
            result["files"] = files
            result["out_dir"] = out_dir
            ev.log(f"輸出 {len(files)} 個檔案到 {out_dir}")
    finally:
        try:
            fdtd.close()
        except Exception:  # noqa: BLE001
            pass
    if use_work:
        shutil.copy2(fsp_run, fsp)
        lp = R.engine_log_path(fsp_run)
        if os.path.exists(lp):
            shutil.copy2(lp, R.engine_log_path(fsp))
        ev.log(f"已複製到:{fsp}")
        shutil.rmtree(os.path.dirname(fsp_run), ignore_errors=True)
    return result


def job_export(ev, job):
    from lumeasy import lumenv
    from lumeasy import results as R
    src = job["fsp"]
    root = lumenv.resolve_root(job.get("lumerical_dir", ""))
    out_dir = job.get("out_dir") or os.path.splitext(src)[0] + "_results"
    base = os.path.splitext(os.path.basename(src))[0]
    tmp = None
    load = src
    if not lumenv.is_ascii(src):
        tmp = os.path.join(lumenv.work_dir(), dt.datetime.now().strftime("export_%Y%m%d_%H%M%S"))
        os.makedirs(tmp, exist_ok=True)
        load = os.path.join(tmp, "model.fsp")
        ev.log("檔案路徑有中文:先複製到英數路徑再開(直接開有時會卡住)…")
        shutil.copy2(src, load)
    fdtd = open_session(ev, root, hide=True)
    try:
        ev.stage("load", f"載入 {os.path.basename(src)}…")
        fdtd.load(load.replace("\\", "/"))
        try:
            d2 = str(fdtd.getnamed("FDTD", "dimension")).strip() in ("2D", "1")
        except Exception:  # noqa: BLE001
            d2 = False
        ev.stage("extract", "取出監視器資料…")
        data = R.extract(fdtd, job.get("monitors") or None, d2, log=ev.log)
        for w in R.check_power(data):
            ev.warn(w)
        files = R.save_all(data, out_dir, base, job.get("formats") or ["npz"], job.get("field_wl", "center"),
                           job.get("unit", "nm"), d2, summary_extra={"source_fsp": src}, log=ev.log)
        ev.log(f"輸出 {len(files)} 個檔案到 {out_dir}")
        return {"files": files, "out_dir": out_dir}
    finally:
        try:
            fdtd.close()
        except Exception:  # noqa: BLE001
            pass
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


def job_probe(ev, job):
    from lumeasy import lumenv
    root = lumenv.resolve_root(job.get("lumerical_dir", ""))
    fdtd = open_session(ev, root, hide=True)
    try:
        fdtd.eval("lemlist = getmaterial();")       # 不帶參數直接呼叫 getmaterial() 會卡住,要這樣寫
        mats = [s.strip() for s in str(fdtd.getv("lemlist")).splitlines() if s.strip()]
        try:
            fdtd.eval("lever = version;")
            ver = str(fdtd.getv("lever"))
        except Exception:  # noqa: BLE001
            ver = lumenv.version_label(root)
        try:
            fdtd.eval('lenproc = getresource("FDTD",1,"processes");')
            nproc = str(fdtd.getv("lenproc"))
        except Exception:  # noqa: BLE001
            nproc = "?"
        ev.log(f"連線成功:{ver},內建材料 {len(mats)} 種,目前 CPU 行程設定 {nproc}")
        return {"materials": mats, "version": ver, "root": root, "processes": nproc}
    finally:
        try:
            fdtd.close()
        except Exception:  # noqa: BLE001
            pass


def main(job_path: str) -> int:
    from lumeasy import lumenv
    env = lumenv.clean_env(dict(os.environ))     # Lumerical 會繼承這個行程的環境變數
    os.environ.clear()
    os.environ.update(env)
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    with open(job_path, encoding="utf-8") as f:
        job = json.load(f)
    ev = Events(job["events"])
    ev.stage("start", "")
    code = 0
    try:
        a = job["action"]
        if a == "probe":
            res = job_probe(ev, job)
        elif a == "build":
            res = job_build(ev, job, run=False)
        elif a == "build_run":
            res = job_build(ev, job, run=True)
        elif a == "export":
            res = job_export(ev, job)
        else:
            raise RuntimeError(f"未知工作 {a}")
        ev.emit("done", result=res)
    except Exception as e:  # noqa: BLE001
        ev.emit("error", msg=str(e), trace=traceback.format_exc())
        code = 1
    finally:
        logf = job.get("_log_file") or (os.path.join(job["log_dir"], "lumeasy_log.txt") if job.get("log_dir") else None)
        if logf:
            try:
                with open(logf, "a", encoding="utf-8") as f:
                    f.write("\n".join(ev.lines) + "\n")
            except OSError:
                pass
        ev.f.close()
    return code
