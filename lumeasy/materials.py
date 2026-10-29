"""材料:讀檔、自動判斷欄位、n,k ⇄ ε 轉換、匯出。

Lumerical 的慣例是 n + ik(k > 0 = 吸收),ε = (n + ik)² = (n² − k²) + i·2nk。
「Sampled 3D data」材料要的是複數 ε,不是 n + ik(放錯只會得到 √n,不會報錯)。
"""
from __future__ import annotations

import math
import re

import numpy as np

C0 = 299792458.0
H_EV = 4.135667696e-15  # eV·s

X_UNITS = [
    ("nm", "波長 nm"), ("um", "波長 µm"), ("m", "波長 m"),
    ("THz", "頻率 THz"), ("Hz", "頻率 Hz"), ("eV", "光子能量 eV"), ("cm-1", "波數 cm⁻¹"),
]
Y_KINDS = [
    ("nk", "n, k(折射率實部、虛部)"),
    ("eps", "ε1, ε2(介電常數實部、虛部)"),
    ("n", "只有 n(k = 0)"),
]
MATERIAL_KINDS = [
    ("const_nk", "固定折射率 n, k"),
    ("const_eps", "固定介電常數 ε1, ε2"),
    ("file", "從檔案匯入(n,k 或 ε 頻譜)"),
    ("builtin_copy", "複製 Lumerical 內建材料並調整擬合"),
]


def nk_to_eps(n, k):
    e = (np.asarray(n, float) + 1j * np.asarray(k, float)) ** 2
    return e.real, e.imag


def eps_to_nk(e1, e2):
    e1 = np.asarray(e1, float)
    e2 = np.asarray(e2, float)
    mag = np.hypot(e1, e2)
    n = np.sqrt(np.maximum((mag + e1) / 2, 0))
    k = np.sign(e2) * np.sqrt(np.maximum((mag - e1) / 2, 0))
    return n, k


def x_to_wl_nm(x, unit: str):
    x = np.asarray(x, float)
    if unit == "nm":
        return x
    if unit == "um":
        return x * 1e3
    if unit == "m":
        return x * 1e9
    if unit == "THz":
        return C0 / (x * 1e12) * 1e9
    if unit == "Hz":
        return C0 / x * 1e9
    if unit == "eV":
        return C0 * H_EV / x * 1e9
    if unit == "cm-1":
        return 1e7 / x
    raise ValueError(unit)


def wl_nm_to_hz(wl):
    return C0 / (np.asarray(wl, float) * 1e-9)


# --------------------------------------------------------------------------
# 讀檔
# --------------------------------------------------------------------------

_num = re.compile(r"^[\s,;\t]*[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?")


def _split(line: str):
    return [s for s in re.split(r"[,\s;\t]+", line.strip()) if s]


def read_table(path: str):
    """讀純文字 / CSV。回傳 (欄名清單或 None, 數值陣列 N×M, 備註)。
    支援 refractiveindex.info 的 CSV(先 wl,n 一段、再 wl,k 一段)。"""
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        lines = f.read().splitlines()
    blocks, header, cur, headers = [], None, [], []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith(("#", "%", "//", ";")):
            continue
        toks = _split(line)
        try:
            vals = [float(t) for t in toks]
        except ValueError:
            if cur:
                blocks.append((header, cur))
                cur = []
            header = toks
            headers.append(toks)
            continue
        cur.append(vals)
    if cur:
        blocks.append((header, cur))
    if not blocks:
        raise ValueError("檔案裡找不到數字資料")
    note = ""
    # refractiveindex.info:兩段各兩欄(wl,n)(wl,k)→ 合併
    if len(blocks) == 2 and all(len(b[1][0]) == 2 for b in blocks):
        h1, d1 = blocks[0]
        h2, d2 = blocks[1]
        a1, a2 = np.array(d1), np.array(d2)
        k = np.interp(a1[:, 0], a2[np.argsort(a2[:, 0]), 0], a2[np.argsort(a2[:, 0]), 1])
        data = np.column_stack([a1[:, 0], a1[:, 1], k])
        hdr = [(h1 or ["x"])[0], (h1 or ["x", "n"])[-1], (h2 or ["x", "k"])[-1]]
        note = "偵測到 refractiveindex.info 格式(n、k 分兩段),已合併。"
        return hdr, data, note
    hdr, rows = blocks[0]
    width = max(len(r) for r in rows)
    rows = [r for r in rows if len(r) == width]
    data = np.array(rows, float)
    if len(blocks) > 1:
        note = f"檔案有 {len(blocks)} 段資料,只用第一段。"
    if hdr is not None and len(hdr) != data.shape[1]:
        hdr = None
    return hdr, data, note


def guess_format(header, data, filename: str = ""):
    """猜欄位意義。回傳 (x_unit, y_kind, 列欄位 (ix, iy1, iy2), 說明, 有沒有把握)。"""
    h = " ".join(header).lower() if header else ""
    fn = filename.lower()
    ncol = data.shape[1]
    x = data[:, 0]
    sure = False
    # --- y ---
    if any(t in h for t in ("eps", "ε", "epsilon", "e1", "e2", "permittivity", "re(e")):
        y_kind, sure = "eps", True
    elif re.search(r"\bn\b", h) or re.search(r"\bk\b", h) or "index" in h:
        y_kind, sure = ("nk" if ncol >= 3 else "n"), True
    elif ncol >= 3 and np.any(data[:, 1] < 0):
        y_kind, sure = "eps", True      # n 不會是負的 → 一定是 ε(金屬)
    else:
        y_kind = "nk" if ncol >= 3 else "n"
    # --- x ---
    if "thz" in h:
        xu = "THz"
    elif "ev" in h:
        xu = "eV"
    elif "cm" in h and "-1" in h:
        xu = "cm-1"
    elif re.search(r"\bhz\b", h) or "freq" in h:
        xu = "Hz" if x.max() > 1e10 else "THz"
    elif "nm" in h:
        xu = "nm"
    elif "um" in h or "µm" in h or "micron" in h:
        xu = "um"
    elif "wl" in h or "lambda" in h or "wavelength" in h:
        xu = "um" if x.max() < 50 else "nm"
    else:
        sure = False
        if x.max() > 1e10:
            xu = "Hz"
        elif x.max() < 1e-4:
            xu = "m"
        elif x.max() < 30:
            xu = "um"
        else:
            xu = "nm"
    if not header:
        sure = False
    msg = f"猜測:第 1 欄 = {dict(X_UNITS)[xu]},其餘 = {dict(Y_KINDS)[y_kind]}。"
    if not sure:
        msg += "沒有欄名可以確認,請看右邊的 n、k 曲線是否合理再按確定(例如玻璃 n≈1.45、k≈0)。"
    return xu, y_kind, msg, sure


def to_nk(data, x_unit: str, y_kind: str, flip_neg_imag=True):
    """把原始表格轉成依波長遞增排序的 (wl_nm, n, k)。"""
    wl = x_to_wl_nm(data[:, 0], x_unit)
    if y_kind == "nk":
        n, k = data[:, 1], data[:, 2]
    elif y_kind == "n":
        n, k = data[:, 1], np.zeros(len(wl))
    else:
        n, k = eps_to_nk(data[:, 1], data[:, 2])
    notes = []
    if flip_neg_imag and np.all(k <= 0) and np.any(k < 0):
        k = -k
        notes.append("虛部全部是負的(另一種時間慣例),已改成正值 = 吸收。")
    o = np.argsort(wl)
    wl, n, k = wl[o], np.asarray(n, float)[o], np.asarray(k, float)[o]
    keep = np.concatenate([[True], np.diff(wl) > 0])
    if not keep.all():
        notes.append(f"去掉 {int((~keep).sum())} 個重複的波長點。")
    return wl[keep], n[keep], k[keep], notes


def sanity(wl, n, k) -> list[str]:
    w = []
    if np.any(k < 0):
        w.append("有負的 k(增益);一般材料不應如此。")
    if np.any((n < 1) & (k < 0.5 * n + 0.1)):
        w.append("有 n < 1 且 k 很小的點:如果不是金屬,可能是欄位選錯(例如把 ε 當成 n)。")
    if np.any(n > 8):
        w.append("有 n > 8 的點:如果不是金屬,可能是單位或欄位選錯。")
    if len(wl) < 2:
        w.append("資料點太少。")
    return w


def material_nk(m: dict, wl_nm):
    """取某材料在 wl 的 (n, k);內建材料回 None。"""
    wl = np.atleast_1d(np.asarray(wl_nm, float))
    kind = m.get("kind")
    if kind == "const_nk":
        return np.full(wl.shape, float(m.get("n", 1))), np.full(wl.shape, float(m.get("k", 0)))
    if kind == "const_eps":
        n, k = eps_to_nk(float(m.get("e1", 1)), float(m.get("e2", 0)))
        return np.full(wl.shape, float(n)), np.full(wl.shape, float(k))
    if kind == "file" and m.get("wl_nm"):
        W = np.asarray(m["wl_nm"], float)
        return np.interp(wl, W, m["n"]), np.interp(wl, W, m["k"])
    return None


def export_material(m: dict, path: str, fmt: str):
    """fmt: nm_nk / um_nk / THz_eps(頻率 THz, ε1, ε2)/ nm_eps。"""
    if m.get("kind") == "file":
        wl, n, k = (np.asarray(m[a], float) for a in ("wl_nm", "n", "k"))
    else:
        wl = np.linspace(300, 2000, 171)
        n, k = material_nk(m, wl)
    e1, e2 = nk_to_eps(n, k)
    if fmt == "nm_nk":
        arr, hdr = np.column_stack([wl, n, k]), "wavelength_nm\tn\tk"
    elif fmt == "um_nk":
        arr, hdr = np.column_stack([wl / 1e3, n, k]), "wl_um\tn\tk"
    elif fmt == "nm_eps":
        arr, hdr = np.column_stack([wl, e1, e2]), "wavelength_nm\teps1\teps2"
    else:
        f = C0 / (wl * 1e-9) / 1e12
        o = np.argsort(f)
        arr, hdr = np.column_stack([f[o], e1[o], e2[o]]), "f_THz\teps1\teps2"
    np.savetxt(path, arr, delimiter="\t", header=hdr, comments="", fmt="%.8g")


DEFAULT_COLORS = ["#4C9BE8", "#F28E2B", "#59A14F", "#E15759", "#B07AA1", "#EDC948",
                  "#76B7B2", "#FF9DA7", "#9C755F", "#BAB0AC"]


def builtin_color(name: str) -> str:
    n = name.lower()
    if "etch" in n:
        return "#FFFFFF"
    if "sio2" in n or "glass" in n:
        return "#A9D4F5"
    if "si3n4" in n or "nitride" in n:
        return "#7BD389"
    if n.startswith("si ") or "silicon) -" in n:
        return "#6C7A89"
    if "au " in n or "gold" in n:
        return "#E8B923"
    if "ag " in n or "silver" in n or "al " in n or "alumin" in n or "pec" in n:
        return "#C0C4CC"
    if "h2o" in n or "water" in n:
        return "#6FB7E9"
    h = sum(map(ord, name))
    return DEFAULT_COLORS[h % len(DEFAULT_COLORS)]


def hex_rgba(hexs: str, alpha=1.0):
    hexs = (hexs or "#888888").lstrip("#")
    r, g, b = (int(hexs[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return [r, g, b, alpha]


def rough_index(name: str, materials: list[dict], wl_nm: float) -> float:
    """估網格用的折射率(內建材料用名稱猜)。"""
    for m in materials:
        if m["name"] == name:
            nk = material_nk(m, wl_nm)
            if nk is not None:
                return float(math.hypot(nk[0][0], nk[1][0]) if nk[1][0] > nk[0][0] else nk[0][0])
            name = m.get("base", name)
    n = name.lower()
    table = [("etch", 1.0), ("h2o", 1.33), ("sio2", 1.46), ("al2o3", 1.77), ("si3n4", 2.0),
             ("tin", 2.0), ("gaas", 3.8), ("inp", 3.4), ("inas", 3.8), ("ge ", 4.5),
             ("si (", 3.9), ("pec", 1.0)]
    for key, val in table:
        if key in n:
            return val
    metals = ("ag ", "au ", "al ", "cu ", "cr ", "ni ", "pt ", "pd ", "ti ", "w ", "fe ", "ta ", "v ", "sn ", "in ", "rh ")
    if any(n.startswith(mt) for mt in metals):
        return 1.5
    return 2.0


# Lumerical 2020 R2 內建材料庫(還沒連線前先用這份;連線測試後會換成實際讀到的清單)
DEFAULT_BUILTINS = [
    "Ag (Silver) - CRC", "Ag (Silver) - Johnson and Christy", "Ag (Silver) - Palik (0-2um)", "Ag (Silver) - Palik (1-10um)",
    "Al (Aluminium) - CRC", "Al (Aluminium) - Palik", "Al2O3 - Palik", "Au (Gold) - CRC", "Au (Gold) - Johnson and Christy",
    "Au (Gold) - Palik", "C (graphene) - Falkovsky (mid-IR)", "Cr (Chromium) - CRC", "Cr (Chromium) - Palik",
    "Cu (Copper) - CRC", "Cu (Copper) - Palik", "Fe (Iron) - CRC", "Fe (Iron) - Palik", "GaAs - Palik",
    "Ge (Germanium) - CRC", "Ge (Germanium) - Palik", "H2O (Water) - Palik", "In (Indium) - Palik", "InAs - Palik",
    "InP - Palik", "Ni (Nickel) - CRC", "Ni (Nickel) - Palik", "PEC (Perfect Electrical Conductor)", "Pd (Palladium) - Palik",
    "Pt (Platinum) - Palik", "Rh (Rhodium) - Palik", "Si (Silicon) - Palik", "Si3N4 (Silicon Nitride) - Kischkat",
    "Si3N4 (Silicon Nitride) - Phillip", "SiO2 (Glass) - Palik", "Sn (Tin) - Palik", "Ta (Tantalum) - CRC",
    "Ti (Titanium) - CRC", "Ti (Titanium) - Palik", "TiN - Palik", "V (Vanadium ) - CRC", "W (Tungsten) - CRC",
    "W (Tungsten) - Palik", "etch",
]
