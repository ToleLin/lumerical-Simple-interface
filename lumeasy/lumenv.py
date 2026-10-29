"""找 Lumerical 安裝位置、載入 lumapi。

只用 Lumerical 官方的 Python API(lumapi)跟軟體溝通;
不碰授權、不碰授權伺服器、不改任何系統設定。
"""
from __future__ import annotations

import glob
import importlib.util
import json
import os
import re
import sys

# 設定與暫存放這裡;LUMEASY_HOME 可以改位置(測試用)。不要改 APPDATA 本身:Lumerical 也從那裡讀偏好與授權設定。
APPDATA = os.environ.get("LUMEASY_HOME") or os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "LumEasy")
SETTINGS = os.path.join(APPDATA, "settings.json")


def _ver_key(path: str):
    m = re.search(r"v(\d{3})", path.replace("\\", "/"))
    return int(m.group(1)) if m else 0


def find_installs() -> list[str]:
    """回傳所有找得到的 Lumerical 根目錄(含 api/python/lumapi.py),新版在前。"""
    pats = []
    for pf in {os.environ.get("ProgramFiles", r"C:\Program Files"), r"C:\Program Files", r"D:\Program Files"}:
        pats += [
            os.path.join(pf, "Lumerical", "v*"),
            os.path.join(pf, "Lumerical", "*", "v*"),
            os.path.join(pf, "ANSYS Inc", "v*", "Lumerical"),
            os.path.join(pf, "ANSYS Inc", "ANSYS Student", "v*", "Lumerical"),
            os.path.join(pf, "Ansys Inc", "v*", "Lumerical"),
        ]
    for env in ("LUMERICAL_HOME", "LUMERICAL_ROOT"):
        if os.environ.get(env):
            pats.append(os.environ[env])
    found = []
    for pat in pats:
        for root in glob.glob(pat):
            if os.path.isfile(os.path.join(root, "api", "python", "lumapi.py")):
                r = os.path.normpath(root)
                if r not in found:
                    found.append(r)
    return sorted(found, key=_ver_key, reverse=True)


def lumapi_path(root: str) -> str:
    return os.path.join(root, "api", "python", "lumapi.py")


def gui_exe(root: str, product: str = "fdtd") -> str:
    name = {"fdtd": "fdtd-solutions.exe", "mode": "mode-solutions.exe"}[product]
    for cand in (os.path.join(root, "bin", name), os.path.join(root, "..", "bin", name)):
        if os.path.isfile(cand):
            return os.path.normpath(cand)
    return os.path.join(root, "bin", name)


def resolve_root(user_root: str = "") -> str:
    if user_root:
        r = user_root
        if r.lower().endswith("lumapi.py"):
            r = os.path.dirname(os.path.dirname(os.path.dirname(r)))
        if os.path.isfile(lumapi_path(r)):
            return os.path.normpath(r)
        raise FileNotFoundError(f"這個資料夾裡沒有 api/python/lumapi.py:{user_root}")
    roots = find_installs()
    if not roots:
        raise FileNotFoundError("找不到 Lumerical。請在「專案」頁手動選安裝資料夾(裡面要有 api\\python\\lumapi.py)")
    return roots[0]


def load_lumapi(root: str):
    """從安裝資料夾載入 lumapi 模組(不複製、不修改原檔)。"""
    p = lumapi_path(root)
    spec = importlib.util.spec_from_file_location("lumapi", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["lumapi"] = mod
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        spec.loader.exec_module(mod)
    return mod


def version_label(root: str) -> str:
    m = re.search(r"v(\d)(\d)(\d)", root.replace("\\", "/"))
    if not m:
        return os.path.basename(root)
    return f"20{m.group(1)}{m.group(2)} R{m.group(3)}"


def load_settings() -> dict:
    try:
        with open(SETTINGS, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_settings(s: dict):
    os.makedirs(APPDATA, exist_ok=True)
    tmp = SETTINGS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=1)
    os.replace(tmp, SETTINGS)


def work_dir() -> str:
    """純英數的暫存工作資料夾:Lumerical 從含中文的路徑讀寫 .fsp 有時會卡住。"""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP") or os.path.expanduser("~")
    d = os.path.join(base, "LumEasy", "work")
    try:
        d.encode("ascii")
    except UnicodeEncodeError:
        d = os.path.join(os.path.splitdrive(sys.executable)[0] + os.sep, "LumEasy_work")
    os.makedirs(d, exist_ok=True)
    return d


def is_ascii(s: str) -> bool:
    try:
        s.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def clean_env(env: dict) -> dict:
    """給 Lumerical 用的乾淨環境變數。
    Lumerical 本身是 Qt5 程式;繼承到本程式(PySide6 / Qt6)的 QT_* 變數或 Qt6 的 DLL 路徑會讓它一開就當掉(0xC0000005)。"""
    out = {}
    mei = getattr(sys, "_MEIPASS", None)
    for k, v in env.items():
        ku = k.upper()
        if ku.startswith(("QT_", "QML", "QTWEBENGINE", "PYSIDE", "SHIBOKEN")):
            continue
        if ku == "PATH":
            parts = [x for x in v.split(os.pathsep)
                     if x and not (mei and os.path.normcase(x).startswith(os.path.normcase(mei)))
                     and "pyside6" not in x.lower() and "shiboken6" not in x.lower()]
            v = os.pathsep.join(parts)
        out[k] = v
    return out
