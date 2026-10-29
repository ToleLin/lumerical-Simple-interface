"""右側預覽:用 matplotlib 畫俯視 XY、側視 XZ、YZ(2D 只畫 XZ),含模擬區、光源、監視器。"""
from __future__ import annotations

import math

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from matplotlib.patches import Circle, Ellipse, Polygon, Rectangle, Wedge
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from lumeasy import materials as MAT
from lumeasy import model as M

MON_COLOR = {"power": "#1f77b4", "profile": "#2ca02c", "index": "#9467bd", "time": "#7f7f7f", "movie": "#8c564b"}


def mat_color(p, name):
    for m in p["materials"]:
        if m["name"] == name and m.get("color"):
            return m["color"]
    return MAT.builtin_color(name or "etch")


def _rot(pts, deg, c):
    if not deg:
        return pts
    a = math.radians(deg)
    ca, sa = math.cos(a), math.sin(a)
    return [(c[0] + (x - c[0]) * ca - (y - c[1]) * sa, c[1] + (x - c[0]) * sa + (y - c[1]) * ca) for x, y in pts]


class Preview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        top.setContentsMargins(8, 6, 8, 0)
        t = QLabel("預覽")
        t.setObjectName("previewTitle")
        top.addWidget(t)
        top.addStretch(1)
        self.cb_region = QCheckBox("模擬區")
        self.cb_src = QCheckBox("光源")
        self.cb_mon = QCheckBox("監視器")
        tips = {self.cb_region: "橘色虛線框 = FDTD 模擬區", self.cb_src: "紅線 + 箭頭 = 光源位置與傳播方向",
                self.cb_mon: "藍 / 綠 / 紫 = 監視器(功率 / 場剖面 / 折射率)"}
        for c in (self.cb_region, self.cb_src, self.cb_mon):
            c.setChecked(True)
            c.setToolTip(tips[c])
            c.toggled.connect(lambda _=None: self.redraw())
            top.addWidget(c)
        from PySide6.QtWidgets import QPushButton
        zb = QPushButton("放大檢視")
        zb.setObjectName("flat")
        zb.setToolTip("開一個大視窗,可以放大、平移、存成圖片。")
        zb.clicked.connect(self.zoom_window)
        top.addWidget(zb)
        v.addLayout(top)
        self.fig = Figure(figsize=(5, 7), dpi=95)
        self.fig.patch.set_facecolor("#ffffff")
        self.canvas = FigureCanvasQTAgg(self.fig)
        self.canvas.setToolTip("俯視 = 從上往下看;側視 = 從前面 / 右邊看。紅框 = 目前選到的物件,虛線白色 = 挖孔。")
        v.addWidget(self.canvas, 1)
        self.info = QLabel("")
        self.info.setWordWrap(True)
        self.info.setObjectName("previewInfo")
        v.addWidget(self.info)
        self.p = None
        self.selected = None
        from lumeasy.results import _cjk_font
        import matplotlib.pyplot as plt
        _cjk_font(plt)
        import matplotlib
        matplotlib.rcParams.update({"font.sans-serif": plt.rcParams["font.sans-serif"], "axes.unicode_minus": False})

    def set_project(self, p, selected=None):
        self.p = p
        self.selected = selected
        self.redraw()

    # ------------------------------------------------------------------
    def zoom_window(self):
        from PySide6.QtWidgets import QDialog
        d = QDialog(self)
        d.setWindowTitle("預覽(放大檢視)")
        d.resize(1100, 900)
        lay = QVBoxLayout(d)
        fig = Figure(figsize=(9, 9), dpi=100)
        can = FigureCanvasQTAgg(fig)
        lay.addWidget(NavigationToolbar2QT(can, d))
        lay.addWidget(can, 1)
        self._render(fig)
        can.draw()
        d.show()

    def redraw(self):
        self._render(self.fig)
        self.canvas.draw_idle()

    def _render(self, fig):
        p = self.p
        fig.clear()
        if p is None:
            return
        d2 = M.is2d(p)
        unit = p["project"].get("unit", "nm")
        s = 1.0 / M.UNIT_NM[unit]
        ul = "nm" if unit == "nm" else "µm"
        try:
            placed = M.place_objects(p)
            reg = M.compute_region(p, placed)
        except Exception as e:  # noqa: BLE001
            self.info.setText(f"預覽錯誤:{e}")
            return
        if d2:
            views = [("xz", fig.add_subplot(111))]
        else:
            gs = fig.add_gridspec(2, 2, height_ratios=[1.15, 1])
            views = [("xy", fig.add_subplot(gs[0, :])), ("xz", fig.add_subplot(gs[1, 0])),
                     ("yz", fig.add_subplot(gs[1, 1]))]
        for view, ax in views:
            self._draw_view(ax, view, p, placed, reg, s)
            a, b = view[0], view[1]
            ax.set_xlabel(f"{a} ({ul})", fontsize=8)
            ax.set_ylabel(f"{b} ({ul})", fontsize=8)
            ax.tick_params(labelsize=7)
            ax.set_title({"xy": "俯視 XY(由上往下看)", "xz": "側視 XZ(從前面看)" if not d2 else "x-z 截面(2D)",
                          "yz": "側視 YZ(從右邊看)"}[view], fontsize=9)
            ax.set_aspect("equal", adjustable="box")
            ax.axhline(0, color="#999", lw=0.5, zorder=0)
            ax.axvline(0, color="#999", lw=0.5, zorder=0)
        fig.tight_layout(pad=0.6)
        errs = [r["error"] for r in placed if r["error"] and r["enabled"]]
        rr = reg
        txt = (f"模擬區 x {rr['x'][0] * s:.4g} … {rr['x'][1] * s:.4g}" +
               ("" if d2 else f",y {rr['y'][0] * s:.4g} … {rr['y'][1] * s:.4g}") +
               f",z {rr['z'][0] * s:.4g} … {rr['z'][1] * s:.4g} {ul}")
        if errs:
            txt += "<br><span style='color:#c00'>" + "<br>".join(errs[:4]) + "</span>"
        self.info.setText(txt)

    def _draw_view(self, ax, view, p, placed, reg, s):
        h, v = view[0], view[1]
        rng = {"x": reg["x"], "y": reg["y"], "z": reg["z"]}
        for r in placed:
            if not r["enabled"] or r["error"]:
                continue
            obj = r["obj"]
            col = mat_color(p, obj.get("material"))
            etch = obj.get("material") == "etch"
            sel = obj.get("name") == self.selected
            kw = dict(facecolor="white" if etch else col, edgecolor="#d62728" if sel else ("#555" if etch else "#333"),
                      lw=1.8 if sel else 0.6, alpha=0.95 if etch else 0.75, ls="--" if etch else "-",
                      zorder=3 if etch or int(obj.get("mesh_order") or 2) < 2 else 2)
            copies = r["copies"] if len(r["copies"]) <= 400 else None
            if copies is None:
                b = r["bbox"]
                i = {"x": 0, "y": 2, "z": 4}
                ax.add_patch(Rectangle((b[i[h]] * s, b[i[v]] * s), (b[i[h] + 1] - b[i[h]]) * s,
                                       (b[i[v] + 1] - b[i[v]]) * s, hatch="//", **kw))
                continue
            for c in copies:
                for patch in self._shape_patches(r, view, c, reg, s, kw):
                    ax.add_patch(patch)
        if self.cb_region.isChecked():
            x0, x1 = rng[h]
            y0, y1 = rng[v]
            ax.add_patch(Rectangle((x0 * s, y0 * s), (x1 - x0) * s, (y1 - y0) * s, fill=False,
                                   edgecolor="#ff7f0e", lw=1.4, ls="--", zorder=5))
        if self.cb_src.isChecked():
            for src in p["sources"]:
                if src.get("enabled", True):
                    self._draw_source(ax, view, src, reg, s, p)
        if self.cb_mon.isChecked():
            for m in p["monitors"]:
                if m.get("enabled", True):
                    self._draw_monitor(ax, view, m, reg, s, p)
        x0, x1 = rng[h]
        y0, y1 = rng[v]
        if h == "y" and M.is2d(p):
            x0, x1 = -1, 1
        padx, pady = 0.08 * (x1 - x0 or 1), 0.08 * (y1 - y0 or 1)
        ax.set_xlim((x0 - padx) * s, (x1 + padx) * s)
        ax.set_ylim((y0 - pady) * s, (y1 + pady) * s)

    def _shape_patches(self, r, view, c, reg, s, kw):
        obj, kind, d, sh = r["obj"], r["kind"], r["data"], r["shift"]
        ox, oy, oz = sh[0] + c[0], sh[1] + c[1], sh[2]
        rot = float(obj.get("rot") or 0)
        lb = r["local"]
        out = []
        if view == "xy":
            if kind == "rect":
                Lx, Ly, cx, cy = d["Lx"], d["Ly"], ox, oy
                if r["through"]:
                    Lx, Ly = 3 * (reg["x"][1] - reg["x"][0]), 3 * (reg["y"][1] - reg["y"][0])
                    cx, cy = sum(reg["x"]) / 2, sum(reg["y"]) / 2
                pts = [(cx - Lx / 2, cy - Ly / 2), (cx + Lx / 2, cy - Ly / 2), (cx + Lx / 2, cy + Ly / 2), (cx - Lx / 2, cy + Ly / 2)]
                out.append(Polygon([(x * s, y * s) for x, y in _rot(pts, rot, (cx, cy))], closed=True, **kw))
            elif kind == "circle":
                out.append(Circle((ox * s, oy * s), d["r"] * s, **kw))
            elif kind == "ellipse":
                out.append(Ellipse((ox * s, oy * s), 2 * d["rx"] * s, 2 * d["ry"] * s, angle=rot, **kw))
            elif kind == "ring":
                out.append(Wedge((ox * s, oy * s), d["ro"] * s, d["t0"] + rot, d["t1"] + rot,
                                 width=(d["ro"] - d["ri"]) * s, **kw))
            elif kind == "sphere":
                out.append(Circle((ox * s, oy * s), d["r"] * s, **kw))
            elif kind == "pyramid":
                for L0, L1, alpha in ((d["Lx0"], d["Ly0"], 1.0), (d["Lx1"], d["Ly1"], 0.0)):
                    pts = [(ox - L0 / 2, oy - L1 / 2), (ox + L0 / 2, oy - L1 / 2), (ox + L0 / 2, oy + L1 / 2), (ox - L0 / 2, oy + L1 / 2)]
                    k2 = dict(kw)
                    if alpha == 0.0:
                        k2.update(fill=False, ls=":")
                        k2.pop("facecolor", None)
                    out.append(Polygon([(x * s, y * s) for x, y in _rot(pts, rot, (ox, oy))], closed=True, **k2))
            elif kind == "poly":
                pts = [(x + ox, y + oy) for x, y in d["pts"]]
                out.append(Polygon([(x * s, y * s) for x, y in _rot(pts, rot, (ox, oy))], closed=True, **kw))
            elif kind == "polys":
                for poly in d["polys"]:
                    pts = [(x + ox, y + oy) for x, y in poly]
                    out.append(Polygon([(x * s, y * s) for x, y in _rot(pts, rot, (ox, oy))], closed=True, **kw))
            elif kind == "stl":
                b = r["bbox"]
                out.append(Rectangle((b[0] * s, b[2] * s), (b[1] - b[0]) * s, (b[3] - b[2]) * s, hatch="..", **kw))
            return out
        # 側視:x-z 或 y-z
        hor = 0 if view == "xz" else 1
        o_h = ox if hor == 0 else oy
        z0 = oz + lb[4]
        if kind == "sphere":
            out.append(Circle((o_h * s, (oz + d["r"]) * s), d["r"] * s, **kw))
            return out
        if kind == "pyramid":
            H = d["H"]
            L0, L1 = (d["Lx0"], d["Lx1"]) if hor == 0 else (d["Ly0"], d["Ly1"])
            pts = [(o_h - L0 / 2, oz), (o_h + L0 / 2, oz), (o_h + L1 / 2, oz + H), (o_h - L1 / 2, oz + H)]
            out.append(Polygon([(x * s, y * s) for x, y in pts], closed=True, **kw))
            return out
        if M.is2d(self.p) and kind in ("poly",):
            pts = [(x + ox, y + oz) for x, y in d["pts"]]
            out.append(Polygon([(x * s, y * s) for x, y in _rot(pts, rot, (ox, oz))], closed=True, **kw))
            return out
        if M.is2d(self.p) and kind == "polys":
            for poly in d["polys"]:
                pts = [(x + ox, y + oz) for x, y in poly]
                out.append(Polygon([(x * s, y * s) for x, y in pts], closed=True, **kw))
            return out
        if kind == "ring" and M.is2d(self.p):
            for sgn in (-1, 1):
                c0 = o_h + sgn * (d["ro"] + d["ri"]) / 2
                w = d["ro"] - d["ri"]
                out.append(Rectangle(((c0 - w / 2) * s, z0 * s), w * s, d["H"] * s, **kw))
            return out
        if kind == "rect" and r["through"]:
            rr = reg["x"] if hor == 0 else reg["y"]
            L = 3 * (rr[1] - rr[0])
            c0 = sum(rr) / 2
            out.append(Rectangle(((c0 - L / 2) * s, (oz + lb[4]) * s), L * s, (lb[5] - lb[4]) * s, **kw))
            return out
        lo, hi = (lb[0], lb[1]) if hor == 0 else (lb[2], lb[3])
        if kind == "stl":
            b = r["bbox"]
            lo, hi = (b[0], b[1]) if hor == 0 else (b[2], b[3])
            out.append(Rectangle((lo * s, b[4] * s), (hi - lo) * s, (b[5] - b[4]) * s, hatch="..", **kw))
            return out
        out.append(Rectangle(((o_h + lo) * s, z0 * s), (hi - lo) * s, (lb[5] - lb[4]) * s, **kw))
        return out

    def _span(self, obj, ax, reg, extra=0.0):
        v = obj.get("s" + ax)
        if v not in (None, ""):
            return float(v)
        return (reg[ax][1] - reg[ax][0]) + extra

    def _draw_source(self, ax, view, src, reg, s, p):
        h, v = view[0], view[1]
        pos = {"x": float(src["x"]), "y": float(src.get("y") or 0), "z": float(src["z"])}
        col = "#d62728"
        if src["type"] == "dipole":
            ax.plot(pos[h] * s, pos[v] * s, marker="*", color=col, ms=12, zorder=8)
            return
        axis = src.get("axis", "z")
        sign = 1 if src.get("direction") == "pos" else -1
        if src["type"] == "tfsf":
            sz = {a: float(src["s" + a]) if src.get("s" + a) not in (None, "") else 0.6 * (reg[a][1] - reg[a][0])
                  for a in (h, v)}
            sh, sv = sz[h], sz[v]
            ax.add_patch(Rectangle(((pos[h] - sh / 2) * s, (pos[v] - sv / 2) * s), sh * s, sv * s, fill=False,
                                   edgecolor=col, lw=1.2, ls="-.", zorder=8))
        if axis in (h, v):
            other = v if axis == h else h
            L = self._span(src, other, reg, 2000 if src["type"] != "mode" else 0)
            if src["type"] == "tfsf":
                L = 0
            if axis == v:
                ax.plot([(pos[h] - L / 2) * s, (pos[h] + L / 2) * s], [pos[v] * s] * 2, color=col, lw=2, zorder=8)
            else:
                ax.plot([pos[h] * s] * 2, [(pos[v] - L / 2) * s, (pos[v] + L / 2) * s], color=col, lw=2, zorder=8)
            ext = 0.12 * max(reg[h][1] - reg[h][0], reg[v][1] - reg[v][0])
            th = math.radians(float(src.get("theta") or 0)) if axis == "z" else 0.0
            dx, dy = (0, sign * ext) if axis == v else (sign * ext, 0)
            if axis == "z" and h == "x":
                dx = abs(ext) * math.sin(th)
                dy = sign * abs(ext) * math.cos(th)
            ax.annotate("", xy=((pos[h] + dx) * s, (pos[v] + dy) * s), xytext=(pos[h] * s, pos[v] * s),
                        arrowprops=dict(arrowstyle="->", color=col, lw=1.8), zorder=9)
        elif src["type"] != "tfsf":
            sh_, sv_ = self._span(src, h, reg, 2000), self._span(src, v, reg, 2000)
            ax.add_patch(Rectangle(((pos[h] - sh_ / 2) * s, (pos[v] - sv_ / 2) * s), sh_ * s, sv_ * s,
                                   facecolor=col, alpha=0.12, edgecolor=col, lw=0.8, zorder=7))

    def _draw_monitor(self, ax, view, m, reg, s, p):
        h, v = view[0], view[1]
        pos = {"x": float(m["x"]), "y": float(m.get("y") or 0), "z": float(m["z"])}
        col = MON_COLOR.get(m["kind"], "#1f77b4")
        o = m["orient"]
        axes = {"z": "xy", "x": "yz", "y": "xz", "point": "", "lx": "x", "ly": "y", "lz": "z", "3d": "xyz"}[o]
        if M.is2d(p):
            axes = axes.replace("y", "")
        sp = {a: (self._span(m, a, reg) if a in axes else 0.0) for a in ("x", "y", "z")}
        if M.is2d(p):
            sp["y"] = 0.0
        wh, wv = sp[h], sp[v]
        if wh == 0 and wv == 0:
            ax.plot(pos[h] * s, pos[v] * s, marker="o", color=col, ms=6, zorder=8)
        elif wh == 0 or wv == 0:
            if wh:
                ax.plot([(pos[h] - wh / 2) * s, (pos[h] + wh / 2) * s], [pos[v] * s] * 2, color=col, lw=2.2, zorder=8)
            else:
                ax.plot([pos[h] * s] * 2, [(pos[v] - wv / 2) * s, (pos[v] + wv / 2) * s], color=col, lw=2.2, zorder=8)
        else:
            ax.add_patch(Rectangle(((pos[h] - wh / 2) * s, (pos[v] - wv / 2) * s), wh * s, wv * s,
                                   facecolor=col, alpha=0.10, edgecolor=col, lw=1.0, zorder=6))
        lab_x = pos[h] + (wh / 2 if wh else 0)
        lab_y = pos[v] + (wv / 2 if wv else 0)
        ax.text(lab_x * s, lab_y * s, " " + m["name"], color=col, fontsize=7, zorder=9, va="bottom")
