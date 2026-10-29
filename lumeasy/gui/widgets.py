"""共用元件:清單 + 表單編輯器、小型 matplotlib 圖。"""
from __future__ import annotations

import copy

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMenu, QPushButton, QScrollArea,
                               QSplitter, QToolButton, QVBoxLayout, QWidget, QFrame)

from lumeasy.gui.forms import FieldForm


def hint(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setWordWrap(True)
    lab.setObjectName("hint")
    lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return lab


def title(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("pageTitle")
    return lab


class ListEditor(QWidget):
    """左邊清單、右邊表單。items() 回傳要編輯的 list(直接改它)。"""
    selectionChanged = Signal(object)

    def __init__(self, win, items, fields_for, label_for, add_actions, on_change=None,
                 extra_for=None, new_name=None, empty_text="(清單是空的,按「新增」)"):
        super().__init__()
        self.win, self.items, self.fields_for, self.label_for = win, items, fields_for, label_for
        self.on_change, self.extra_for, self.new_name = on_change, extra_for, new_name
        self.empty_text = empty_text
        sp = QSplitter(Qt.Horizontal)
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._sel)
        lv.addWidget(self.list, 1)
        row = QHBoxLayout()
        self.add_btn = QToolButton()
        self.add_btn.setText("＋ 新增")
        self.add_btn.setPopupMode(QToolButton.InstantPopup)
        self.add_btn.setObjectName("primarySmall")
        menu = QMenu(self)
        for lab, fac in add_actions:
            menu.addAction(lab, lambda fac=fac: self.add(fac()))
        self.add_btn.setMenu(menu)
        row.addWidget(self.add_btn)
        for txt, fn, tip in (("複製", self.dup, "複製選到的項目"), ("刪除", self.delete, "刪除選到的項目"),
                             ("↑", lambda: self.move(-1), "往上移"), ("↓", lambda: self.move(1), "往下移")):
            b = QPushButton(txt)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            if txt in ("↑", "↓"):
                b.setFixedWidth(34)
            row.addWidget(b)
        lv.addLayout(row)
        sp.addWidget(left)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        sp.addWidget(self.scroll)
        sp.setStretchFactor(0, 2)
        sp.setStretchFactor(1, 5)
        sp.setSizes([260, 640])
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(sp)
        self.form = None
        self._building = False

    def current(self):
        i = self.list.currentRow()
        it = self.items()
        return it[i] if 0 <= i < len(it) else None

    def refresh(self, keep=True):
        it = self.items()
        cur = self.list.currentRow() if keep else -1
        self._building = True
        self.list.clear()
        for x in it:
            QListWidgetItem(self.label_for(x), self.list)
        if not it:
            self.list.addItem(self.empty_text)
            self.list.item(0).setFlags(Qt.NoItemFlags)
        self._building = False
        if it:
            self.list.setCurrentRow(min(max(cur, 0), len(it) - 1))
        self._sel(self.list.currentRow() if it else -1)

    def select_name(self, name):
        for i, x in enumerate(self.items()):
            if x.get("name") == name:
                self.list.setCurrentRow(i)
                return

    def update_label(self):
        i = self.list.currentRow()
        x = self.current()
        if x is not None and self.list.item(i):
            self.list.item(i).setText(self.label_for(x))

    def _sel(self, i):
        if self._building:
            return
        x = self.current()
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 4, 8, 8)
        if x is None:
            v.addWidget(hint("在左邊選一個項目來編輯,或按「＋ 新增」。"))
            self.form = None
        else:
            self.form = FieldForm(self.fields_for(x), x, self.win, lambda k, x=x: self._changed(x, k))
            v.addWidget(self.form)
            if self.extra_for:
                ex = self.extra_for(x)
                if ex is not None:
                    v.addWidget(ex)
        v.addStretch(1)
        self.scroll.setWidget(w)
        self.selectionChanged.emit(x)

    def rebuild_form(self):
        self._sel(self.list.currentRow())

    def _changed(self, x, key):
        if self.on_change:
            self.on_change(x, key)
        self.update_label()
        self.win.changed()

    def add(self, item):
        if item is None:
            return
        self.items().append(item)
        self.refresh(keep=False)
        self.list.setCurrentRow(len(self.items()) - 1)
        self.win.changed()

    def dup(self):
        x = self.current()
        if x is None:
            return
        y = copy.deepcopy(x)
        if self.new_name:
            y["name"] = self.new_name(x.get("name", "item"))
        it = self.items()
        it.insert(self.list.currentRow() + 1, y)
        r = self.list.currentRow() + 1
        self.refresh()
        self.list.setCurrentRow(r)
        self.win.changed()

    def delete(self):
        i = self.list.currentRow()
        it = self.items()
        if 0 <= i < len(it):
            it.pop(i)
            self.refresh()
            self.win.changed()

    def move(self, d):
        i = self.list.currentRow()
        it = self.items()
        j = i + d
        if 0 <= i < len(it) and 0 <= j < len(it):
            it[i], it[j] = it[j], it[i]
            self.refresh()
            self.list.setCurrentRow(j)
            self.win.changed()


class MiniPlot(QWidget):
    def __init__(self, h=2.6):
        super().__init__()
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
        from matplotlib.figure import Figure
        self.fig = Figure(figsize=(4.5, h), dpi=95)
        self.canvas = FigureCanvasQTAgg(self.fig)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(self.canvas)
        self.setMinimumHeight(int(h * 80))

    def plot_nk(self, wl, n, k, title=""):
        self.fig.clear()
        a = self.fig.add_subplot(111)
        a.plot(wl, n, label="n", color="#1f77b4")
        a.set_xlabel("波長 (nm)", fontsize=8)
        a.set_ylabel("n", color="#1f77b4", fontsize=8)
        a.tick_params(labelsize=7)
        b = a.twinx()
        b.plot(wl, k, label="k", color="#d62728")
        b.set_ylabel("k", color="#d62728", fontsize=8)
        b.tick_params(labelsize=7)
        if title:
            a.set_title(title, fontsize=9)
        a.grid(alpha=0.3)
        self.fig.tight_layout(pad=0.5)
        self.canvas.draw_idle()

    def clear(self, msg=""):
        self.fig.clear()
        if msg:
            self.fig.text(0.5, 0.5, msg, ha="center", va="center", fontsize=9, color="#888")
        self.canvas.draw_idle()
