"""草圖畫布(像 Onshape:在格子上畫矩形 / 圓 / 多邊形,再擠出或挖孔)。

場景座標 = nm,y 軸朝上(3D 是 x-y 俯視,2D 是 x-z 截面)。
Lumerical 沒有布林減法:「挖孔」= 放一個材料 etch、網格優先順序 1 的同形狀物件蓋過去。
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsPathItem, QGraphicsScene, QGraphicsView

from lumeasy import model as M
from lumeasy.gui.preview import mat_color


def _circle(cx, cy, r, n=48, t0=0.0, t1=360.0):
    a0, a1 = math.radians(t0), math.radians(t1)
    return [(cx + r * math.cos(a0 + (a1 - a0) * i / n), cy + r * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + (0 if t1 - t0 >= 360 else 1))]


def _rot(pts, deg, c):
    if not deg:
        return pts
    a = math.radians(deg)
    ca, sa = math.cos(a), math.sin(a)
    return [(c[0] + (x - c[0]) * ca - (y - c[1]) * sa, c[1] + (x - c[0]) * sa + (y - c[1]) * ca) for x, y in pts]


def footprints(r, d2, reg):
    """擺放結果 → 畫布上的多邊形(3D 俯視 x-y;2D 截面 x-z)。回傳 [ [(x,y),...], ... ]。"""
    obj, kind, d, sh = r["obj"], r["kind"], r["data"], r["shift"]
    rot = float(obj.get("rot") or 0)
    out = []
    copies = r["copies"] if len(r["copies"]) <= 2500 else r["copies"][:2500]
    for c in copies:
        ox, oy, oz = sh[0] + c[0], sh[1] + c[1], sh[2]
        lb = r["local"]
        if d2:
            z0 = oz + lb[4]
            if kind == "rect":
                Lx, cx = d["Lx"], ox
                if r["through"]:
                    Lx, cx = 3 * (reg["x"][1] - reg["x"][0]), sum(reg["x"]) / 2
                pts = [(cx - Lx / 2, z0), (cx + Lx / 2, z0), (cx + Lx / 2, z0 + d["H"]), (cx - Lx / 2, z0 + d["H"])]
                out.append(_rot(pts, rot, (cx, z0 + d["H"] / 2)))
            elif kind in ("circle", "ellipse"):
                w = d["r"] if kind == "circle" else d["rx"]
                out.append([(ox - w, z0), (ox + w, z0), (ox + w, z0 + d["H"]), (ox - w, z0 + d["H"])])
            elif kind == "ring":
                for sgn in (-1, 1):
                    c0, w = ox + sgn * (d["ro"] + d["ri"]) / 2, d["ro"] - d["ri"]
                    out.append([(c0 - w / 2, z0), (c0 + w / 2, z0), (c0 + w / 2, z0 + d["H"]), (c0 - w / 2, z0 + d["H"])])
            elif kind == "sphere":
                out.append(_circle(ox, oz + d["r"], d["r"]))
            elif kind == "pyramid":
                H = d["H"]
                out.append([(ox - d["Lx0"] / 2, oz), (ox + d["Lx0"] / 2, oz), (ox + d["Lx1"] / 2, oz + H), (ox - d["Lx1"] / 2, oz + H)])
            elif kind == "poly":
                out.append(_rot([(x + ox, y + oz) for x, y in d["pts"]], rot, (ox, oz)))
            elif kind == "polys":
                for poly in d["polys"]:
                    out.append([(x + ox, y + oz) for x, y in poly])
            continue
        if kind == "rect":
            Lx, Ly, cx, cy = d["Lx"], d["Ly"], ox, oy
            if r["through"]:
                Lx, Ly = 3 * (reg["x"][1] - reg["x"][0]), 3 * (reg["y"][1] - reg["y"][0])
                cx, cy = sum(reg["x"]) / 2, sum(reg["y"]) / 2
            pts = [(cx - Lx / 2, cy - Ly / 2), (cx + Lx / 2, cy - Ly / 2), (cx + Lx / 2, cy + Ly / 2), (cx - Lx / 2, cy + Ly / 2)]
            out.append(_rot(pts, rot, (cx, cy)))
        elif kind in ("circle", "sphere"):
            out.append(_circle(ox, oy, d["r"]))
        elif kind == "ellipse":
            out.append(_rot([(ox + d["rx"] * math.cos(t), oy + d["ry"] * math.sin(t))
                             for t in [2 * math.pi * i / 48 for i in range(48)]], rot, (ox, oy)))
        elif kind == "ring":
            outer = _circle(ox, oy, d["ro"], 48, d["t0"] + rot, d["t1"] + rot)
            inner = _circle(ox, oy, d["ri"], 48, d["t0"] + rot, d["t1"] + rot)
            out.append(outer + inner[::-1])
        elif kind == "pyramid":
            L0, L1 = d["Lx0"], d["Ly0"]
            out.append(_rot([(ox - L0 / 2, oy - L1 / 2), (ox + L0 / 2, oy - L1 / 2), (ox + L0 / 2, oy + L1 / 2), (ox - L0 / 2, oy + L1 / 2)], rot, (ox, oy)))
        elif kind == "poly":
            out.append(_rot([(x + ox, y + oy) for x, y in d["pts"]], rot, (ox, oy)))
        elif kind == "polys":
            for poly in d["polys"]:
                out.append(_rot([(x + ox, y + oy) for x, y in poly], rot, (ox, oy)))
        elif kind == "stl":
            b = r["bbox"]
            out.append([(b[0], b[2]), (b[1], b[2]), (b[1], b[3]), (b[0], b[3])])
    return out


class SketchCanvas(QGraphicsView):
    shapeDrawn = Signal(str, object)        # ("rect", (x0,y0,x1,y1)) / ("circle", (cx,cy,r)) / ("polygon", [(x,y)...])
    objectClicked = Signal(str)
    objectMoved = Signal(str, float, float)
    cursorMoved = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.Antialiasing)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setMouseTracking(True)
        self.scale(0.35, -0.35)
        self.grid = 50.0
        self.snap = True
        self.tool = "select"
        self.d2 = False
        self.unit_label = "nm"
        self.unit_nm = 1.0
        self._start = None
        self._rubber = None
        self._poly = []
        self._pan = None
        self._drag = None
        self.items_by_name = {}
        self.selected = None
        self.plane_z = 0.0
        self.scene().setSceneRect(-1e7, -1e7, 2e7, 2e7)

    # -- 內容 ---------------------------------------------------------------
    def load(self, p, plane_z=None, selected=None):
        sc = self.scene()
        for it in list(sc.items()):
            sc.removeItem(it)
        self.items_by_name = {}
        self.selected = selected
        self.d2 = M.is2d(p)
        try:
            placed = M.place_objects(p)
            reg = M.compute_region(p, placed)
        except Exception:  # noqa: BLE001
            return
        h, v = ("x", "z") if self.d2 else ("x", "y")
        x0, x1 = reg[h]
        y0, y1 = reg[v]
        reg_item = sc.addRect(QRectF(x0, y0, x1 - x0, y1 - y0), self._pen("#ff7f0e", 1.5, Qt.DashLine))
        reg_item.setZValue(50)
        for r in placed:
            if not r["enabled"] or r["error"]:
                continue
            obj = r["obj"]
            col = QColor(mat_color(p, obj.get("material")))
            etch = obj.get("material") == "etch"
            active = True
            if not self.d2 and plane_z is not None:
                b = r["bbox"]
                active = b[4] - 1e-6 <= plane_z <= b[5] + 1e-6
            path = QPainterPath()
            for poly in footprints(r, self.d2, reg):
                path.addPolygon(QPolygonF([QPointF(x, y) for x, y in poly] + [QPointF(*poly[0])]))
            it = QGraphicsPathItem(path)
            col.setAlpha(170 if active else 55)
            it.setBrush(QBrush(QColor(255, 255, 255, 230) if etch else col))
            sel = obj["name"] == selected
            it.setPen(self._pen("#d62728" if sel else ("#444" if active else "#aaa"), 2.2 if sel else 1.0,
                                Qt.DashLine if etch else Qt.SolidLine))
            it.setZValue(10 + (5 if etch or int(obj.get("mesh_order") or 2) < 2 else 0) + (20 if sel else 0))
            it.setData(0, obj["name"])
            it.setToolTip(f"{obj['name']}({M.SHAPES[obj['shape']]['label']},{obj.get('material')})")
            sc.addItem(it)
            self.items_by_name[obj["name"]] = it
        self.viewport().update()

    def fit(self, p):
        try:
            reg = M.compute_region(p)
        except Exception:  # noqa: BLE001
            return
        h, v = ("x", "z") if M.is2d(p) else ("x", "y")
        r = QRectF(reg[h][0], reg[v][0], reg[h][1] - reg[h][0], reg[v][1] - reg[v][0])
        self.fitInView(r.adjusted(-0.1 * r.width(), -0.1 * r.height(), 0.1 * r.width(), 0.1 * r.height()), Qt.KeepAspectRatio)

    @staticmethod
    def _pen(c, w, style=Qt.SolidLine):
        pen = QPen(QColor(c), w, style)
        pen.setCosmetic(True)
        return pen

    # -- 格線 ---------------------------------------------------------------
    def drawBackground(self, painter, rect):
        painter.fillRect(rect, QColor("#fbfbfd"))
        px = self.transform().m11()
        g = self.grid
        while g * px < 7:
            g *= 2
        left, right = math.floor(rect.left() / g) * g, rect.right()
        bottom, top = math.floor(rect.top() / g) * g, rect.bottom()
        minor, major = self._pen("#e6e8ee", 1), self._pen("#c9cdd8", 1)
        x = left
        i0 = int(round(left / g))
        while x <= right:
            painter.setPen(major if i0 % 5 == 0 else minor)
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            x += g
            i0 += 1
        y = bottom
        j0 = int(round(bottom / g))
        while y <= top:
            painter.setPen(major if j0 % 5 == 0 else minor)
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            y += g
            j0 += 1
        painter.setPen(self._pen("#7a7f8c", 1.4))
        painter.drawLine(QPointF(0, rect.top()), QPointF(0, rect.bottom()))
        painter.drawLine(QPointF(rect.left(), 0), QPointF(rect.right(), 0))

    def drawForeground(self, painter, rect):
        if self.tool == "polygon" and self._poly:
            painter.setPen(self._pen("#d62728", 1.8))
            pts = [QPointF(x, y) for x, y in self._poly]
            if self._hover is not None:
                pts.append(QPointF(*self._hover))
            painter.drawPolyline(QPolygonF(pts))
            painter.setBrush(QColor("#d62728"))
            s = 4 / self.transform().m11()
            for x, y in self._poly:
                painter.drawEllipse(QPointF(x, y), s, s)

    _hover = None

    # -- 滑鼠 ---------------------------------------------------------------
    def _snap(self, pt):
        x, y = pt.x(), pt.y()
        if self.snap and self.grid > 0:
            x = round(x / self.grid) * self.grid
            y = round(y / self.grid) * self.grid
        return x, y

    def wheelEvent(self, e):
        f = 1.2 if e.angleDelta().y() > 0 else 1 / 1.2
        self.scale(f, f)

    def mousePressEvent(self, e):
        if e.button() in (Qt.MiddleButton, Qt.RightButton) and not (self.tool == "polygon" and e.button() == Qt.RightButton and self._poly):
            self._pan = e.position()
            self.setCursor(Qt.ClosedHandCursor)
            return
        if e.button() == Qt.RightButton and self.tool == "polygon":
            self._finish_poly()
            return
        if e.button() != Qt.LeftButton:
            return
        pt = self._snap(self.mapToScene(e.position().toPoint()))
        if self.tool == "select":
            it = self._item_at(e)
            if it is not None:
                name = it.data(0)
                self.objectClicked.emit(name)
                self._drag = (name, pt, it, it.pos())
            return
        if self.tool in ("rect", "circle"):
            self._start = pt
            self._rubber = QGraphicsPathItem()
            self._rubber.setPen(self._pen("#d62728", 1.8, Qt.DashLine))
            self._rubber.setBrush(QColor(214, 39, 40, 40))
            self._rubber.setZValue(100)
            self.scene().addItem(self._rubber)
        elif self.tool == "polygon":
            if len(self._poly) >= 3:
                x0, y0 = self._poly[0]
                tol = 8 / self.transform().m11()
                if math.hypot(pt[0] - x0, pt[1] - y0) <= tol:
                    self._finish_poly()
                    return
            self._poly.append(pt)
            self.viewport().update()

    def mouseDoubleClickEvent(self, e):
        if self.tool == "polygon":
            self._finish_poly()

    def mouseMoveEvent(self, e):
        if self._pan is not None:
            d = e.position() - self._pan
            self._pan = e.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(d.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(d.y()))
            return
        sp = self.mapToScene(e.position().toPoint())
        pt = self._snap(sp)
        self.cursorMoved.emit(pt[0], pt[1])
        if self._drag is not None:
            name, p0, it, pos0 = self._drag
            it.setPos(pos0 + QPointF(pt[0] - p0[0], pt[1] - p0[1]))
            return
        if self._start is not None and self._rubber is not None:
            x0, y0 = self._start
            path = QPainterPath()
            if self.tool == "rect":
                path.addRect(QRectF(QPointF(x0, y0), QPointF(*pt)).normalized())
            else:
                r = math.hypot(pt[0] - x0, pt[1] - y0)
                path.addEllipse(QPointF(x0, y0), r, r)
            self._rubber.setPath(path)
        if self.tool == "polygon":
            self._hover = pt
            self.viewport().update()

    def mouseReleaseEvent(self, e):
        if self._pan is not None:
            self._pan = None
            self.setCursor(Qt.ArrowCursor if self.tool == "select" else Qt.CrossCursor)
            return
        if self._drag is not None:
            name, p0, it, pos0 = self._drag
            self._drag = None
            pt = self._snap(self.mapToScene(e.position().toPoint()))
            dx, dy = pt[0] - p0[0], pt[1] - p0[1]
            if abs(dx) > 1e-9 or abs(dy) > 1e-9:
                self.objectMoved.emit(name, dx, dy)
            return
        if self._start is not None:
            pt = self._snap(self.mapToScene(e.position().toPoint()))
            x0, y0 = self._start
            self._start = None
            if self._rubber is not None:
                self.scene().removeItem(self._rubber)
                self._rubber = None
            if self.tool == "rect":
                if abs(pt[0] - x0) > 1e-9 and abs(pt[1] - y0) > 1e-9:
                    self.shapeDrawn.emit("rect", (min(x0, pt[0]), min(y0, pt[1]), max(x0, pt[0]), max(y0, pt[1])))
            else:
                r = math.hypot(pt[0] - x0, pt[1] - y0)
                if r > 1e-9:
                    self.shapeDrawn.emit("circle", (x0, y0, r))

    def keyPressEvent(self, e):
        if self.tool == "polygon":
            if e.key() == Qt.Key_Escape:
                self._poly = []
                self.viewport().update()
                return
            if e.key() == Qt.Key_Backspace and self._poly:
                self._poly.pop()
                self.viewport().update()
                return
            if e.key() in (Qt.Key_Return, Qt.Key_Enter):
                self._finish_poly()
                return
        super().keyPressEvent(e)

    def _finish_poly(self):
        pts = []
        for p in self._poly:
            if not pts or p != pts[-1]:
                pts.append(p)
        self._poly = []
        self._hover = None
        self.viewport().update()
        if len(pts) >= 3:
            self.shapeDrawn.emit("polygon", pts)

    def _item_at(self, e):
        for it in self.items(e.position().toPoint()):
            if isinstance(it, QGraphicsPathItem) and it.data(0):
                return it
        return None

    def set_tool(self, tool):
        self.tool = tool
        self._poly = []
        self._hover = None
        self.setCursor(Qt.ArrowCursor if tool == "select" else Qt.CrossCursor)
        self.viewport().update()
