"""依 model.py 的欄位定義自動產生表單。

數字欄可以直接打算式(例如 2*150、600/2+50),長度一律以專案單位顯示、內部存 nm。
"""
from __future__ import annotations

import ast
import operator as op

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPlainTextEdit, QPushButton, QWidget, QSizePolicy)

from lumeasy import model as M

_OPS = {ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul, ast.Div: op.truediv, ast.Pow: op.pow,
        ast.USub: op.neg, ast.UAdd: op.pos}


def calc(text: str) -> float:
    """安全地算簡單算式(只允許數字與 + - * / ** 括號)。"""
    t = str(text).strip().replace("^", "**").replace("×", "*").replace("÷", "/")
    if not t:
        raise ValueError("空白")

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](ev(n.operand))
        raise ValueError("只能用數字和 + - * / ( )")
    return float(ev(ast.parse(t, mode="eval")))


def fmt(v) -> str:
    if v is None:
        return ""
    v = float(v)
    if v == int(v) and abs(v) < 1e12:
        return str(int(v))
    return f"{v:.6g}"


KIND_HELP = {
    "len": "長度", "wl": "波長(nm)", "float": "數字", "int": "整數", "angle": "角度(度)", "time": "時間(fs)",
    "choice": "從清單選一個", "bool": "勾選 = 開", "material": "材料:★ 是你自己加的,其他是 Lumerical 內建",
    "objtop": "選一個排在前面的物件", "objref": "選一個物件", "file": "按「瀏覽…」選檔案", "vertices": "每行一個頂點",
    "autolen": "勾「自動」或填數字", "outputs": "勾選要記錄的分量", "formats": "可以複選", "color": "點一下選顏色",
    "builtin": "Lumerical 內建材料", "text": "文字",
}


def tooltip_for(f, ctx=None) -> str:
    """滑鼠提示:這是什麼、怎麼填、對應 Lumerical 的哪個設定。"""
    tip = f.get("tip") or M.TIPS.get(f["label"]) or ""
    kind = f.get("kind", "")
    how = KIND_HELP.get(kind, "")
    if kind == "len" and ctx is not None:
        how = f"長度,單位 {ctx.unit_label()};可以直接打算式,例如 2*150"
    elif kind in ("float", "int", "angle", "wl", "time"):
        how += ";可以直接打算式"
    parts = [f"<b>{f['label']}</b>"]
    if tip:
        parts.append(tip)
    if how:
        parts.append(f"<span style='color:#555'>填法:{how}</span>")
    if f.get("lum"):
        parts.append(f"<span style='color:#1f5fbf'>對應 Lumerical:{f['lum']}</span>")
    return "<br>".join(parts)


def vertices_text(pts, scale=1.0) -> str:
    return chr(10).join(f"{fmt(x * scale)}, {fmt(y * scale)}" for x, y in pts)


UNIT_TXT = {"len": None, "wl": "nm", "angle": "°", "time": "fs"}


class NumEdit(QLineEdit):
    valueChanged = Signal()

    def __init__(self, integer=False, minimum=None, maximum=None):
        super().__init__()
        self.integer, self.minimum, self.maximum = integer, minimum, maximum
        self._val = 0.0
        self.editingFinished.connect(self._commit)
        self.setMinimumWidth(90)
        self.setToolTip("可以直接打算式,例如 2*150 或 (400-80)/2")

    def setValue(self, v):
        self._val = v
        self.setText(fmt(v))
        self._ok(True)

    def value(self):
        return self._val

    def _ok(self, ok):
        self.setStyleSheet("" if ok else "background:#ffe1e1;")

    def _commit(self):
        try:
            v = calc(self.text())
            if self.integer:
                v = int(round(v))
            if self.minimum is not None and v < self.minimum:
                v = type(v)(self.minimum)
            if self.maximum is not None and v > self.maximum:
                v = type(v)(self.maximum)
        except Exception:  # noqa: BLE001
            self._ok(False)
            return
        changed = v != self._val
        self._val = v
        self.setText(fmt(v))
        self._ok(True)
        if changed:
            self.valueChanged.emit()


class FieldForm(QWidget):
    """data 是會被直接修改的 dict;每改一個欄位就呼叫 on_change(key)。"""

    def __init__(self, fields, data, ctx, on_change=None, parent=None):
        super().__init__(parent)
        self.fields, self.data, self.ctx, self.on_change = fields, data, ctx, on_change
        self.widgets = {}
        self.lay = QFormLayout(self)
        self.lay.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.lay.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.lay.setContentsMargins(4, 4, 4, 4)
        self.lay.setVerticalSpacing(6)
        self.build()

    # ctx 提供:unit()、dim()、materials()、objects(exclude)、files_dir()
    def unit_factor(self):
        return M.UNIT_NM[self.ctx.unit()]

    def visible(self, f):
        d = f.get("dims")
        if d is not None and d != self.ctx.dim():
            return False
        if f.get("show") and not f["show"](self.data):
            return False
        if f.get("adv") and getattr(self.ctx, "simple", lambda: False)():
            # 簡易模式隱藏進階欄位;但值已經被改過(不是預設)的照樣顯示,免得設定藏起來看不到
            return self.data.get(f["key"], f.get("default")) != f.get("default")
        return True

    def build(self):
        while self.lay.rowCount():
            self.lay.removeRow(0)
        self.widgets = {}
        sec = None
        for f in self.fields:
            if not self.visible(f):
                continue
            w = self.make(f)
            if w is None:
                continue
            if f.get("sec") and f["sec"] != sec:
                sec = f["sec"]
                h = QLabel(sec)
                h.setObjectName("formSection")
                self.lay.addRow(h)
            lab = QLabel(f["label"])
            lab.setWordWrap(True)
            lab.setMaximumWidth(190)
            lab.setMinimumWidth(120)
            tt = tooltip_for(f, self.ctx)
            lab.setToolTip(tt)
            w.setToolTip(tt)
            for child in w.findChildren(QWidget):
                if not child.toolTip():
                    child.setToolTip(tt)
            self.lay.addRow(lab, w)

    def _emit(self, key):
        if self.on_change:
            self.on_change(key)
        # 有欄位的顯示與否取決於剛剛改的值 → 重建表單(延後到訊號處理完)
        if any(f.get("show") for f in self.fields):
            from PySide6.QtCore import QTimer
            before = [f["key"] for f in self.fields if self.visible(f)]
            QTimer.singleShot(0, lambda before=before: self._maybe_rebuild(before))

    def _maybe_rebuild(self, before):
        now = [f["key"] for f in self.fields if self.visible(f)]
        if now != before:
            self.build()

    def make(self, f):
        k, kind = f["key"], f["kind"]
        val = self.data.get(k, f.get("default"))
        if kind in ("len", "wl", "float", "int", "angle", "time"):
            e = NumEdit(integer=(kind == "int"), minimum=f.get("min"), maximum=f.get("max"))
            fac = self.unit_factor() if kind == "len" else 1.0
            e.setValue((float(val or 0) / fac) if kind != "int" else int(val or 0))

            def ch(e=e, k=k, fac=fac, kind=kind):
                self.data[k] = e.value() * fac if kind != "int" else int(e.value())
                self._emit(k)
            e.valueChanged.connect(ch)
            self.widgets[k] = e
            return self._with_unit(e, self.ctx.unit_label() if kind == "len" else UNIT_TXT.get(kind))
        if kind == "autolen":
            box = QWidget()
            h = QHBoxLayout(box)
            h.setContentsMargins(0, 0, 0, 0)
            cb = QCheckBox("自動")
            e = NumEdit(minimum=0)
            fac = self.unit_factor()
            auto = val in (None, "")
            cb.setChecked(auto)
            e.setEnabled(not auto)
            e.setValue(0 if auto else float(val) / fac)

            def ch(cb=cb, e=e, k=k, fac=fac):
                e.setEnabled(not cb.isChecked())
                if cb.isChecked():
                    self.data[k] = None
                else:
                    if e.value() <= 0:
                        e.setValue(1000 / fac)
                    self.data[k] = e.value() * fac
                self._emit(k)
            cb.toggled.connect(ch)
            e.valueChanged.connect(ch)
            h.addWidget(cb)
            h.addWidget(e, 1)
            h.addWidget(QLabel(self.ctx.unit_label()))
            self.widgets[k] = (cb, e)
            return box
        if kind == "text":
            e = QLineEdit(str(val or ""))

            def ch(e=e, k=k):
                if self.data.get(k) != e.text().strip():
                    self.data[k] = e.text().strip()
                    self._emit(k)
            e.editingFinished.connect(ch)
            self.widgets[k] = e
            return e
        if kind == "bool":
            c = QCheckBox()
            c.setChecked(bool(val))

            def ch(_=None, c=c, k=k):
                self.data[k] = c.isChecked()
                self._emit(k)
            c.toggled.connect(ch)
            self.widgets[k] = c
            return c
        if kind == "choice":
            c = QComboBox()
            for v, lab in f["choices"]:
                c.addItem(lab, v)
            i = c.findData(val)
            c.setCurrentIndex(max(i, 0))
            if i < 0 and f["choices"]:
                self.data[k] = f["choices"][0][0]

            def ch(_=None, c=c, k=k):
                self.data[k] = c.currentData()
                self._emit(k)
            c.currentIndexChanged.connect(ch)
            self.widgets[k] = c
            return c
        if kind in ("material", "objref", "objtop"):
            c = QComboBox()
            c.setMaxVisibleItems(25)
            if kind == "material":
                c.setEditable(True)
                custom, builtin = self.ctx.materials()
                for n in custom:
                    c.addItem("★ " + n, n)
                c.addItem("etch(挖空 = 背景折射率)", "etch")
                for n in builtin:
                    if n != "etch":
                        c.addItem(n, n)
            elif kind == "objref":
                c.addItem("(不指定,用手動範圍)", "")
                for n in self.ctx.objects(self.data.get("name")):
                    c.addItem(n, n)
            else:
                c.addItem("(不疊,從 z = 0 算)", "")
                c.addItem("上一個物件", "@prev")
                for n in self.ctx.objects(self.data.get("name"), before=self.data):
                    c.addItem(n, n)
            i = c.findData(val)
            if i < 0 and val:
                c.addItem(str(val), val)
                i = c.count() - 1
            c.setCurrentIndex(max(i, 0))

            def ch(_=None, c=c, k=k):
                v = c.currentData()
                if v is None:      # 使用者自己打的字
                    v = c.currentText().replace("★ ", "").strip()
                if self.data.get(k) != v:
                    self.data[k] = v
                    self._emit(k)
            c.currentIndexChanged.connect(ch)
            if c.isEditable():
                c.lineEdit().editingFinished.connect(ch)
            self.widgets[k] = c
            return c
        if kind == "color":
            from PySide6.QtWidgets import QColorDialog
            from PySide6.QtGui import QColor
            b = QPushButton(str(val or "#888888"))

            def paint(b=b):
                c = self.data.get(k) or "#888888"
                fg = "#000" if QColor(c).lightness() > 140 else "#fff"
                b.setText(c)
                b.setStyleSheet(f"background:{c}; color:{fg}; border:1px solid #888; padding:3px;")
            paint()

            def pick(b=b, k=k):
                c = QColorDialog.getColor(QColor(self.data.get(k) or "#888888"), self, "選顏色")
                if c.isValid():
                    self.data[k] = c.name()
                    paint()
                    self._emit(k)
            b.clicked.connect(pick)
            self.widgets[k] = b
            return b
        if kind == "builtin":
            c = QComboBox()
            c.setMaxVisibleItems(25)
            for n in self.ctx.materials()[1]:
                if n != "etch":
                    c.addItem(n, n)
            i = c.findData(val)
            c.setCurrentIndex(max(i, 0))
            if i < 0 and c.count():
                self.data[k] = c.currentData()

            def ch(_=None, c=c, k=k):
                self.data[k] = c.currentData()
                self._emit(k)
            c.currentIndexChanged.connect(ch)
            self.widgets[k] = c
            return c
        if kind == "file":
            box = QWidget()
            h = QHBoxLayout(box)
            h.setContentsMargins(0, 0, 0, 0)
            e = QLineEdit(str(val or ""))
            b = QPushButton("瀏覽…")

            def pick(e=e, k=k, flt=f.get("filter", "")):
                p, _ = QFileDialog.getOpenFileName(self, "選擇檔案", self.ctx.files_dir(), flt + ";;所有檔案 (*.*)")
                if p:
                    e.setText(p)
                    self.data[k] = p
                    self._emit(k)

            def ch(e=e, k=k):
                if self.data.get(k) != e.text().strip():
                    self.data[k] = e.text().strip()
                    self._emit(k)
            b.clicked.connect(pick)
            e.editingFinished.connect(ch)
            h.addWidget(e, 1)
            h.addWidget(b)
            self.widgets[k] = e
            return box
        if kind == "vertices":
            fac = self.unit_factor()
            try:
                shown = vertices_text(M.parse_vertices(val or ""), 1 / fac)
            except ValueError:
                shown = str(val or "")
            t = QPlainTextEdit(shown)
            t.setFixedHeight(110)
            t.setToolTip(f"每行一個頂點,例如「0, 0」;單位 {self.ctx.unit_label()}。也可以在「草圖」頁用滑鼠畫。")
            timer = QTimer(t)
            timer.setSingleShot(True)
            timer.setInterval(500)

            def ch(t=t, k=k, fac=fac):
                try:
                    pts = M.parse_vertices(t.toPlainText())
                except ValueError:
                    t.setStyleSheet("background:#ffe1e1;")
                    return
                t.setStyleSheet("")
                self.data[k] = vertices_text(pts, fac)    # 內部一律存 nm
                self._emit(k)
            timer.timeout.connect(ch)
            t.textChanged.connect(timer.start)
            self.widgets[k] = t
            wrap = QWidget()
            v = QHBoxLayout(wrap)
            v.setContentsMargins(0, 0, 0, 0)
            v.addWidget(t, 1)
            v.addWidget(QLabel(f"單位\n{self.ctx.unit_label()}"))
            return wrap
        if kind in ("outputs", "formats"):
            from PySide6.QtWidgets import QGridLayout
            box = QWidget()
            g = QGridLayout(box)
            g.setContentsMargins(0, 0, 0, 0)
            g.setHorizontalSpacing(8)
            opts = [(c, c) for c in M.FIELD_OUTPUTS] if kind == "outputs" else M.OUTPUT_FORMATS
            per_row = 5 if kind == "outputs" else 2
            cur = set(val or [])
            cbs = []
            for i, (v, lab) in enumerate(opts):
                c = QCheckBox(lab)
                c.setChecked(v in cur)
                cbs.append((v, c))
                g.addWidget(c, i // per_row, i % per_row)
            if kind == "outputs":
                allb = QPushButton("全選 / 全不選")
                g.addWidget(allb, 2, 0, 1, 2)

                def toggle_all(cbs=cbs):
                    on = not all(c.isChecked() for _, c in cbs)
                    for _, c in cbs:
                        c.setChecked(on)
                allb.clicked.connect(toggle_all)

            def ch(_=None, cbs=cbs, k=k):
                self.data[k] = [v for v, c in cbs if c.isChecked()]
                self._emit(k)
            for _, c in cbs:
                c.toggled.connect(ch)
            self.widgets[k] = cbs
            return box
        return None

    def _with_unit(self, w, unit):
        if not unit:
            return w
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(w, 1)
        u = QLabel(unit)
        u.setMinimumWidth(22)
        h.addWidget(u)
        box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        return box
