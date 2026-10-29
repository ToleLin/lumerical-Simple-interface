"""開發測試:把範例專案丟給 worker(獨立行程)跑,印出事件。
用法:python dev/run_job.py <example> <action> [out_dir]"""
import json, os, subprocess, sys, time, pathlib
here = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(here.parent))
from lumeasy import examples, model as M
from dev_kitchen import kitchen  # noqa: E402

name, action = sys.argv[1], sys.argv[2]
out = sys.argv[3] if len(sys.argv) > 3 else str(here / "out")
p = {"pillar": examples.pillar_unit_cell_3d, "grating": examples.grating_2d, "kitchen": kitchen}[name]()
p["project"]["folder"] = out
p["run"]["processes"] = 0
os.makedirs(out, exist_ok=True)
ev = here / f"events_{name}_{int(time.time())}.jsonl"
job = here / f"job_{name}.json"
json.dump({"action": action, "project": p, "events": str(ev)}, open(job, "w", encoding="utf-8"), ensure_ascii=False)
t0 = time.time()
proc = subprocess.Popen([str(here.parent / ".venv/Scripts/python.exe"), "-m", "lumeasy", "--worker", str(job)],
                        cwd=str(here.parent))
pos = 0
while True:
    time.sleep(0.5)
    if ev.exists():
        with open(ev, encoding="utf-8") as f:
            f.seek(pos); chunk = f.read(); pos = f.tell()
        for line in chunk.splitlines():
            e = json.loads(line)
            if e["t"] == "progress" and "建模" in e.get("msg", ""):
                continue
            msg = e.get("msg") or e.get("name") or ""
            if e["t"] == "done":
                msg = json.dumps(e["result"], ensure_ascii=False)[:1500]
            if e["t"] == "error":
                msg += "\n" + e.get("trace", "")
            print(f"{time.time()-t0:6.1f}s {e['t']:8s} {msg}", flush=True)
    if proc.poll() is not None:
        time.sleep(0.6)
        if ev.exists():
            with open(ev, encoding="utf-8") as f:
                f.seek(pos); rest = f.read()
            for line in rest.splitlines():
                e = json.loads(line); print("  ", e["t"], (e.get("msg") or json.dumps(e.get("result"), ensure_ascii=False))[:1500])
        print("exit", proc.returncode)
        break
