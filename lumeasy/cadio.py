"""CAD 檔案讀取(預覽、對齊、DXF 轉多邊形用)。

* STL:Lumerical 原生 stlimport,這裡只讀頂點算包圍盒與預覽。
* GDSII:Lumerical 原生 gdsimport;這裡用 gdstk 讀多邊形給預覽與對齊。
* DXF:Lumerical 不支援 → 這裡把封閉多段線 / 圓轉成多邊形,再用 addpoly 建。
一個 CAD 物件只能有一種材料;不同材料的零件請分成不同檔案或不同圖層各建一個物件。
"""
from __future__ import annotations

import math
import os
import struct

import numpy as np


def mtime(path):
    try:
        return os.path.getmtime(path)
    except (OSError, TypeError):
        return None


def read_stl(path: str) -> np.ndarray:
    """回傳三角形頂點 (3N, 3),檔案單位。"""
    with open(path, "rb") as f:
        raw = f.read()
    if len(raw) >= 84:
        n = struct.unpack("<I", raw[80:84])[0]
        if 84 + 50 * n == len(raw):
            dt = np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
            tri = np.frombuffer(raw, dtype=dt, count=n, offset=84)
            return tri["v"].reshape(-1, 3).astype(float)
    verts = []
    for line in raw.decode("utf-8", errors="replace").splitlines():
        t = line.strip().split()
        if len(t) == 4 and t[0].lower() == "vertex":
            verts.append([float(t[1]), float(t[2]), float(t[3])])
    if not verts:
        raise ValueError("讀不到 STL 的頂點(檔案格式不對?)")
    return np.array(verts, float)


def _parse_layer(layer: str):
    s = str(layer).strip()
    if not s:
        return None, None
    if ":" in s:
        a, b = s.split(":", 1)
        return int(a), int(b)
    return int(s), None


def gds_info(path: str):
    """回傳 {cell 名稱: [(layer, datatype), ...]},第一個是最上層。"""
    import gdstk
    lib = gdstk.read_gds(path)
    tops = lib.top_level()
    cells = tops + [c for c in lib.cells if c not in tops]
    info = {}
    for c in cells:
        ld = sorted({(p.layer, p.datatype) for p in c.get_polygons()})
        info[c.name] = ld
    return info


def gds_polygons(path: str, cell: str, layer: str):
    """多邊形(nm,檔案座標,已展開所有參照)。"""
    import gdstk
    lib = gdstk.read_gds(path)
    scale = lib.unit / 1e-9
    if cell:
        cs = [c for c in lib.cells if c.name == cell]
        if not cs:
            raise ValueError(f"GDS 裡沒有 cell「{cell}」")
        c = cs[0]
    else:
        tops = lib.top_level()
        if not tops:
            raise ValueError("GDS 裡沒有 cell")
        c = tops[0]
    L, D = _parse_layer(layer)
    polys = [q for q in c.get_polygons()
             if L is None or (q.layer == L and (D is None or q.datatype == D))]
    return [[(float(x) * scale, float(y) * scale) for x, y in p.points] for p in polys]


def gds_top_cell(path: str) -> str:
    import gdstk
    lib = gdstk.read_gds(path)
    tops = lib.top_level()
    return tops[0].name if tops else ""


def dxf_layers(path: str):
    import ezdxf
    doc = ezdxf.readfile(path)
    return sorted({e.dxf.layer for e in doc.modelspace()})


def dxf_polygons(path: str, layer: str, unit_nm: float):
    """封閉的 LWPOLYLINE / POLYLINE、CIRCLE、ELLIPSE、SOLID / 3DFACE → 多邊形(nm)。
    有圓弧(bulge)的多段線會切成小線段。"""
    import ezdxf
    from ezdxf import path as ezpath
    doc = ezdxf.readfile(path)
    out = []
    for e in doc.modelspace():
        if layer and e.dxf.layer != layer:
            continue
        t = e.dxftype()
        pts = None
        try:
            if t in ("LWPOLYLINE", "POLYLINE"):
                closed = e.closed if t == "LWPOLYLINE" else e.is_closed
                if not closed:
                    continue
                p = ezpath.make_path(e)
                pts = [(v.x, v.y) for v in p.flattening(distance=0.01)]
            elif t == "CIRCLE":
                c, r = e.dxf.center, e.dxf.radius
                pts = [(c.x + r * math.cos(a), c.y + r * math.sin(a))
                       for a in np.linspace(0, 2 * math.pi, 73)[:-1]]
            elif t == "ELLIPSE":
                p = ezpath.make_path(e)
                pts = [(v.x, v.y) for v in p.flattening(distance=0.01)]
            elif t in ("SOLID", "3DFACE", "TRACE"):
                vs = [e.dxf.get(f"vtx{i}") for i in range(4)]
                vs = [v for v in vs if v is not None]
                pts = [(v[0], v[1]) for v in vs]
                if t != "3DFACE" and len(pts) == 4:     # SOLID 的頂點順序是 1-2-4-3
                    pts = [pts[0], pts[1], pts[3], pts[2]]
        except Exception:  # noqa: BLE001
            continue
        if pts and len(pts) >= 3:
            if pts[0] == pts[-1]:
                pts = pts[:-1]
            out.append([(x * unit_nm, y * unit_nm) for x, y in pts])
    return out
