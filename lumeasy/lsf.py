"""把專案轉成 Lumerical 腳本(LSF)。

每一行指令都獨立送進 Lumerical 執行,失敗時才知道是「哪個物件的哪個設定」錯了
(Lumerical 的 eval 錯誤訊息只有 'Failed to evaluate code')。整份腳本也會存成 .lsf,
可以直接貼進 Lumerical 的腳本視窗重建同一個模型。

2D:使用者畫 x-z 截面;Lumerical 2D 只做 x-y 平面 → 我們的 z 寫成 Lumerical 的 y。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from lumeasy import model as M
from lumeasy import materials as MAT

NM = 1e-9


def q(s: str) -> str:
    return '"' + str(s).replace('"', "'") + '"'


def num(v_nm: float) -> str:
    """nm → 公尺字串。"""
    return f"{float(v_nm) * NM:.10g}"


def fnum(v: float) -> str:
    return f"{float(v):.10g}"


@dataclass
class Stmt:
    label: str          # 給人看的:屬於哪個物件、在做什麼
    code: str
    optional: bool = False   # 失敗只警告(例如舊版 Lumerical 沒有的屬性)


@dataclass
class Script:
    stmts: list[Stmt] = field(default_factory=list)
    checks: list[tuple[str, str, float]] = field(default_factory=list)  # (物件, 屬性, 期望值 SI)
    warnings: list[str] = field(default_factory=list)

    def text(self, header: str = "") -> str:
        out, last = [], None
        if header:
            out += ["# " + h for h in header.splitlines()] + [""]
        for s in self.stmts:
            if s.label != last:
                out += ["", f"# ---- {s.label}"]
                last = s.label
            out.append(s.code)
        return "\n".join(out) + "\n"


class Gen:
    def __init__(self, p: dict):
        self.p = p
        self.d2 = M.is2d(p)
        self.s = Script()
        self.placed = M.place_objects(p)
        self.reg = M.compute_region(p, self.placed)

    # -- helpers ----------------------------------------------------------
    def add(self, label, code, optional=False):
        self.s.stmts.append(Stmt(label, code, optional))

    def setp(self, label, prop, value, optional=False):
        if isinstance(value, str) and not value.startswith("["):
            v = q(value)
        elif isinstance(value, bool):
            v = "1" if value else "0"
        elif isinstance(value, (int, float)):
            v = fnum(value)
        else:
            v = value
        self.add(label, f"set({q(prop)},{v});", optional)

    def setlen(self, label, prop, v_nm, check_obj=None):
        self.add(label, f"set({q(prop)},{num(v_nm)});")
        if check_obj:
            self.s.checks.append((check_obj, prop, float(v_nm) * NM))

    def rspan(self, ax):
        lo, hi = self.reg[ax]
        return hi - lo

    def rcenter(self, ax):
        lo, hi = self.reg[ax]
        return (lo + hi) / 2

    def pos3(self, label, x, y, z, chk=None):
        """在 (x,y,z)(我們的座標)設定中心,2D 時寫成 Lumerical 的 (x, y=z)。"""
        self.setlen(label, "x", x, chk)
        if self.d2:
            self.setlen(label, "y", z, chk and None)
            if chk:
                self.s.checks.append((chk, "y", float(z) * NM))
        else:
            self.setlen(label, "y", y, chk)
            self.setlen(label, "z", z, chk)

    def span(self, label, ax, v_nm, chk=None):
        """ax 是我們的軸;2D 時 z → Lumerical y,y 不存在。"""
        if self.d2:
            if ax == "y":
                return
            lax = "y" if ax == "z" else ax
        else:
            lax = ax
        self.setlen(label, f"{lax} span", v_nm, chk)

    # -- sections ---------------------------------------------------------
    def materials(self):
        g = self.p["global"]
        for m in self.p["materials"]:
            lab = f"材料 {m['name']}"
            name = q(m["name"])
            kind = m.get("kind")
            if kind in ("const_nk", "const_eps"):
                if kind == "const_nk":
                    n, k = float(m.get("n", 1)), float(m.get("k", 0))
                else:
                    n, k = (float(a) for a in MAT.eps_to_nk(float(m.get("e1", 1)), float(m.get("e2", 0))))
                self.add(lab, 'lemat = addmaterial("(n,k) Material");')
                self.add(lab, f'setmaterial(lemat,"name",{name});')
                self.add(lab, f'setmaterial({name},"Refractive Index",{fnum(n)});')
                self.add(lab, f'setmaterial({name},"Imaginary Refractive Index",{fnum(k)});')
            elif kind == "file":
                wl = np.asarray(m["wl_nm"], float)
                n, k = np.asarray(m["n"], float), np.asarray(m["k"], float)
                e1, e2 = MAT.nk_to_eps(n, k)
                f = MAT.wl_nm_to_hz(wl)
                o = np.argsort(f)
                fs = ";".join(f"{v:.10g}" for v in f[o])
                es = ";".join(f"{a:.10g}{b:+.10g}i" for a, b in zip(e1[o], e2[o]))
                self.add(lab, 'lemat = addmaterial("Sampled 3D data");')
                self.add(lab, f'setmaterial(lemat,"name",{name});')
                self.add(lab, f"lemf = [{fs}];")
                self.add(lab, f"leme = [{es}];")
                self.add(lab, f'setmaterial({name},"sampled data",[lemf,leme]);')
                lo, hi = float(wl.min()), float(wl.max())
                if g["wl_start"] < lo - 1e-6 or g["wl_stop"] > hi + 1e-6:
                    self.s.warnings.append(
                        f"材料 {m['name']} 的資料只涵蓋 {lo:.0f}–{hi:.0f} nm,模擬波長 "
                        f"{g['wl_start']:.0f}–{g['wl_stop']:.0f} nm 超出範圍的部分 Lumerical 會自己外插。")
            elif kind == "builtin_copy":
                base = m.get("base", "")
                self.add(lab, f"lemat = copymaterial({q(base)});")
                self.add(lab, f'setmaterial(lemat,"name",{name});')
            else:
                continue
            if kind in ("file", "builtin_copy"):
                if float(m.get("fit_tol") or 0) > 0:
                    self.add(lab, f'setmaterial({name},"tolerance",{fnum(m["fit_tol"])});', True)
                if int(m.get("max_coef") or 0) > 0:
                    self.add(lab, f'setmaterial({name},"max coefficients",{int(m["max_coef"])});', True)
            if m.get("color"):
                r, gg, b, a = MAT.hex_rgba(m["color"], float(m.get("alpha", 1.0)))
                self.add(lab, f'setmaterial({name},"color",[{r:.4g},{gg:.4g},{b:.4g},{a:.4g}]);', True)

    def region(self):
        r = self.p["region"]
        lab = "FDTD 模擬區"
        self.add(lab, "addfdtd;")
        self.setp(lab, "dimension", "2D" if self.d2 else "3D")
        self.setlen(lab, "x", self.rcenter("x"), "FDTD")
        self.setlen(lab, "x span", self.rspan("x"), "FDTD")
        if self.d2:
            self.setlen(lab, "y", self.rcenter("z"), "FDTD")
            self.setlen(lab, "y span", self.rspan("z"), "FDTD")
        else:
            for ax in ("y", "z"):
                self.setlen(lab, ax, self.rcenter(ax), "FDTD")
                self.setlen(lab, f"{ax} span", self.rspan(ax), "FDTD")
        self.setp(lab, "simulation time", float(r["sim_time"]) * 1e-15)
        self.setp(lab, "mesh accuracy", int(r["mesh_acc"]))
        self.setp(lab, "index", float(r["bg_index"]))
        self.setp(lab, "auto shutoff min", float(r["shutoff"]))
        self.setp(lab, "pml type", r["pml_type"], optional=True)
        self.setp(lab, "pml layers", int(r["pml_layers"]), optional=True)
        if float(r.get("min_mesh") or 0) > 0:
            self.setp(lab, "min mesh step", float(r["min_mesh"]) * NM)

        def bc_axis(lax, choice):
            if choice in ("PML", "Metal", "PMC"):
                self.setp(lab, f"{lax} min bc", choice)
                self.setp(lab, f"{lax} max bc", choice)
            elif choice in ("Periodic", "Bloch"):
                self.setp(lab, f"{lax} min bc", choice)
            else:  # Symmetric / Anti-Symmetric:對稱面在模擬區中心
                self.setp(lab, f"{lax} min bc", choice)
        bc_axis("x", r["bc_x"])
        if self.d2:
            zl = "y"
        else:
            bc_axis("y", r["bc_y"])
            zl = "z"
        zmin, zmax = r["bc_zmin"], r["bc_zmax"]
        if zmin in ("Periodic", "Bloch") or zmax in ("Periodic", "Bloch"):
            self.setp(lab, f"{zl} min bc", zmin if zmin in ("Periodic", "Bloch") else zmax)
        else:
            self.setp(lab, f"{zl} min bc", zmin)
            self.setp(lab, f"{zl} max bc", zmax)
        bcs = [r["bc_x"], zmin, zmax] + ([] if self.d2 else [r["bc_y"]])
        if "Bloch" in bcs:
            self.setp(lab, "set based on source angle", 1, optional=True)

    def _common_obj(self, lab, obj, nm):
        mat = obj.get("material") or "etch"
        self.setp(lab, "material", mat)
        if float(obj.get("rot") or 0):
            self.setp(lab, "first axis", "z")
            self.setp(lab, "rotation 1", float(obj["rot"]))
        mo = int(obj.get("mesh_order") or 2)
        if mo != 2:
            self.setp(lab, "override mesh order from material database", 1)
            self.setp(lab, "mesh order", mo)

    def _rect(self, lab, nm, cx, cy, Lx, Ly, z0, H, obj):
        self.add(lab, "addrect;")
        self.setp(lab, "name", nm)
        self.setlen(lab, "x", cx, nm)
        self.setlen(lab, "x span", Lx, nm)
        if self.d2:
            self.setlen(lab, "y", z0 + H / 2, nm)
            self.setlen(lab, "y span", H, nm)
        else:
            self.setlen(lab, "y", cy, nm)
            self.setlen(lab, "y span", Ly, nm)
            self.setlen(lab, "z", z0 + H / 2, nm)
            self.setlen(lab, "z span", H, nm)
        self._common_obj(lab, obj, nm)

    def _poly(self, lab, nm, ox, oy, z0, H, pts, obj):
        self.add(lab, "addpoly;")
        self.setp(lab, "name", nm)
        self.setlen(lab, "x", ox, nm)
        if self.d2:
            self.setlen(lab, "y", z0, nm)
        else:
            self.setlen(lab, "y", oy, nm)
            self.setlen(lab, "z", z0 + H / 2, nm)
            self.setlen(lab, "z span", H, nm)
        v = ";".join(f"{num(x)},{num(y)}" for x, y in pts)
        self.add(lab, f'set("vertices",[{v}]);')
        self._common_obj(lab, obj, nm)

    def objects(self):
        rx, ry = self.reg["x"], self.reg["y"]
        for r in self.placed:
            obj = r["obj"]
            if not r["enabled"]:
                continue
            if r["error"]:
                raise ValueError(r["error"])
            lab = f"物件 {obj['name']}({M.SHAPES[obj['shape']]['label']})"
            sh, d, kind = r["shift"], r["data"], r["kind"]
            names = M.copy_names(obj, r["nx"], r["ny"])
            c0 = r["copies"][0]
            bx, by, bz = sh[0] + c0[0], sh[1] + c0[1], sh[2]   # 第一個複本的原生原點
            base_names = []
            s = obj["shape"]
            if kind == "rect":
                Lx, Ly = d["Lx"], d["Ly"]
                cx, cy = bx, by
                if r["through"]:
                    Lx = 2 * (rx[1] - rx[0]) + 4000
                    cx = (rx[0] + rx[1]) / 2
                    if not self.d2:
                        Ly = 2 * (ry[1] - ry[0]) + 4000
                        cy = (ry[0] + ry[1]) / 2
                self._rect(lab, names[0], cx, cy, Lx, Ly, bz, d["H"], obj)
                base_names = [names[0]]
            elif kind in ("circle", "ellipse"):
                rxx = d["r"] if kind == "circle" else d["rx"]
                if self.d2:
                    self._rect(lab, names[0], bx, 0, 2 * rxx, 0, bz, d["H"], obj)
                else:
                    self.add(lab, "addcircle;")
                    self.setp(lab, "name", names[0])
                    self.setlen(lab, "x", bx, names[0])
                    self.setlen(lab, "y", by, names[0])
                    self.setlen(lab, "z", bz + d["H"] / 2, names[0])
                    self.setlen(lab, "z span", d["H"], names[0])
                    if kind == "ellipse":
                        self.setp(lab, "make ellipsoid", 1)
                        self.setlen(lab, "radius", d["rx"])
                        self.setlen(lab, "radius 2", d["ry"])
                    else:
                        self.setlen(lab, "radius", d["r"], names[0])
                    self._common_obj(lab, obj, names[0])
                base_names = [names[0]]
            elif kind == "ring":
                if self.d2:
                    w = d["ro"] - d["ri"]
                    c = (d["ro"] + d["ri"]) / 2
                    na, nb = names[0] + "_L", names[0] + "_R"
                    self._rect(lab, na, bx - c, 0, w, 0, bz, d["H"], obj)
                    self._rect(lab, nb, bx + c, 0, w, 0, bz, d["H"], obj)
                    base_names = [na, nb]
                else:
                    self.add(lab, "addring;")
                    self.setp(lab, "name", names[0])
                    self.setlen(lab, "x", bx, names[0])
                    self.setlen(lab, "y", by, names[0])
                    self.setlen(lab, "z", bz + d["H"] / 2, names[0])
                    self.setlen(lab, "z span", d["H"], names[0])
                    self.setlen(lab, "outer radius", d["ro"])
                    self.setlen(lab, "inner radius", d["ri"])
                    self.setp(lab, "theta start", d["t0"])
                    self.setp(lab, "theta stop", d["t1"])
                    self._common_obj(lab, obj, names[0])
                    base_names = [names[0]]
            elif kind == "sphere":
                if self.d2:
                    self.add(lab, "addcircle;")
                    self.setp(lab, "name", names[0])
                    self.setlen(lab, "x", bx, names[0])
                    self.setlen(lab, "y", bz + d["r"], names[0])
                    self.setlen(lab, "radius", d["r"], names[0])
                else:
                    self.add(lab, "addsphere;")
                    self.setp(lab, "name", names[0])
                    self.setlen(lab, "x", bx, names[0])
                    self.setlen(lab, "y", by, names[0])
                    self.setlen(lab, "z", bz + d["r"], names[0])
                    self.setlen(lab, "radius", d["r"], names[0])
                self._common_obj(lab, obj, names[0])
                base_names = [names[0]]
            elif kind == "pyramid":
                if self.d2:
                    H = d["H"]
                    pts = [(-d["Lx0"] / 2, 0), (d["Lx0"] / 2, 0), (d["Lx1"] / 2, H), (-d["Lx1"] / 2, H)]
                    self._poly(lab, names[0], bx, 0, bz, 0, pts, obj)
                else:
                    self.add(lab, "addpyramid;")
                    self.setp(lab, "name", names[0])
                    self.setlen(lab, "x", bx, names[0])
                    self.setlen(lab, "y", by, names[0])
                    self.setlen(lab, "z", bz + d["H"] / 2, names[0])
                    self.setlen(lab, "z span", d["H"], names[0])
                    self.setlen(lab, "x span bottom", d["Lx0"])
                    self.setlen(lab, "y span bottom", d["Ly0"])
                    self.setlen(lab, "x span top", d["Lx1"])
                    self.setlen(lab, "y span top", d["Ly1"])
                    self._common_obj(lab, obj, names[0])
                base_names = [names[0]]
            elif kind == "poly":
                self._poly(lab, names[0], bx, by, bz, d["H"], d["pts"], obj)
                base_names = [names[0]]
            elif kind == "stl":
                if self.d2:
                    raise ValueError(f"{obj['name']}:STL 是 3D 立體,2D 模擬不能用(2D 請用多邊形、GDS 或 DXF 畫截面)")
                path = str(obj["file"]).replace("\\", "/")
                scale = M.FILE_UNIT_NM[obj.get("file_unit", "um")] * NM
                self.add(lab, f"stlimport({q(path)},{scale:.10g});")
                self.setp(lab, "name", names[0])
                self.setp(lab, "material", obj.get("material") or "etch")
                self.setlen(lab, "x", sh[0], names[0])
                self.setlen(lab, "y", sh[1], names[0])
                self.setlen(lab, "z", sh[2], names[0])
                if float(obj.get("rot") or 0):
                    self.setp(lab, "first axis", "z")
                    self.setp(lab, "rotation 1", float(obj["rot"]))
                continue
            elif kind == "polys" and s == "gds":
                from lumeasy import cadio
                path = str(obj["file"]).replace("\\", "/")
                cell = obj.get("cell") or cadio.gds_top_cell(obj["file"])
                layer = str(obj.get("layer", "1")).strip()
                lay = q(layer) if ":" in layer else str(int(layer))
                if self.d2:
                    z0, z1 = -500.0, 500.0
                else:
                    z0, z1 = sh[2], sh[2] + d["H"]
                self.add(lab, f"gdsimport({q(path)},{q(cell)},{lay},{q(obj.get('material') or 'etch')},{num(z0)},{num(z1)});")
                self.setp(lab, "name", names[0])
                self.setlen(lab, "x", sh[0], names[0])
                if self.d2:
                    self.setlen(lab, "y", sh[2], names[0])
                else:
                    self.setlen(lab, "y", sh[1], names[0])
                if float(obj.get("rot") or 0):
                    self.setp(lab, "first axis", "z")
                    self.setp(lab, "rotation 1", float(obj["rot"]))
                continue
            elif kind == "polys":   # DXF
                for k, poly in enumerate(d["polys"]):
                    self._poly(lab, f"{obj['name']}_{k + 1}", sh[0], sh[1], sh[2], d["H"], poly, obj)
                continue
            # 陣列:第一個建好後在 Lumerical 裡用迴圈複製(上萬個也很快)
            nx, ny = r["nx"], r["ny"]
            if nx * ny > 1:
                px, py = float(obj.get("px") or 0), float(obj.get("py") or 0)
                for b in base_names:
                    root = b[:-len("_0_0")] if b.endswith("_0_0") else (b[:-2] if b.endswith("_0") else b)
                    suffix = ""
                    if b.endswith("_L") or b.endswith("_R"):   # 2D 圓環的兩半
                        root, suffix = b[:-2], b[-2:]
                        root = root[:-len("_0_0")] if root.endswith("_0_0") else (root[:-2] if root.endswith("_0") else root)
                    if ny == 1:
                        nm_expr = f'"{root}_"+num2str(ci)+"{suffix}"'
                    else:
                        nm_expr = f'"{root}_"+num2str(ci)+"_"+num2str(cj)+"{suffix}"'
                    dy_expr = "0" if self.d2 else f"cj*{num(py)}"
                    self.add(lab, f"for(ci=0:{nx - 1}){{ for(cj=0:{ny - 1}){{ if(ci+cj>0){{ "
                                  f"select({q(b)}); copy(ci*{num(px)},{dy_expr}); set(\"name\",{nm_expr}); }} }} }}")
                if nx * ny > 5000:
                    self.s.warnings.append(f"{obj['name']} 有 {nx * ny} 個複本,Lumerical 建模和網格化會比較久。")

    def mesh(self):
        bbs = {r["obj"]["name"]: r["bbox"] for r in self.placed if r["enabled"] and not r["error"]}
        for m in self.p["mesh"]:
            if not m.get("enabled", True):
                continue
            lab = f"網格覆寫 {m['name']}"
            t = (m.get("target") or "").strip()
            if t:
                if t not in bbs:
                    raise ValueError(f"網格覆寫 {m['name']}:找不到物件「{t}」")
                b, buf = bbs[t], float(m.get("buffer") or 0)
                cx, cy, cz = (b[0] + b[1]) / 2, (b[2] + b[3]) / 2, (b[4] + b[5]) / 2
                sx, sy, sz = b[1] - b[0] + 2 * buf, b[3] - b[2] + 2 * buf, b[5] - b[4] + 2 * buf
            else:
                cx, cy, cz = (float(m[k]) for k in ("x", "y", "z"))
                sx, sy, sz = (float(m[k]) for k in ("sx", "sy", "sz"))
            self.add(lab, "addmesh;")
            self.setp(lab, "name", m["name"])
            self.pos3(lab, cx, cy, cz)
            self.span(lab, "x", sx)
            self.span(lab, "y", sy)
            self.span(lab, "z", sz)
            self.setp(lab, "override x mesh", 1)
            self.setlen(lab, "dx", float(m["dx"]))
            if self.d2:
                self.setp(lab, "override y mesh", 1)
                self.setlen(lab, "dy", float(m["dz"]))
            else:
                self.setp(lab, "override y mesh", 1)
                self.setlen(lab, "dy", float(m["dy"]))
                self.setp(lab, "override z mesh", 1)
                self.setlen(lab, "dz", float(m["dz"]))

    def globals_(self):
        g = self.p["global"]
        lab = "全域波長與頻率點"
        self.add(lab, f'setglobalsource("wavelength start",{fnum(float(g["wl_start"]) * NM)});')
        self.add(lab, f'setglobalsource("wavelength stop",{fnum(float(g["wl_stop"]) * NM)});')
        self.add(lab, f'setglobalmonitor("frequency points",{int(g["fpoints"])});')

    def _lax(self, ax):
        """我們的注入軸 → Lumerical 的 injection axis。"""
        if self.d2:
            if ax == "y":
                raise ValueError("2D 模擬沒有 y 方向(2D 是 x-z 截面),注入軸請選 x 或 z")
            return "y-axis" if ax == "z" else "x-axis"
        return f"{ax}-axis"

    def _src_span(self, lab, s, ax_inj, extra):
        for ax in ("x", "y", "z"):
            if ax == ax_inj:
                continue
            v = s.get("s" + ax)
            self.span(lab, ax, float(v) if v not in (None, "") else self.rspan(ax) + extra)

    def _pol_2d(self, s):
        """2D 偏振:回 Lumerical 的 polarization angle。
        Lumerical 2D(x-y 平面)y 注入時:0° = E 在面內(我們的 TM / p)、90° = E 沿 Lumerical z(我們的 y,TE / s)。"""
        return 90.0 if s.get("pol2d", "TE") == "TE" else 0.0

    def _theta(self, s):
        """Lumerical 的 θ 是把 k 繞 z 軸逆時針轉,實測(2020 R2,kx/k0 = ±sin θ):
             3D z 注入:往下(Backward)θ>0 → −x,往上 → +x
             2D y 注入:往下 θ>0 → +x,往上 → −x
           統一成「垂直注入時 θ > 0 = 光往 +x 偏」。x 方向注入照 Lumerical 原本的定義。"""
        th = float(s.get("theta") or 0)
        if s.get("axis") == "z":
            down = s.get("direction") != "pos"
            if (down and not self.d2) or (not down and self.d2):
                th = -th
        return th

    def _dipole_angles(self, s):
        th, ph = math.radians(float(s.get("theta") or 0)), math.radians(float(s.get("phi") or 0))
        d = (math.sin(th) * math.cos(ph), math.sin(th) * math.sin(ph), math.cos(th))
        if not self.d2:
            return float(s.get("theta") or 0), float(s.get("phi") or 0)
        L = (d[0], d[2], d[1])   # 我們的 (x, y, z) → Lumerical (x, z→y, y→z)
        return math.degrees(math.acos(max(-1, min(1, L[2])))), math.degrees(math.atan2(L[1], L[0]))

    def sources(self):
        for s in self.p["sources"]:
            if not s.get("enabled", True):
                continue
            t = s["type"]
            lab = f"光源 {s['name']}({M.SOURCE_TYPES[t]['label']})"
            cmd = {"planewave": "addplane", "gaussian": "addgaussian", "mode": "addmode",
                   "dipole": "adddipole", "tfsf": "addtfsf"}[t]
            self.add(lab, f"{cmd};")
            self.setp(lab, "name", s["name"])
            self.pos3(lab, float(s["x"]), float(s.get("y") or 0), float(s["z"]))
            if t == "dipole":
                self.setp(lab, "dipole type", s["dtype"])
                th, ph = self._dipole_angles(s)
                self.setp(lab, "theta", th)
                self.setp(lab, "phi", ph)
                continue
            ax = s.get("axis", "z")
            self.setp(lab, "injection axis", self._lax(ax))
            self.setp(lab, "direction", "Forward" if s.get("direction") == "pos" else "Backward")
            if t == "mode":
                self._src_span(lab, s, ax, 0.0)
                self.setp(lab, "mode selection", s["mode"])
                if s["mode"] == "user select":
                    self.setp(lab, "selected mode number", int(s.get("mode_num") or 1))
                continue
            if t == "tfsf":
                for a2 in ("x", "y", "z"):
                    v = s.get("s" + a2)
                    self.span(lab, a2, float(v) if v not in (None, "") else 0.6 * self.rspan(a2))
            else:
                self._src_span(lab, s, ax, 2000.0)
            if t == "planewave":
                self.setp(lab, "plane wave type", s.get("pwtype", "Bloch/periodic"))
            if t == "gaussian":
                self.setlen(lab, "waist radius w0", float(s["w0"]))
                self.setlen(lab, "distance from waist", float(s.get("focus") or 0))
            self.setp(lab, "polarization angle", self._pol_2d(s) if self.d2 else float(s.get("pol") or 0))
            self.setp(lab, "angle theta", self._theta(s))
            if not self.d2 and t != "tfsf":
                self.setp(lab, "angle phi", float(s.get("phi") or 0))

    MON_CMD = {"power": "addpower", "profile": "addprofile", "index": "addindex",
               "time": "addtime", "movie": "addmovie"}

    def mon_type(self, orient):
        if not self.d2:
            return {"z": "2D Z-normal", "x": "2D X-normal", "y": "2D Y-normal", "point": "Point",
                    "lx": "Linear X", "ly": "Linear Y", "lz": "Linear Z", "3d": "3D"}[orient]
        t = {"z": "Linear X", "x": "Linear Y", "y": "2D Z-normal", "point": "Point",
             "lx": "Linear X", "lz": "Linear Y", "3d": "2D Z-normal"}.get(orient)
        if t is None:
            raise ValueError("2D 模擬沒有 y 方向,不能放沿 y 的線監視器")
        return t

    def mon_axes(self, orient):
        """這個方向的監視器要設哪些(我們的)範圍軸。"""
        return {"z": "xy", "x": "yz", "y": "xz", "point": "", "lx": "x", "ly": "y", "lz": "z",
                "3d": "xyz"}[orient]

    def monitors(self):
        for m in self.p["monitors"]:
            if not m.get("enabled", True):
                continue
            kind, orient = m["kind"], m["orient"]
            lab = f"監視器 {m['name']}"
            if kind == "movie" and orient not in ("x", "y", "z"):
                raise ValueError(f"監視器 {m['name']}:動畫監視器只能是平面")
            self.add(lab, f"{self.MON_CMD[kind]};")
            self.setp(lab, "name", m["name"])
            self.setp(lab, "monitor type", self.mon_type(orient))
            self.pos3(lab, float(m["x"]), float(m.get("y") or 0), float(m["z"]))
            for ax in self.mon_axes(orient):
                v = m.get("s" + ax)
                self.span(lab, ax, float(v) if v not in (None, "") else self.rspan(ax))
            if kind in ("power", "profile", "time"):
                outs = set(m.get("outputs") or [])
                for c in M.FIELD_OUTPUTS:
                    self.setp(lab, f"output {c}", 1 if c in outs else 0, optional=True)
            if kind in ("power", "profile", "index") and int(m.get("fpoints") or 0) > 0:
                self.setp(lab, "override global monitor settings", 1)
                self.setp(lab, "frequency points", int(m["fpoints"]))
            if kind == "movie":
                self.setp(lab, "field component", m.get("movie_comp", "Ey"), optional=True)
            ds = int(m.get("downsample") or 1)
            if ds > 1 and kind != "movie":
                for ax in self.mon_axes(orient):      # 只有面內方向能降取樣
                    if self.d2 and ax == "y":
                        continue
                    lax = ("Y" if ax == "z" else ax.upper()) if self.d2 else ax.upper()
                    self.setp(lab, f"down sample {lax}", ds, optional=True)

    def build(self, fsp_path: str | None = None) -> Script:
        self.materials()
        self.region()
        self.objects()
        self.mesh()
        self.globals_()
        self.sources()
        self.monitors()
        if fsp_path:
            self.add("存檔", f"save({q(fsp_path.replace(chr(92), '/'))});")
        return self.s


def generate(p: dict, fsp_path: str | None = None) -> Script:
    return Gen(p).build(fsp_path)


# --------------------------------------------------------------------------
# 檢查(建模前):錯誤擋下來,警告只提醒
# --------------------------------------------------------------------------

def validate(p: dict, builtin_names: list[str] | None = None) -> list[tuple[str, str]]:
    out = []
    d2 = M.is2d(p)
    g = p["global"]
    if not p["project"].get("name"):
        out.append(("error", "專案名稱是空的"))
    if float(g["wl_start"]) >= float(g["wl_stop"]):
        out.append(("error", "波長起點要小於終點"))
    custom = {m["name"] for m in p["materials"]}
    names = []
    try:
        names = M.all_names(p)
    except Exception as e:  # noqa: BLE001
        out.append(("error", str(e)))
    dup = sorted({n for n in names if names.count(n) > 1})
    if dup:
        out.append(("error", "名稱重複:" + "、".join(dup)))
    if "FDTD" in names:
        out.append(("error", "名稱 FDTD 是 Lumerical 模擬區保留的,請換一個"))
    for n in names + list(custom):
        if '"' in n:
            out.append(("error", f"名稱「{n}」不能有雙引號"))
    if builtin_names:
        clash = custom & set(builtin_names)
        if clash:
            out.append(("error", "自訂材料不能和 Lumerical 內建材料同名:" + "、".join(sorted(clash))))
    placed = M.place_objects(p)
    for r in placed:
        o = r["obj"]
        if not r["enabled"]:
            continue
        if r["error"]:
            out.append(("error", r["error"]))
            continue
        mat = o.get("material") or ""
        if mat not in custom and mat != "etch" and builtin_names and mat not in builtin_names:
            out.append(("error", f"物件 {o['name']}:材料「{mat}」不存在(內建清單沒有,也不是自訂材料)"))
        if d2 and o["shape"] == "stl":
            out.append(("error", f"物件 {o['name']}:2D 模擬不能用 STL"))
        sz = r["bbox"]
        if (sz[1] - sz[0]) <= 0 or (not d2 and (sz[3] - sz[2]) <= 0) or (sz[5] - sz[4]) <= 0:
            if o["shape"] != "polygon" or not d2:
                out.append(("warn", f"物件 {o['name']}:有一個方向的尺寸是 0"))
        if o["shape"] == "ring" and float(o.get("r_in", 0)) >= float(o.get("r_out", 0)):
            out.append(("error", f"物件 {o['name']}:內半徑要小於外半徑"))
    reg = M.compute_region(p, placed)
    for ax in ("x", "z") if d2 else ("x", "y", "z"):
        if reg[ax][1] - reg[ax][0] <= 0:
            out.append(("error", f"模擬區 {ax} 範圍是 0"))
    if not any(s.get("enabled", True) for s in p["sources"]):
        out.append(("warn", "還沒有光源(只建模型可以,執行模擬一定要有)"))
    if not any(m.get("enabled", True) for m in p["monitors"]):
        out.append(("warn", "還沒有監視器(跑完會沒有資料)"))

    def inside(x, y, z):
        ok = reg["x"][0] - 1e-6 <= x <= reg["x"][1] + 1e-6 and reg["z"][0] - 1e-6 <= z <= reg["z"][1] + 1e-6
        if not d2:
            ok = ok and reg["y"][0] - 1e-6 <= y <= reg["y"][1] + 1e-6
        return ok
    for s in p["sources"]:
        if s.get("enabled", True) and not inside(float(s["x"]), float(s.get("y") or 0), float(s["z"])):
            out.append(("warn", f"光源 {s['name']} 的中心在模擬區外面"))
        if d2 and s.get("axis") == "y" and s["type"] != "dipole":
            out.append(("error", f"光源 {s['name']}:2D 沒有 y 方向,注入軸請選 x 或 z"))
        if s["type"] == "mode" and p["region"]["bc_y" if not d2 else "bc_x"] in ("Symmetric", "Anti-Symmetric"):
            out.append(("warn", f"光源 {s['name']}:模態光源搭配對稱邊界時,Lumerical 2020 R2 的模態解算區會被切掉一截,"
                                "可能找到假模態;建議改全 PML。"))
    for m in p["monitors"]:
        if m.get("enabled", True) and not inside(float(m["x"]), float(m.get("y") or 0), float(m["z"])):
            out.append(("warn", f"監視器 {m['name']} 的中心在模擬區外面(Lumerical 會截到模擬區裡面)"))
        if d2 and m["orient"] == "ly":
            out.append(("error", f"監視器 {m['name']}:2D 沒有 y 方向"))
    try:
        sc = generate(p)
        out += [("warn", w) for w in sc.warnings]
    except Exception as e:  # noqa: BLE001
        out.append(("error", str(e)))
    return out
