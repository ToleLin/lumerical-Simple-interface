"""開跑前粗估網格數與記憶體(Lumerical 在隱藏模式記憶體不足時會跳出看不到的視窗、永遠不返回)。

只是數量級估計:真正的網格由 Lumerical 的非均勻網格決定。
"""
from __future__ import annotations

import ctypes
import math

from lumeasy import model as M
from lumeasy import materials as MAT

PPW = {1: 6, 2: 10, 3: 14, 4: 18, 5: 22, 6: 26, 7: 30, 8: 34}   # 每個波長幾格(依網格精度)


def free_ram_gb() -> float:
    class MS(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
    try:
        s = MS()
        s.dwLength = ctypes.sizeof(MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s))
        return s.ullAvailPhys / 1024 ** 3
    except Exception:  # noqa: BLE001
        return float("nan")


def estimate(p: dict) -> dict:
    d2 = M.is2d(p)
    placed = M.place_objects(p)
    reg = M.compute_region(p, placed)
    g, r = p["global"], p["region"]
    wl = float(g["wl_start"])
    ppw = PPW.get(int(r["mesh_acc"]), 10)
    nbg = float(r["bg_index"])
    dx_bg = wl / (nbg * ppw)
    dims = ("x", "z") if d2 else ("x", "y", "z")
    span = {a: max(reg[a][1] - reg[a][0], 1e-3) for a in dims}
    vol = math.prod(span.values())
    cells = 0.0
    obj_vol = 0.0
    nmax = nbg
    for rr in placed:
        if not rr["enabled"] or rr["error"]:
            continue
        n = MAT.rough_index(rr["obj"].get("material", ""), p["materials"], wl)
        nmax = max(nmax, n)
        b = rr["bbox"]
        lo = {"x": max(b[0], reg["x"][0]), "y": max(b[2], reg["y"][0]), "z": max(b[4], reg["z"][0])}
        hi = {"x": min(b[1], reg["x"][1]), "y": min(b[3], reg["y"][1]), "z": min(b[5], reg["z"][1])}
        v = math.prod(max(hi[a] - lo[a], 0) for a in dims)
        dxo = wl / (max(n, nbg) * ppw)
        cells += v / dxo ** len(dims)
        obj_vol += v
    cells += max(vol - obj_vol, 0) / dx_bg ** len(dims)
    for m in p["mesh"]:
        if not m.get("enabled", True):
            continue
        dd = [float(m["dx"]), float(m["dz"])] if d2 else [float(m["dx"]), float(m["dy"]), float(m["dz"])]
        sp = [float(m["sx"]), float(m["sz"])] if d2 else [float(m["sx"]), float(m["sy"]), float(m["sz"])]
        if m.get("target"):
            for rr in placed:
                if rr["obj"]["name"] == m["target"] and not rr["error"]:
                    b, buf = rr["bbox"], float(m.get("buffer") or 0)
                    sp = [b[1] - b[0] + 2 * buf, b[5] - b[4] + 2 * buf] if d2 else \
                         [b[1] - b[0] + 2 * buf, b[3] - b[2] + 2 * buf, b[5] - b[4] + 2 * buf]
        cells += math.prod(s / max(d, 0.1) for s, d in zip(sp, dd))
    # PML:每個 PML 面多 layers 層
    npml = int(r.get("pml_layers") or 12)
    dx_avg = (vol / max(cells, 1)) ** (1 / len(dims))
    pml_axes = [("x", r["bc_x"] == "PML")] + ([] if d2 else [("y", r["bc_y"] == "PML")]) + \
               [("z", r["bc_zmin"] == "PML"), ("z", r["bc_zmax"] == "PML")]
    for a, on in pml_axes:
        if on:
            area = vol / span[a]
            cells += npml * area / dx_avg ** (len(dims) - 1) * (2 if a != "z" else 1)
    grid_gb = cells * 18 / 1024 ** 3 + 0.3
    mon_gb = 0.0
    for m in p["monitors"]:
        if not m.get("enabled", True) or m["kind"] not in ("power", "profile"):
            continue
        axes = {"z": "xy", "x": "yz", "y": "xz", "point": "", "lx": "x", "ly": "y", "lz": "z", "3d": "xyz"}[m["orient"]]
        if d2:
            axes = axes.replace("y", "")
        pts = 1.0
        ds = max(int(m.get("downsample") or 1), 1)
        for a in axes:
            v = m.get("s" + a)
            s = float(v) if v not in (None, "") else span.get(a, 0)
            pts *= max(s / dx_avg / ds, 1)
        nf = int(m.get("fpoints") or 0) or int(g["fpoints"])
        comps = len([c for c in (m.get("outputs") or []) if c != "power"])
        mon_gb += pts * nf * comps * 16 / 1024 ** 3
    return {"cells": cells, "grid_gb": grid_gb, "mon_gb": mon_gb, "total_gb": grid_gb + mon_gb,
            "dx_bg_nm": dx_bg, "dx_min_nm": wl / (nmax * ppw), "free_gb": free_ram_gb(),
            "fsp_gb": mon_gb * 1.05 + 0.01}
