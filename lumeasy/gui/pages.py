"""各頁面。所有頁面直接改 win.p(專案 dict),改完呼叫 win.changed()。"""
from __future__ import annotations

import copy
import math
import os

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QMessageBox, QPlainTextEdit, QPushButton, QRadioButton, QScrollArea, QSplitter,
                               QTableWidget, QTableWidgetItem, QTextBrowser, QToolButton, QVBoxLayout, QWidget)

from lumeasy import lumenv
from lumeasy import materials as MAT
from lumeasy import model as M
from lumeasy.gui.forms import FieldForm, NumEdit, fmt
from lumeasy.gui.sketch import SketchCanvas
from lumeasy.gui.widgets import ListEditor, MiniPlot, hint, title

F = M.F


def scroll_wrap(w):
    s = QScrollArea()
    s.setWidgetResizable(True)
    s.setFrameShape(QFrame.NoFrame)
    s.setWidget(w)
    return s


# ==========================================================================
# 1 專案
# ==========================================================================
class ProjectPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        v = QVBoxLayout(self)
        v.addWidget(title("1  專案設定"))
        v.addWidget(hint("設定檔名、存放位置、2D / 3D 與長度單位。之後每一頁的數字都以這裡選的單位顯示;"
                         "切換單位會自動換算,模型不會變。"))
        g = QGroupBox("基本")
        f = QFormLayout(g)
        self.name = QLineEdit()
        self.name.editingFinished.connect(self._name)
        f.addRow("專案 / 檔案名稱", self.name)
        row = QHBoxLayout()
        self.folder = QLineEdit()
        self.folder.editingFinished.connect(self._folder)
        b = QPushButton("選資料夾…")
        b.setToolTip("模型檔、腳本、結果都會存在這裡。路徑可以有中文(程式會自動處理)。")
        b.clicked.connect(self._pick_folder)
        b2 = QPushButton("開啟")
        b2.clicked.connect(lambda: self.win.open_path(self.win.p["project"]["folder"]))
        row.addWidget(self.folder, 1)
        row.addWidget(b)
        row.addWidget(b2)
        f.addRow("存放資料夾", row)
        self.dim = QComboBox()
        self.dim.addItem("3D(立體)", "3D")
        self.dim.addItem("2D(x-z 截面,沿 y 無限長)", "2D")
        self.dim.currentIndexChanged.connect(self._dim)
        f.addRow("模擬維度", self.dim)
        self.unit = QComboBox()
        self.unit.addItem("nm(奈米)", "nm")
        self.unit.addItem("µm(微米)", "um")
        self.unit.currentIndexChanged.connect(self._unit)
        f.addRow("長度單位", self.unit)
        self.out_hint = QLabel()
        self.out_hint.setWordWrap(True)
        f.addRow("會產生的檔案", self.out_hint)
        v.addWidget(g)
        g2 = QGroupBox("Lumerical 連線(只用官方 Python API;不碰授權與授權伺服器)")
        f2 = QFormLayout(g2)
        row2 = QHBoxLayout()
        self.lum = QComboBox()
        self.lum.setEditable(True)
        self.lum.currentTextChanged.connect(self._lum)
        b3 = QPushButton("選安裝資料夾…")
        b3.setToolTip("自動找不到 Lumerical 時,手動選安裝資料夾(例如 C:\\Program Files\\Lumerical\\v202)。")
        b3.clicked.connect(self._pick_lum)
        row2.addWidget(self.lum, 1)
        row2.addWidget(b3)
        f2.addRow("安裝位置", row2)
        row3 = QHBoxLayout()
        t = QPushButton("連線測試(並讀取內建材料清單)")
        t.setToolTip("在背景開一次 Lumerical(看不到視窗),確認連得上,並讀回這台電腦的內建材料清單。")
        t.setObjectName("primary")
        t.clicked.connect(self.win.probe)
        row3.addWidget(t)
        row3.addStretch(1)
        f2.addRow("", row3)
        self.lum_status = QLabel("")
        self.lum_status.setWordWrap(True)
        f2.addRow("狀態", self.lum_status)
        v.addWidget(g2)
        g3 = QGroupBox("備註(會存在專案檔裡)")
        vv = QVBoxLayout(g3)
        self.notes = QPlainTextEdit()
        self.notes.setFixedHeight(90)
        self.notes.textChanged.connect(self._notes)
        vv.addWidget(self.notes)
        v.addWidget(g3)
        v.addStretch(1)
        self._loading = False

    def refresh(self):
        self._loading = True
        pp = self.win.p["project"]
        self.name.setText(pp["name"])
        self.folder.setText(pp.get("folder", ""))
        self.dim.setCurrentIndex(0 if pp.get("dimension") != "2D" else 1)
        self.unit.setCurrentIndex(0 if pp.get("unit") != "um" else 1)
        self.lum.clear()
        found = lumenv.find_installs()
        for r in found:
            self.lum.addItem(r)
        cur = pp.get("lumerical_dir") or (found[0] if found else "")
        if cur and self.lum.findText(cur) < 0:
            self.lum.addItem(cur)
        self.lum.setCurrentText(cur)
        if not found and not cur:
            self.lum_status.setText("<span style='color:#c00'>找不到 Lumerical 安裝。請按「選安裝資料夾」"
                                    "(裡面要有 api\\python\\lumapi.py)。</span>")
        elif not self.lum_status.text():
            self.lum_status.setText(f"找到 {lumenv.version_label(cur)}:{cur}(按「連線測試」確認可以用)")
        self.notes.setPlainText(pp.get("notes", ""))
        self._out()
        self._loading = False

    def _out(self):
        pp = self.win.p["project"]
        fo = pp.get("folder") or "(還沒選資料夾)"
        n = pp["name"]
        self.out_hint.setText(f"{fo}\\{n}.fsp、{n}.lsf(Lumerical 腳本)、{n}_project.json、"
                              f"{n}_results\\(跑完的資料與圖)。同名時自動加 _01、_02,不會覆寫舊檔。")

    def _name(self):
        t = self.name.text().strip()
        if t and t != self.win.p["project"]["name"]:
            self.win.p["project"]["name"] = t
            self._out()
            self.win.changed()

    def _folder(self):
        if self._loading:
            return
        self.win.p["project"]["folder"] = self.folder.text().strip()
        self._out()
        self.win.changed()

    def _pick_folder(self):
        d = QFileDialog.getExistingDirectory(self, "選擇存放資料夾", self.win.p["project"].get("folder") or os.path.expanduser("~"))
        if d:
            self.folder.setText(os.path.normpath(d))
            self._folder()
            self.win.settings["last_folder"] = d

    def _dim(self):
        if self._loading:
            return
        self.win.set_dimension(self.dim.currentData())

    def _unit(self):
        if self._loading:
            return
        self.win.set_unit(self.unit.currentData())

    def _lum(self, t):
        if self._loading:
            return
        self.win.p["project"]["lumerical_dir"] = t.strip()
        self.win.changed(preview=False)

    def _pick_lum(self):
        d = QFileDialog.getExistingDirectory(self, "選 Lumerical 安裝資料夾(例如 C:\\Program Files\\Lumerical\\v202)")
        if d:
            try:
                r = lumenv.resolve_root(d)
            except FileNotFoundError as e:
                QMessageBox.warning(self, "不是 Lumerical 資料夾", str(e))
                return
            self.lum.setCurrentText(r)

    def _notes(self):
        if not self._loading:
            self.win.p["project"]["notes"] = self.notes.toPlainText()
            self.win.changed(preview=False)


# ==========================================================================
# 2 材料
# ==========================================================================
MAT_FIELDS = {
    "const_nk": [F("name", "名稱", "text"), F("n", "折射率 n", "float", 1.5), F("k", "消光係數 k", "float", 0.0, tip="> 0 = 吸收。"),
                 F("color", "顏色", "color", "#4C9BE8")],
    "const_eps": [F("name", "名稱", "text"), F("e1", "ε1(實部)", "float", 2.25, tip="介電常數實部;金屬是負的。"),
                  F("e2", "ε2(虛部)", "float", 0.0, tip="介電常數虛部;> 0 = 吸收。"), F("color", "顏色", "color", "#C0C4CC")],
    "file": [F("name", "名稱", "text"),
             F("fit_tol", "擬合容差", "float", 0.0, min=0, tip="0 = Lumerical 預設(0.1)。金屬或色散強的材料建議 0.001,擬合才貼近資料。"),
             F("max_coef", "最多擬合係數", "int", 0, min=0, max=64, tip="0 = Lumerical 預設(6)。金屬建議 12。"),
             F("color", "顏色", "color", "#59A14F")],
    "builtin_copy": [F("name", "新材料名稱", "text"), F("base", "複製哪一個內建材料", "builtin", "Al (Aluminium) - Palik"),
                     F("fit_tol", "擬合容差", "float", 0.001, min=0, tip="0 = 不改。建議 0.001。"),
                     F("max_coef", "最多擬合係數", "int", 12, min=0, max=64, tip="0 = 不改。建議 12。"),
                     F("color", "顏色", "color", "#C0C4CC")],
}


class ImportDialog(QDialog):
    """匯入 n,k 或 ε 檔:自動猜欄位,畫出 n、k 讓使用者確認。"""

    def __init__(self, win, path):
        super().__init__(win)
        self.win, self.path = win, path
        self.setWindowTitle("匯入材料檔")
        self.resize(900, 620)
        self.hdr, self.data, note = MAT.read_table(path)
        xu, yk, msg, sure = MAT.guess_format(self.hdr, self.data, os.path.basename(path))
        last = win.settings.get("last_import_format")
        if not sure and last:
            xu, yk = last
            msg += f"(這個檔沒有欄名,先套用你上次選的格式:{dict(MAT.X_UNITS)[xu]} / {dict(MAT.Y_KINDS)[yk]})"
        v = QVBoxLayout(self)
        v.addWidget(QLabel(f"<b>{os.path.basename(path)}</b> — {self.data.shape[0]} 列 × {self.data.shape[1]} 欄"))
        if note:
            v.addWidget(hint(note))
        self.msg = hint(msg)
        v.addWidget(self.msg)
        sp = QSplitter(Qt.Horizontal)
        left = QWidget()
        lf = QFormLayout(left)
        self.name = QLineEdit(os.path.splitext(os.path.basename(path))[0].replace(" ", "_")[:40])
        lf.addRow("材料名稱", self.name)
        self.xu = QComboBox()
        for k, lab in MAT.X_UNITS:
            self.xu.addItem(lab, k)
        self.xu.setCurrentIndex(self.xu.findData(xu))
        lf.addRow("第 1 欄是", self.xu)
        self.yk = QComboBox()
        for k, lab in MAT.Y_KINDS:
            self.yk.addItem(lab, k)
        self.yk.setCurrentIndex(self.yk.findData(yk))
        lf.addRow("第 2、3 欄是", self.yk)
        self.flip = QCheckBox("虛部全是負的時自動改正(另一種時間慣例)")
        self.flip.setChecked(True)
        lf.addRow("", self.flip)
        self.table = QTableWidget()
        n = min(12, self.data.shape[0])
        self.table.setRowCount(n)
        self.table.setColumnCount(self.data.shape[1])
        if self.hdr:
            self.table.setHorizontalHeaderLabels([str(h) for h in self.hdr])
        for i in range(n):
            for j in range(self.data.shape[1]):
                self.table.setItem(i, j, QTableWidgetItem(f"{self.data[i, j]:.6g}"))
        lf.addRow("前幾列", self.table)
        sp.addWidget(left)
        right = QWidget()
        rv = QVBoxLayout(right)
        self.plot = MiniPlot(3.6)
        rv.addWidget(self.plot)
        self.warn = hint("")
        rv.addWidget(self.warn)
        sp.addWidget(right)
        sp.setSizes([380, 500])
        v.addWidget(sp, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("匯入")
        bb.button(QDialogButtonBox.Cancel).setText("取消")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        for w in (self.xu, self.yk):
            w.currentIndexChanged.connect(self.update)
        self.flip.toggled.connect(self.update)
        self.result_mat = None
        self.update()

    def update(self, *_):
        try:
            if self.data.shape[1] < 3 and self.yk.currentData() != "n":
                self.yk.setCurrentIndex(self.yk.findData("n"))
            wl, n, k, notes = MAT.to_nk(self.data, self.xu.currentData(), self.yk.currentData(), self.flip.isChecked())
        except Exception as e:  # noqa: BLE001
            self.warn.setText(f"<span style='color:#c00'>{e}</span>")
            return
        self.wl, self.n, self.k = wl, n, k
        self.plot.plot_nk(wl, n, k, f"{wl.min():.0f} – {wl.max():.0f} nm,{len(wl)} 點")
        w = notes + MAT.sanity(wl, n, k)
        i = int(np.argmin(np.abs(wl - 550)))
        w.insert(0, f"在 {wl[i]:.0f} nm:n = {n[i]:.4g},k = {k[i]:.3g}(ε1 = {n[i] ** 2 - k[i] ** 2:.4g},ε2 = {2 * n[i] * k[i]:.3g})")
        self.warn.setText("<br>".join(w))

    def accept(self):
        if not hasattr(self, "wl"):
            return
        name = self.name.text().strip()
        if not name:
            QMessageBox.warning(self, "缺名稱", "請填材料名稱")
            return
        self.win.settings["last_import_format"] = [self.xu.currentData(), self.yk.currentData()]
        self.result_mat = {"name": name, "kind": "file", "src": self.path,
                           "x_unit": self.xu.currentData(), "y_kind": self.yk.currentData(),
                           "wl_nm": [float(x) for x in self.wl], "n": [float(x) for x in self.n],
                           "k": [float(x) for x in self.k], "fit_tol": 0.0, "max_coef": 0,
                           "color": MAT.DEFAULT_COLORS[len(self.win.p["materials"]) % len(MAT.DEFAULT_COLORS)]}
        super().accept()


class MaterialsPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        v = QVBoxLayout(self)
        v.addWidget(title("2  材料"))
        v.addWidget(hint("Lumerical 內建材料可以直接在「幾何」頁選。這裡加自己的材料:固定 n,k、固定 ε,或匯入頻譜檔"
                         "(n,k 或 ε 都可以,會自動換算成 Lumerical 要的複數介電常數 ε = (n + ik)²)。"))
        self.ed = ListEditor(win, lambda: self.win.p["materials"],
                             lambda m: MAT_FIELDS.get(m.get("kind"), MAT_FIELDS["const_nk"]),
                             self._label, [], on_change=self._changed, extra_for=self._extra,
                             new_name=lambda n: M.unique_name(self.win.p, n + "_copy"))
        menu = self.ed.add_btn.menu()
        menu.clear()
        menu.addAction("固定折射率 n, k", lambda: self._new("const_nk"))
        menu.addAction("固定介電常數 ε1, ε2", lambda: self._new("const_eps"))
        menu.addAction("從檔案匯入頻譜(n,k 或 ε)…", self.import_file)
        menu.addAction("複製 Lumerical 內建材料並調整擬合…", lambda: self._new("builtin_copy"))
        v.addWidget(self.ed, 3)
        row = QHBoxLayout()
        b = QPushButton("匯出選到的材料成檔案…")
        b.setToolTip("把選到的材料存成文字檔:可選 (nm, n, k)、(µm, n, k)、(THz, ε1, ε2)、(nm, ε1, ε2)。")
        b.clicked.connect(self.export)
        row.addWidget(b)
        b2 = QPushButton("從檔案匯入…")
        b2.setToolTip("讀 n,k 或 ε 的頻譜檔(txt / csv,也支援 refractiveindex.info 的格式),自動換算成 Lumerical 的材料。")
        b2.clicked.connect(self.import_file)
        row.addWidget(b2)
        row.addStretch(1)
        v.addLayout(row)
        conv = QGroupBox("n,k ⇄ ε 換算小工具")
        conv.setToolTip("改任一邊,另一邊自動換算:ε1 = n² − k²、ε2 = 2nk。")
        cg = QGridLayout(conv)
        self.cn, self.ck, self.ce1, self.ce2 = (NumEdit() for _ in range(4))
        for w, lab, c in ((self.cn, "n", 0), (self.ck, "k", 2), (self.ce1, "ε1", 4), (self.ce2, "ε2", 6)):
            cg.addWidget(QLabel(lab), 0, c)
            cg.addWidget(w, 0, c + 1)
        self.cn.setValue(1.5)
        self.ck.setValue(0)
        self.ce1.setValue(2.25)
        self.ce2.setValue(0)
        self.cn.valueChanged.connect(self._nk2e)
        self.ck.valueChanged.connect(self._nk2e)
        self.ce1.valueChanged.connect(self._e2nk)
        self.ce2.valueChanged.connect(self._e2nk)
        v.addWidget(conv)

    def _nk2e(self):
        e1, e2 = MAT.nk_to_eps(self.cn.value(), self.ck.value())
        self.ce1.setValue(float(e1))
        self.ce2.setValue(float(e2))

    def _e2nk(self):
        n, k = MAT.eps_to_nk(self.ce1.value(), self.ce2.value())
        self.cn.setValue(float(n))
        self.ck.setValue(float(k))

    def _label(self, m):
        kind = dict(MAT.MATERIAL_KINDS).get(m.get("kind"), "")
        if m.get("kind") == "const_nk":
            extra = f"n={fmt(m.get('n'))} k={fmt(m.get('k'))}"
        elif m.get("kind") == "const_eps":
            extra = f"ε={fmt(m.get('e1'))}{float(m.get('e2') or 0):+g}i"
        elif m.get("kind") == "file":
            extra = f"{len(m.get('wl_nm', []))} 點"
        else:
            extra = m.get("base", "")
        return f"{m['name']}   [{kind}] {extra}"

    def refresh(self):
        self.ed.refresh()

    def _new(self, kind):
        nm = M.unique_name(self.win.p, {"const_nk": "myMat", "const_eps": "myMetal", "builtin_copy": "copyMat"}[kind])
        m = M.defaults(MAT_FIELDS[kind])
        m.update(name=nm, kind=kind)
        m["color"] = MAT.DEFAULT_COLORS[len(self.win.p["materials"]) % len(MAT.DEFAULT_COLORS)]
        self.ed.add(m)

    def import_file(self):
        p, _ = QFileDialog.getOpenFileName(self, "選材料檔", self.win.settings.get("last_mat_dir", ""),
                                           "文字 / CSV (*.txt *.csv *.dat *.tsv *.nk);;所有檔案 (*.*)")
        if not p:
            return
        self.win.settings["last_mat_dir"] = os.path.dirname(p)
        try:
            d = ImportDialog(self.win, p)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "讀不了這個檔", str(e))
            return
        if d.exec() and d.result_mat:
            m = d.result_mat
            m["name"] = M.unique_name(self.win.p, m["name"]) if m["name"] in {x["name"] for x in self.win.p["materials"]} else m["name"]
            self.ed.add(m)
            self.win.log(f"匯入材料 {m['name']}:{len(m['wl_nm'])} 點,{min(m['wl_nm']):.0f}–{max(m['wl_nm']):.0f} nm")

    def export(self):
        m = self.ed.current()
        if m is None or m.get("kind") == "builtin_copy":
            QMessageBox.information(self, "匯出", "請先選一個自訂材料(內建材料的複本沒有資料可以匯出)。")
            return
        p, flt = QFileDialog.getSaveFileName(self, "匯出材料", m["name"] + ".txt",
                                             "波長 nm, n, k (*.txt);;波長 µm, n, k (*.txt);;頻率 THz, ε1, ε2 (*.txt);;波長 nm, ε1, ε2 (*.txt)")
        if not p:
            return
        fmt_ = {"波長 nm, n, k (*.txt)": "nm_nk", "波長 µm, n, k (*.txt)": "um_nk",
                "頻率 THz, ε1, ε2 (*.txt)": "THz_eps", "波長 nm, ε1, ε2 (*.txt)": "nm_eps"}.get(flt, "nm_nk")
        MAT.export_material(m, p, fmt_)
        self.win.log(f"已匯出 {p}")

    def _changed(self, m, key):
        if key == "name":
            old = getattr(self, "_old_name", None)
            for o in self.win.p["objects"]:
                if old and o.get("material") == old:
                    o["material"] = m["name"]
        self._old_name = m["name"]
        if key in ("n", "k", "e1", "e2"):
            self.ed.rebuild_form()

    def _extra(self, m):
        self._old_name = m["name"]
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        pl = MiniPlot(2.6)
        wl = np.linspace(float(self.win.p["global"]["wl_start"]), float(self.win.p["global"]["wl_stop"]), 200)
        if m.get("kind") == "file":
            W = np.asarray(m["wl_nm"])
            pl.plot_nk(W, m["n"], m["k"], f"資料範圍 {W.min():.0f}–{W.max():.0f} nm(模擬 {wl[0]:.0f}–{wl[-1]:.0f} nm)")
            v.addWidget(hint(f"來源:{m.get('src', '')}(資料已存進專案檔,原檔搬走也沒關係)"))
        elif m.get("kind") in ("const_nk", "const_eps"):
            nk = MAT.material_nk(m, wl)
            pl.plot_nk(wl, nk[0], nk[1], "固定值")
            if m.get("kind") == "const_eps":
                v.addWidget(hint(f"換算:n = {nk[0][0]:.5g},k = {nk[1][0]:.4g}"))
            else:
                e1, e2 = MAT.nk_to_eps(nk[0][0], nk[1][0])
                v.addWidget(hint(f"換算:ε1 = {float(e1):.5g},ε2 = {float(e2):.4g}"))
        else:
            pl.clear("內建材料的色散由 Lumerical 提供")
            v.addWidget(hint("內建金屬的預設擬合在可見光常常不好(例如 Al 在 400–750 nm 的 n 誤差可到 0.4)。"
                             "這裡複製一份,把擬合容差調到 0.001、最多係數 12,物件改用這個新名字。"))
        v.addWidget(pl)
        return w


# ==========================================================================
# 3 幾何
# ==========================================================================
def obj_label(o):
    sh = M.SHAPES.get(o.get("shape"), {}).get("label", o.get("shape"))
    tag = ""
    if o.get("material") == "etch":
        tag = "  〔挖孔〕"
    if not o.get("enabled", True):
        tag += "  (停用)"
    arr = ""
    if o.get("shape") in M.ARRAYABLE and (int(o.get("nx") or 1) > 1 or int(o.get("ny") or 1) > 1):
        arr = f" ×{int(o.get('nx') or 1)}×{int(o.get('ny') or 1)}"
    return f"{o['name']}  —  {sh}{arr}  ·  {o.get('material')}{tag}"


class GeometryPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        v = QVBoxLayout(self)
        v.addWidget(title("3  結構"))
        v.addWidget(hint("從原點 (0,0,0) 開始放物件;要疊上去就選「疊在…的頂面上」。挖孔 = 材料選 etch。"
                         "滑鼠移到任何欄位上會顯示說明。"))
        quick = QHBoxLayout()
        for txt, fn, tp in (("＋ 基板", self.add_substrate, "加一塊玻璃基板:頂面在 z = 0、往下 1 µm,x、y 自動貫穿模擬區。"),
                            ("＋ 薄膜", self.add_film, "加一層薄膜,疊在目前最後一個物件的頂面上,x、y 自動貫穿模擬區。"),
                            ("＋ 柱子陣列", self.add_pillars, "加一組 3 × 3 的圓柱陣列,疊在最後一個物件上(個數、週期可以改)。")):
            b = QPushButton(txt)
            b.setToolTip(tp)
            b.clicked.connect(fn)
            quick.addWidget(b)
        quick.addStretch(1)
        acts = [(f"{d['label']}", (lambda s=s: self._new(s))) for s, d in M.SHAPES.items()]
        self.ed = ListEditor(win, lambda: self.win.p["objects"], lambda o: M.tag_fields(M.object_fields(o["shape"]), "object"), obj_label,
                             acts, on_change=self._changed, extra_for=self._extra,
                             new_name=lambda n: M.unique_name(self.win.p, n))
        self.ed.selectionChanged.connect(lambda o: self.win.set_selected(o.get("name") if o else None))
        tab1 = QWidget()
        t1 = QVBoxLayout(tab1)
        t1.setContentsMargins(0, 6, 0, 0)
        t1.addLayout(quick)
        t1.addWidget(self.ed, 1)
        from PySide6.QtWidgets import QTabWidget
        self.tabs = QTabWidget()
        self.tabs.addTab(tab1, "輸入尺寸")
        self.sketch = SketchPage(win, embedded=True)
        self.tabs.addTab(self.sketch, "草圖畫圖")
        self.tabs.setTabToolTip(0, "用數字描述每個物件(長寬高、半徑、頂點…),清單裡的順序 = 建模順序。")
        self.tabs.setTabToolTip(1, "像 Onshape:在格子上畫矩形 / 圓 / 多邊形,再擠出或挖孔。")
        self.tabs.currentChanged.connect(lambda _=None: self.refresh())
        v.addWidget(self.tabs, 1)

    def refresh(self):
        if self.tabs.currentIndex() == 1:
            self.sketch.refresh()
        else:
            self.ed.refresh()

    def _new(self, shape):
        base = {"box": "box", "cylinder": "pillar", "ellipse": "ellipse", "ring": "ring", "sphere": "sphere",
                "pyramid": "taper", "regpoly": "hexagon", "polygon": "poly", "stl": "stl", "gds": "gds", "dxf": "dxf"}[shape]
        o = M.new_object(shape, M.unique_name(self.win.p, base))
        if self.win.p["objects"]:
            o["on_top"] = ""
        return o

    def add_substrate(self):
        o = M.new_object("box", M.unique_name(self.win.p, "substrate"))
        o.update(material="SiO2 (Glass) - Palik", H=1000.0 if self.win.unit() == "nm" else 2000.0, dz=-1000.0, through=True)
        self.win.p["objects"].insert(0, o)
        self.ed.refresh()
        self.ed.select_name(o["name"])
        self.win.changed()

    def add_film(self):
        o = M.new_object("box", M.unique_name(self.win.p, "film"))
        o.update(material="Si3N4 (Silicon Nitride) - Phillip", H=100.0, through=True,
                 on_top="@prev" if self.win.p["objects"] else "")
        self.ed.add(o)

    def add_pillars(self):
        o = M.new_object("cylinder", M.unique_name(self.win.p, "pillars"))
        o.update(r=80.0, H=300.0, nx=3, ny=3, px=400.0, py=400.0, on_top="@prev" if self.win.p["objects"] else "")
        self.ed.add(o)

    def _changed(self, o, key):
        if key == "name":
            old = getattr(self, "_old_name", None)
            if old and old != o["name"]:
                for x in self.win.p["objects"]:
                    if x.get("on_top") == old:
                        x["on_top"] = o["name"]
                for m in self.win.p["mesh"]:
                    if m.get("target") == old:
                        m["target"] = o["name"]
            self._old_name = o["name"]
            self.win.set_selected(o["name"])
        if key in ("file", "file_unit", "layer", "cell"):
            self.ed.rebuild_form()

    def _extra(self, o):
        self._old_name = o["name"]
        if o["shape"] not in M.CAD_SHAPES:
            return None
        w = QGroupBox("CAD 檔案資訊")
        v = QVBoxLayout(w)
        v.addWidget(hint("一個 CAD 物件只能有一種材料:不同材料的零件請分成不同檔案(STL)或不同圖層(GDS / DXF)各建一個物件。"
                         "2D 模擬時 GDS / DXF 的多邊形直接當成 x-z 截面。"))
        f = o.get("file")
        if not f or not os.path.exists(f):
            v.addWidget(hint("還沒選檔案,或檔案不存在。"))
            return w
        try:
            if o["shape"] == "stl":
                from lumeasy import cadio
                vtx = cadio.read_stl(f)
                ext = vtx.max(0) - vtx.min(0)
                v.addWidget(hint(f"{len(vtx) // 3} 個三角形;檔案座標範圍 {fmt(ext[0])} × {fmt(ext[1])} × {fmt(ext[2])}(檔案單位)"))
                v.addWidget(self._unit_buttons(o, ext))
            elif o["shape"] == "gds":
                from lumeasy import cadio
                info = cadio.gds_info(f)
                v.addWidget(hint("Cell 與圖層(點一下套用):"))
                g = QGridLayout()
                r = 0
                for cell, lays in list(info.items())[:12]:
                    g.addWidget(QLabel(cell), r, 0)
                    col = 1
                    for (L, D) in lays[:10]:
                        b = QPushButton(f"{L}:{D}")
                        b.clicked.connect(lambda _=None, cell=cell, L=L, D=D: self._set_gds(o, cell, f"{L}:{D}"))
                        g.addWidget(b, r, col)
                        col += 1
                    r += 1
                v.addLayout(g)
                polys = M.cad_polygons(o, 1.0)
                if polys:
                    xs = [x for p in polys for x, _ in p]
                    ys = [y for p in polys for _, y in p]
                    v.addWidget(hint(f"這個圖層有 {len(polys)} 個多邊形,範圍 {fmt((max(xs) - min(xs)) / M.UNIT_NM[self.win.unit()])} × "
                                     f"{fmt((max(ys) - min(ys)) / M.UNIT_NM[self.win.unit()])} {self.win.unit_label()}(GDS 自帶單位,不用選)"))
            else:
                from lumeasy import cadio
                lays = cadio.dxf_layers(f)
                row = QHBoxLayout()
                row.addWidget(QLabel("圖層:"))
                for L in lays[:12]:
                    b = QPushButton(L)
                    b.clicked.connect(lambda _=None, L=L: self._set_layer(o, L))
                    row.addWidget(b)
                row.addStretch(1)
                v.addLayout(row)
                polys = M.cad_polygons(o, 1.0)
                if polys:
                    xs = [x for p in polys for x, _ in p]
                    ys = [y for p in polys for _, y in p]
                    span = np.array([max(xs) - min(xs), max(ys) - min(ys), 0.0]) / M.FILE_UNIT_NM[o.get("file_unit", "um")]
                    v.addWidget(hint(f"找到 {len(polys)} 個封閉形狀"))
                    v.addWidget(self._unit_buttons(o, span))
                else:
                    v.addWidget(hint("這個圖層沒有封閉的多段線 / 圓。"))
        except Exception as e:  # noqa: BLE001
            v.addWidget(hint(f"<span style='color:#c00'>讀檔失敗:{e}</span>"))
        return w

    def _unit_buttons(self, o, ext_file_units):
        """一鍵換單位:列出每種單位解讀下的實際尺寸。"""
        box = QWidget()
        g = QGridLayout(box)
        g.setContentsMargins(0, 0, 0, 0)
        g.addWidget(QLabel("<b>檔案單位一鍵切換</b>(看哪一個尺寸才對):"), 0, 0, 1, 3)
        u = self.win.unit()
        for i, (key, lab) in enumerate((("nm", "nm"), ("um", "µm"), ("mm", "mm"), ("m", "m"))):
            sz = [e * M.FILE_UNIT_NM[key] / M.UNIT_NM[u] for e in ext_file_units]
            txt = " × ".join(fmt(s) for s in sz if s) + f" {self.win.unit_label()}"
            b = QPushButton(f"當成 {lab}")
            b.setCheckable(True)
            b.setChecked(o.get("file_unit") == key)
            b.clicked.connect(lambda _=None, key=key: self._set_unit(o, key))
            g.addWidget(b, i + 1, 0)
            g.addWidget(QLabel(f"→ 尺寸 {txt}"), i + 1, 1)
        return box

    def _set_unit(self, o, key):
        o["file_unit"] = key
        self.ed.rebuild_form()
        self.win.changed()

    def _set_gds(self, o, cell, layer):
        o["cell"], o["layer"] = cell, layer
        self.ed.rebuild_form()
        self.win.changed()

    def _set_layer(self, o, L):
        o["layer"] = L
        self.ed.rebuild_form()
        self.win.changed()


# ==========================================================================
# 3b 草圖
# ==========================================================================
class SketchPage(QWidget):
    def __init__(self, win, embedded=False):
        super().__init__()
        self.win = win
        v = QVBoxLayout(self)
        if embedded:
            v.setContentsMargins(0, 6, 0, 0)
        else:
            v.addWidget(title("草圖建模(畫在格子上 → 擠出 / 挖孔)"))
        self.help = hint("")
        v.addWidget(self.help)
        bar = QHBoxLayout()
        self.tools = QButtonGroup(self)
        for i, (key, txt) in enumerate((("select", "選取 / 拖曳移動"), ("rect", "矩形"), ("circle", "圓形"),
                                        ("polygon", "多邊形"))):
            b = QToolButton()
            b.setText(txt)
            b.setCheckable(True)
            b.setObjectName("tool")
            if i == 1:
                b.setChecked(True)
            self.tools.addButton(b, i)
            b.setToolTip({"select": "點形狀選取(右邊會出現它的數字);按住拖曳可以移動。",
                          "rect": "按住拖曳畫矩形。", "circle": "從圓心按住拖曳到半徑。",
                          "polygon": "逐點點擊;點回第一點、雙擊或按 Enter 完成;Backspace 刪最後一點、Esc 取消。"}[key])
            b.clicked.connect(lambda _=None, key=key: self.canvas.set_tool(key))
            bar.addWidget(b)
        bar.addSpacing(12)
        bar.addWidget(QLabel("格點"))
        self.grid = NumEdit(minimum=0.001)
        self.grid.setFixedWidth(70)
        self.grid.valueChanged.connect(self._grid)
        bar.addWidget(self.grid)
        self.grid_unit = QLabel("nm")
        bar.addWidget(self.grid_unit)
        self.snap = QCheckBox("吸附格點")
        self.snap.setToolTip("畫圖時座標自動對齊到最近的格點。")
        self.snap.setChecked(True)
        self.snap.toggled.connect(lambda c: setattr(self.canvas, "snap", c))
        bar.addWidget(self.snap)
        fit = QPushButton("全部顯示")
        fit.setToolTip("把整個模擬區縮放到畫面裡。")
        fit.clicked.connect(lambda: self.canvas.fit(self.win.p))
        bar.addWidget(fit)
        bar.addStretch(1)
        self.cursor = QLabel("")
        bar.addWidget(self.cursor)
        v.addLayout(bar)
        bar2 = QHBoxLayout()
        self.plane_lab = QLabel("草圖平面")
        bar2.addWidget(self.plane_lab)
        self.plane = QComboBox()
        self.plane.setMinimumWidth(190)
        self.plane.setToolTip("畫在哪個高度:z = 0、某個物件的頂面(會綁在那個物件上),或自訂高度。")
        self.plane.currentIndexChanged.connect(self._plane_changed)
        bar2.addWidget(self.plane)
        self.plane_z = NumEdit()
        self.plane_z.setFixedWidth(80)
        self.plane_z.valueChanged.connect(self._plane_changed)
        bar2.addWidget(self.plane_z)
        self.plane_zu = QLabel("nm")
        bar2.addWidget(self.plane_zu)
        bar2.addSpacing(14)
        bar2.addWidget(QLabel("畫完後"))
        self.op = QComboBox()
        self.op.setToolTip("擠出 = 從草圖平面往上長出一個柱;挖孔 = 往下挖掉(放一個 etch、優先順序 1 的同形狀物件)。")
        self.op.addItem("擠出(長出材料)", "extrude")
        self.op.addItem("挖孔(往下挖掉)", "cut")
        self.op.currentIndexChanged.connect(self._op_changed)
        bar2.addWidget(self.op)
        self.h_lab = QLabel("高度")
        bar2.addWidget(self.h_lab)
        self.height = NumEdit(minimum=0)
        self.height.setFixedWidth(80)
        bar2.addWidget(self.height)
        self.h_unit = QLabel("nm")
        bar2.addWidget(self.h_unit)
        bar2.addWidget(QLabel("材料"))
        self.mat = QComboBox()
        self.mat.setMinimumWidth(200)
        bar2.addWidget(self.mat)
        bar2.addStretch(1)
        v.addLayout(bar2)
        sp = QSplitter(Qt.Horizontal)
        self.canvas = SketchCanvas()
        self.canvas.set_tool("rect")
        self.canvas.shapeDrawn.connect(self._drawn)
        self.canvas.objectClicked.connect(self._clicked)
        self.canvas.objectMoved.connect(self._moved)
        self.canvas.cursorMoved.connect(self._cursor)
        sp.addWidget(self.canvas)
        self.side = QScrollArea()
        self.side.setWidgetResizable(True)
        self.side.setFrameShape(QFrame.NoFrame)
        sp.addWidget(self.side)
        sp.setSizes([700, 420])
        v.addWidget(sp, 1)
        self.height.setValue(200)
        self.grid.setValue(50)
        self._sel = None
        self._fitted = False

    def refresh(self):
        u = self.win.unit_label()
        fac = M.UNIT_NM[self.win.unit()]
        for lab in (self.grid_unit, self.plane_zu, self.h_unit):
            lab.setText(u)
        self.canvas.grid = self.grid.value() * fac
        d2 = M.is2d(self.win.p)
        for w in (self.plane_lab, self.plane, self.plane_z, self.plane_zu):
            w.setVisible(not d2)
        self.h_lab.setVisible(not d2)
        self.height.setVisible(not d2)
        self.h_unit.setVisible(not d2)
        self.help.setText(("2D:畫布就是 x-z 截面。" if d2 else "3D:畫布是俯視 x-y,先選草圖平面。")
                          + "畫好形狀後依上面的設定擠出或挖孔。滾輪縮放、右鍵拖曳平移;滑鼠停在按鈕上看詳細說明。")
        self.help.setToolTip("Lumerical 沒有布林減法:「挖孔」= 放一個材料 etch(背景折射率)、網格優先順序 1 的同形狀物件蓋過去。<br>"
                             "選「某物件的頂面」當草圖平面時,新物件會綁在那個物件上,之後改它的高度,上面的東西會跟著移動。<br>"
                             "多邊形:逐點點擊,點回第一點 / 雙擊 / Enter 完成,Backspace 刪最後一點,Esc 取消。")
        cur = self.plane.currentData()
        self.plane.blockSignals(True)
        self.plane.clear()
        self.plane.addItem("z = 0(原點高度)", "")
        for o in self.win.p["objects"]:
            if o.get("enabled", True):
                self.plane.addItem(f"{o['name']} 的頂面", o["name"])
        self.plane.addItem("自訂高度 z =", "@z")
        i = self.plane.findData(cur)
        self.plane.setCurrentIndex(max(i, 0))
        self.plane.blockSignals(False)
        self.plane_z.setVisible(not d2 and self.plane.currentData() == "@z")
        custom, builtin = self.win.materials()
        curm = self.mat.currentData()
        self.mat.blockSignals(True)
        self.mat.clear()
        for n in custom:
            self.mat.addItem("★ " + n, n)
        for n in builtin:
            if n != "etch":
                self.mat.addItem(n, n)
        i = self.mat.findData(curm)
        if i < 0:
            i = self.mat.findData("Si3N4 (Silicon Nitride) - Phillip")
        self.mat.setCurrentIndex(max(i, 0))
        self.mat.blockSignals(False)
        self._op_changed()
        self.redraw()
        if not self._fitted:
            self.canvas.fit(self.win.p)
            self._fitted = True

    def _op_changed(self, *_):
        cut = self.op.currentData() == "cut"
        self.h_lab.setText("深度" if cut else "高度")
        self.mat.setEnabled(not cut)
        if M.is2d(self.win.p):
            self.op.setItemText(0, "加材料")
            self.op.setItemText(1, "挖孔(挖掉)")
        else:
            self.op.setItemText(0, "擠出(長出材料)")
            self.op.setItemText(1, "挖孔(往下挖掉)")

    def plane_level(self):
        """回傳 (on_top 參照, 偏移 z(nm), 平面實際高度 nm)。"""
        ref = self.plane.currentData()
        if ref == "@z":
            z = self.plane_z.value() * M.UNIT_NM[self.win.unit()]
            return "", z, z
        if ref:
            try:
                for r in M.place_objects(self.win.p):
                    if r["obj"]["name"] == ref and not r["error"]:
                        return ref, 0.0, r["bbox"][5]
            except Exception:  # noqa: BLE001
                pass
        return "", 0.0, 0.0

    def _plane_changed(self, *_):
        self.plane_z.setVisible(not M.is2d(self.win.p) and self.plane.currentData() == "@z")
        self.redraw()

    def _grid(self):
        self.canvas.grid = self.grid.value() * M.UNIT_NM[self.win.unit()]
        self.canvas.viewport().update()

    def redraw(self):
        z = None if M.is2d(self.win.p) else self.plane_level()[2]
        self.canvas.load(self.win.p, plane_z=z, selected=self._sel)

    def _cursor(self, x, y):
        fac = M.UNIT_NM[self.win.unit()]
        self.cursor.setText(f"x = {fmt(x / fac)},{'z' if M.is2d(self.win.p) else 'y'} = {fmt(y / fac)} {self.win.unit_label()}")

    def _drawn(self, kind, data):
        p = self.win.p
        d2 = M.is2d(p)
        cut = self.op.currentData() == "cut"
        H = self.height.value() * M.UNIT_NM[self.win.unit()]
        mat = "etch" if cut else (self.mat.currentData() or "etch")
        ref, z_off, _ = self.plane_level() if not d2 else ("", 0.0, 0.0)
        if kind == "rect":
            x0, y0, x1, y1 = data
            o = M.new_object("box", M.unique_name(p, "hole" if cut else "block"))
            if d2:
                o.update(Lx=x1 - x0, H=y1 - y0, dx=(x0 + x1) / 2, dz=y0)
            else:
                o.update(Lx=x1 - x0, Ly=y1 - y0, dx=(x0 + x1) / 2, dy=(y0 + y1) / 2, H=H)
        elif kind == "circle":
            cx, cy, r = data
            if d2:
                o = M.new_object("sphere", M.unique_name(p, "hole" if cut else "rod"))
                o.update(r=r, dx=cx, dz=cy, anchor="center")
            else:
                o = M.new_object("cylinder", M.unique_name(p, "hole" if cut else "pillar"))
                o.update(r=r, dx=cx, dy=cy, H=H)
        else:
            o = M.new_object("polygon", M.unique_name(p, "hole" if cut else "shape"))
            from lumeasy.gui.forms import vertices_text
            o.update(vertices=vertices_text(data), anchor="file", dx=0.0, dy=0.0, dz=0.0, H=H)
        o["material"] = mat
        if not d2:
            o["on_top"] = ref
            o["dz"] = z_off - H if cut else z_off
        if cut:
            o["mesh_order"] = 1
        p["objects"].append(o)
        self._sel = o["name"]
        self.win.changed()
        self.win.set_selected(o["name"])
        self.redraw()
        self._show_form()
        self.win.log(f"草圖 → 新增 {o['name']}({M.SHAPES[o['shape']]['label']},{'挖孔' if cut else mat})")

    def _clicked(self, name):
        self._sel = name
        self.win.set_selected(name)
        self.redraw()
        self._show_form()

    def _moved(self, name, dx, dy):
        for o in self.win.p["objects"]:
            if o["name"] == name:
                o["dx"] = float(o.get("dx") or 0) + dx
                if M.is2d(self.win.p):
                    o["dz"] = float(o.get("dz") or 0) + dy
                else:
                    o["dy"] = float(o.get("dy") or 0) + dy
                break
        self._sel = name
        self.win.changed()
        self.redraw()
        self._show_form()

    def _show_form(self):
        o = next((x for x in self.win.p["objects"] if x["name"] == self._sel), None)
        w = QWidget()
        v = QVBoxLayout(w)
        if o is None:
            v.addWidget(hint("點一個形狀(選取工具)就能在這裡改它的數字。"))
        else:
            v.addWidget(QLabel(f"<b>{o['name']}</b>"))
            form = FieldForm(M.tag_fields(M.object_fields(o["shape"]), "object"), o, self.win, lambda k, o=o: self._form_changed(o, k))
            v.addWidget(form)
            b = QPushButton("刪除這個物件")
            b.clicked.connect(lambda: self._delete(o))
            v.addWidget(b)
        v.addStretch(1)
        self.side.setWidget(w)

    def _form_changed(self, o, k):
        if k == "name":
            old = self._sel
            for x in self.win.p["objects"]:
                if x.get("on_top") == old:
                    x["on_top"] = o["name"]
            self._sel = o["name"]
            self.win.set_selected(o["name"])
        self.win.changed()
        self.redraw()

    def _delete(self, o):
        self.win.p["objects"].remove(o)
        self._sel = None
        self.win.changed()
        self.redraw()
        self._show_form()


# ==========================================================================
# 4 光源
# ==========================================================================
class SourcePage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        v = QVBoxLayout(self)
        v.addWidget(title("4  光源與波長"))
        v.addWidget(hint("波長範圍是全域的:所有光源與監視器共用。光源範圍勾「自動」= 比模擬區再大一點(平面波一定要蓋滿)。"))
        g = QGroupBox("全域波長")
        gv = QVBoxLayout(g)
        self.gform_box = gv
        v.addWidget(g)
        acts = [(d["label"], (lambda t=t: M.new_source(t, M.unique_name(self.win.p, t)))) for t, d in M.SOURCE_TYPES.items()]
        self.ed = ListEditor(win, lambda: self.win.p["sources"], lambda s: M.tag_fields(M.source_fields(s["type"]), "source", s["type"]),
                             lambda s: f"{s['name']}  —  {M.SOURCE_TYPES[s['type']]['label']}" + ("" if s.get("enabled", True) else "  (停用)"),
                             acts, new_name=lambda n: M.unique_name(self.win.p, n))
        v.addWidget(self.ed, 1)
        self.gform = None

    def refresh(self):
        if self.gform is not None:
            self.gform.setParent(None)
        self.gform = FieldForm(M.tag_fields(M.GLOBAL_FIELDS, "global"), self.win.p["global"], self.win, lambda k: self.win.changed())
        self.gform_box.addWidget(self.gform)
        self.ed.refresh()


# ==========================================================================
# 5 模擬區
# ==========================================================================
class RegionPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        outer = QVBoxLayout(self)
        outer.addWidget(title("5  FDTD 模擬區、邊界與網格"))
        outer.addWidget(hint("範圍選「自動」= 物件包圍盒 + 邊距(貫穿模擬區的基板 / 薄膜不算在橫向範圍內)。"
                             "週期結構:x、y 選手動、範圍填週期、邊界選週期(斜入射用 Bloch)。"))
        sp = QSplitter(Qt.Horizontal)
        left = QWidget()
        self.lv = QVBoxLayout(left)
        self.readout = QLabel()
        self.readout.setWordWrap(True)
        self.readout.setObjectName("readout")
        self.lv.addWidget(self.readout)
        self.form_holder = QVBoxLayout()
        self.lv.addLayout(self.form_holder)
        self.lv.addStretch(1)
        sp.addWidget(scroll_wrap(left))
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.addWidget(QLabel("<b>網格覆寫區</b>(在細小結構附近加密網格)"))
        self.ed = ListEditor(win, lambda: self.win.p["mesh"], lambda m: M.tag_fields(M.MESH_FIELDS, "mesh"),
                             lambda m: f"{m['name']}  —  " + (f"包住 {m['target']}" if m.get("target") else "手動範圍") +
                                       f"  dx={fmt(m['dx'] / M.UNIT_NM[self.win.unit()])}",
                             [("網格覆寫", lambda: dict(M.defaults(M.MESH_FIELDS), name=M.unique_name(self.win.p, "mesh")))],
                             new_name=lambda n: M.unique_name(self.win.p, n))
        rv.addWidget(self.ed, 1)
        self.est = QLabel()
        self.est.setWordWrap(True)
        self.est.setObjectName("readout")
        rv.addWidget(self.est)
        sp.addWidget(right)
        sp.setSizes([520, 480])
        outer.addWidget(sp, 1)
        self.form = None

    def refresh(self):
        if self.form is not None:
            self.form.setParent(None)
        self.form = FieldForm(M.tag_fields(M.REGION_FIELDS, "region"), self.win.p["region"], self.win, lambda k: self._changed(k))
        self.form_holder.addWidget(self.form)
        self.ed.refresh()
        self.update_readout()

    def _changed(self, k):
        self.win.changed()
        self.update_readout()

    def update_readout(self):
        from lumeasy import estimate
        p = self.win.p
        s = 1 / M.UNIT_NM[self.win.unit()]
        u = self.win.unit_label()
        try:
            reg = M.compute_region(p)
            txt = "<b>目前模擬區</b>:" + ",".join(
                f"{a} {fmt(reg[a][0] * s)} … {fmt(reg[a][1] * s)}(寬 {fmt((reg[a][1] - reg[a][0]) * s)})"
                for a in (("x", "z") if M.is2d(p) else ("x", "y", "z"))) + f" {u}"
        except Exception as e:  # noqa: BLE001
            txt = f"<span style='color:#c00'>{e}</span>"
        self.readout.setText(txt)
        try:
            e = estimate.estimate(p)
            col = "#c00" if e["total_gb"] > 0.6 * e["free_gb"] else "#060"
            self.est.setText(f"<b>粗估</b>:網格約 {e['cells'] / 1e6:.3g} 百萬格(最小格 ≈ {e['dx_min_nm']:.3g} nm),"
                             f"記憶體約 <span style='color:{col}'>{e['total_gb']:.2g} GB</span>"
                             f"(監視器 {e['mon_gb']:.2g} GB),目前可用 {e['free_gb']:.1f} GB。"
                             f"超過可用的 6 成時,Lumerical 在背景會卡在看不到的記憶體不足視窗。")
        except Exception as ex:  # noqa: BLE001
            self.est.setText(f"估計失敗:{ex}")


# ==========================================================================
# 6 監視器
# ==========================================================================
class MonitorPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        v = QVBoxLayout(self)
        v.addWidget(title("6  監視器(要記錄哪裡的光)"))
        v.addWidget(hint("點下面的按鈕直接放一個常用監視器(位置以原點為參考,可以再改);"
                         "範圍勾「自動」= 蓋滿整個模擬區。要記錄的電場 / 磁場分量用勾選的。"))
        g = QGroupBox("一鍵新增")
        grid = QGridLayout(g)
        presets = [("上方(反射)", "top"), ("下方(穿透)", "bottom"), ("左側 x−", "left"), ("右側 x+", "right"),
                   ("前方 y−", "front"), ("後方 y+", "back"), ("XY 水平截面(場圖)", "xy"), ("XZ 直立截面(場圖)", "xz"),
                   ("YZ 直立截面(場圖)", "yz"), ("點(單點頻譜)", "point"), ("封閉盒(六面,算總功率)", "box"),
                   ("折射率 XZ(檢查結構)", "index"), ("時域點(看共振)", "time"), ("動畫 XZ", "movie")]
        mtips = {"top": "放在結構上方、光源再上面一點的水平面:量反射率。", "bottom": "放在結構下方的水平面:量穿透率。",
                 "left": "x 負方向邊上的直立面:量往左漏出的光。", "right": "x 正方向邊上的直立面:量往右漏出的光。",
                 "front": "y 負方向的直立面。", "back": "y 正方向的直立面。",
                 "xy": "穿過結構中間的水平截面:看電場 / 磁場分布(場圖)。", "xz": "y = 0 的直立截面:看光怎麼穿過結構(場圖)。",
                 "yz": "x = 0 的直立截面(場圖)。", "point": "單一點:看那一點的頻譜。",
                 "box": "六個面圍住所有物件:算散射 / 總輸出功率(各面只蓋到盒子為止,斜射的光不會算兩次)。",
                 "index": "折射率截面:跑完畫出 Lumerical 實際用的折射率分布,檢查結構有沒有建對。",
                 "time": "時域點:記錄場隨時間變化,看共振衰減。", "movie": "存成動畫(只在 Lumerical 裡看)。"}
        for i, (lab, key) in enumerate(presets):
            b = QPushButton(lab)
            b.setToolTip(mtips.get(key, ""))
            b.clicked.connect(lambda _=None, key=key: self.add_preset(key))
            grid.addWidget(b, i // 5, i % 5)
            if key in ("front", "back", "yz", "xy"):
                b.setProperty("only3d", True)
        self.preset_box = g
        v.addWidget(g)
        self.ed = ListEditor(win, lambda: self.win.p["monitors"], lambda m: M.tag_fields(M.MONITOR_FIELDS, "monitor"),
                             self._label, [("自訂監視器", lambda: M.new_monitor(M.unique_name(self.win.p, "monitor")))],
                             new_name=lambda n: M.unique_name(self.win.p, n))
        v.addWidget(self.ed, 1)

    def _label(self, m):
        k = dict(M.MON_KINDS)[m["kind"]].split("(")[0]
        o = dict(M.MON_ORIENTS)[m["orient"]].split("(")[0]
        s = 1 / M.UNIT_NM[self.win.unit()]
        return f"{m['name']}  —  {k} · {o} · z={fmt(float(m['z']) * s)}" + ("" if m.get("enabled", True) else "  (停用)")

    def refresh(self):
        d2 = M.is2d(self.win.p)
        for b in self.preset_box.findChildren(QPushButton):
            b.setVisible(not (d2 and b.property("only3d")))
        self.ed.refresh()

    def add_preset(self, key):
        p = self.win.p
        placed = M.place_objects(p)
        reg = M.compute_region(p, placed)
        top, bot = M.struct_top(p, placed), M.struct_bottom(p, placed)
        z_src = max((float(s["z"]) for s in p["sources"] if s.get("enabled", True) and s.get("axis", "z") == "z"), default=None)
        zt = reg["z"][1] - 0.15 * (reg["z"][1] - top) if reg["z"][1] > top else reg["z"][1]
        if z_src is not None and zt <= z_src:
            zt = (z_src + reg["z"][1]) / 2
        zb = reg["z"][0] + 0.3 * max(bot - reg["z"][0], 0)
        zc = (top + bot) / 2
        cx, cy = sum(reg["x"]) / 2, sum(reg["y"]) / 2
        ix = 0.1 * (reg["x"][1] - reg["x"][0])
        iy = 0.1 * (reg["y"][1] - reg["y"][0])
        new = []
        U = lambda n: M.unique_name(p, n)  # noqa: E731
        allf = list(M.FIELD_OUTPUTS)
        if key == "top":
            new.append(M.new_monitor(U("R_top"), kind="power", orient="z", x=cx, y=cy, z=zt, plot_field=False))
        elif key == "bottom":
            new.append(M.new_monitor(U("T_bottom"), kind="power", orient="z", x=cx, y=cy, z=zb, plot_field=False))
        elif key == "left":
            new.append(M.new_monitor(U("left"), kind="power", orient="x", x=reg["x"][0] + ix, y=cy, z=sum(reg["z"]) / 2, plot_field=False))
        elif key == "right":
            new.append(M.new_monitor(U("right"), kind="power", orient="x", x=reg["x"][1] - ix, y=cy, z=sum(reg["z"]) / 2, plot_field=False))
        elif key == "front":
            new.append(M.new_monitor(U("front"), kind="power", orient="y", x=cx, y=reg["y"][0] + iy, z=sum(reg["z"]) / 2, plot_field=False))
        elif key == "back":
            new.append(M.new_monitor(U("back"), kind="power", orient="y", x=cx, y=reg["y"][1] - iy, z=sum(reg["z"]) / 2, plot_field=False))
        elif key == "xy":
            new.append(M.new_monitor(U("field_XY"), kind="profile", orient="z", x=cx, y=cy, z=zc, outputs=allf, plot_spectrum=False))
        elif key == "xz":
            new.append(M.new_monitor(U("field_XZ"), kind="profile", orient="y", x=cx, y=cy, z=sum(reg["z"]) / 2, outputs=allf, plot_spectrum=False))
        elif key == "yz":
            new.append(M.new_monitor(U("field_YZ"), kind="profile", orient="x", x=cx, y=cy, z=sum(reg["z"]) / 2, outputs=allf, plot_spectrum=False))
        elif key == "point":
            new.append(M.new_monitor(U("point"), kind="power", orient="point", x=cx, y=cy, z=zc, plot_spectrum=False))
        elif key == "index":
            new.append(M.new_monitor(U("index_XZ"), kind="index", orient="y", x=cx, y=cy, z=sum(reg["z"]) / 2, plot_spectrum=False))
        elif key == "time":
            new.append(M.new_monitor(U("time"), kind="time", orient="point", x=cx, y=cy, z=zc, plot_spectrum=False, plot_field=False))
        elif key == "movie":
            new.append(M.new_monitor(U("movie"), kind="movie", orient="y", x=cx, y=cy, z=sum(reg["z"]) / 2, plot_spectrum=False, plot_field=False))
        elif key == "box":
            # 封閉盒:各面只蓋到盒子為止,斜射的光才不會被算兩次
            b = [r["bbox"] for r in placed if r["enabled"] and not r["error"] and not r["through"]]
            if not b:
                QMessageBox.information(self, "封閉盒", "要先有一個(不是貫穿基板的)物件,盒子會包住所有物件。")
                return
            x0 = min(q[0] for q in b) - ix
            x1 = max(q[1] for q in b) + ix
            y0 = min(q[2] for q in b) - iy
            y1 = max(q[3] for q in b) + iy
            z0 = min(q[4] for q in b) - 0.05 * (reg["z"][1] - reg["z"][0])
            z1 = max(q[5] for q in b) + 0.05 * (reg["z"][1] - reg["z"][0])
            xc, yc, zc2 = (x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2
            sx, sy, sz = x1 - x0, y1 - y0, z1 - z0
            fs = dict(kind="power", plot_field=False, outputs=["Px", "Py", "Pz", "power"])
            new += [M.new_monitor(U("box_top"), orient="z", x=xc, y=yc, z=z1, sx=sx, sy=sy, **fs),
                    M.new_monitor(U("box_bot"), orient="z", x=xc, y=yc, z=z0, sx=sx, sy=sy, **fs),
                    M.new_monitor(U("box_xmin"), orient="x", x=x0, y=yc, z=zc2, sy=sy, sz=sz, **fs),
                    M.new_monitor(U("box_xmax"), orient="x", x=x1, y=yc, z=zc2, sy=sy, sz=sz, **fs)]
            if not M.is2d(p):
                new += [M.new_monitor(U("box_ymin"), orient="y", x=xc, y=y0, z=zc2, sx=sx, sz=sz, **fs),
                        M.new_monitor(U("box_ymax"), orient="y", x=xc, y=y1, z=zc2, sx=sx, sz=sz, **fs)]
        for m in new:
            p["monitors"].append(m)
        self.ed.refresh()
        self.ed.select_name(new[-1]["name"])
        self.win.changed()


# ==========================================================================
# 7 執行與輸出
# ==========================================================================
class RunPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        outer = QVBoxLayout(self)
        outer.addWidget(title("7  執行與輸出"))
        sp = QSplitter(Qt.Horizontal)
        left = QWidget()
        lv = QVBoxLayout(left)
        g = QGroupBox("輸出設定")
        self.gv = QVBoxLayout(g)
        lv.addWidget(g)
        btns = QGridLayout()
        b1 = QPushButton("① 檢查設定")
        b1.clicked.connect(self.check)
        b2 = QPushButton("② 只建模型(存 .fsp)")
        b2.setObjectName("primary")
        b2.clicked.connect(lambda: self.win.start_job("build"))
        b3 = QPushButton("③ 建模並執行、輸出資料")
        b3.setObjectName("primary")
        b3.clicked.connect(lambda: self.win.start_job("build_run"))
        b4 = QPushButton("停止")
        b4.setObjectName("danger")
        b4.clicked.connect(self.win.stop_job)
        b5 = QPushButton("用 Lumerical 開最近的 .fsp")
        b5.clicked.connect(self.win.open_last_in_lumerical)
        b6 = QPushButton("開啟輸出資料夾")
        b6.clicked.connect(self.win.open_last_folder)
        for b, tp in ((b1, "檢查名稱重複、材料不存在、光源或監視器在模擬區外…,並更新右邊的腳本。"),
                      (b2, "只在 Lumerical 裡建好模型、存成 .fsp(不跑)。"),
                      (b3, "建模 → 執行 → 取資料、存檔、畫圖。"), (b4, "中斷目前的工作(只關這次開的 Lumerical)。"),
                      (b5, "用 Lumerical 視窗打開最近建好的 .fsp,目視檢查。"), (b6, "打開結果資料夾。")):
            b.setToolTip(tp)
        for i, b in enumerate((b1, b2, b3, b4, b5, b6)):
            btns.addWidget(b, i // 3, i % 3)
        lv.addLayout(btns)
        self.checks = QListWidget()
        self.checks.setMinimumHeight(120)
        lv.addWidget(QLabel("<b>檢查結果</b>"))
        lv.addWidget(self.checks, 1)
        ex = QGroupBox("從既有的 .fsp 匯出資料(不重跑)")
        exl = QHBoxLayout(ex)
        self.ex_path = QLineEdit()
        bp = QPushButton("選 .fsp…")
        bp.clicked.connect(self._pick_fsp)
        be = QPushButton("匯出")
        be.clicked.connect(self._export)
        exl.addWidget(self.ex_path, 1)
        exl.addWidget(bp)
        exl.addWidget(be)
        lv.addWidget(ex)
        sp.addWidget(scroll_wrap(left))
        right = QWidget()
        rv = QVBoxLayout(right)
        row = QHBoxLayout()
        row.addWidget(QLabel("<b>會送給 Lumerical 的腳本(.lsf)</b>"))
        row.addStretch(1)
        bc = QPushButton("複製")
        bc.clicked.connect(self._copy)
        bs = QPushButton("另存…")
        bs.clicked.connect(self._save_lsf)
        row.addWidget(bc)
        row.addWidget(bs)
        rv.addLayout(row)
        self.lsf = QPlainTextEdit()
        self.lsf.setReadOnly(True)
        self.lsf.setObjectName("code")
        self.lsf.setLineWrapMode(QPlainTextEdit.NoWrap)
        rv.addWidget(self.lsf, 1)
        sp.addWidget(right)
        sp.setSizes([600, 400])
        outer.addWidget(sp, 1)
        self.form = None

    def refresh(self):
        if self.form is not None:
            self.form.setParent(None)
        self.form = FieldForm(M.tag_fields(M.RUN_FIELDS, "run"), self.win.p["run"], self.win, lambda k: self.win.changed(preview=False))
        self.gv.addWidget(self.form)
        self.check(quiet=True)

    def check(self, quiet=False):
        from lumeasy import lsf
        res = lsf.validate(self.win.p, self.win.builtin)
        self.checks.clear()
        if not res:
            self.checks.addItem("通過:沒有發現問題")
        for lvl, msg in res:
            self.checks.addItem(("錯誤:" if lvl == "error" else "注意:") + msg)
            it = self.checks.item(self.checks.count() - 1)
            it.setForeground(Qt.red if lvl == "error" else Qt.darkYellow)
        try:
            sc = lsf.generate(self.win.p, os.path.join(self.win.p["project"].get("folder") or "C:/", self.win.p["project"]["name"] + ".fsp"))
            self.lsf.setPlainText(sc.text())
        except Exception as e:  # noqa: BLE001
            self.lsf.setPlainText(f"# 腳本產生失敗:{e}")
        return res

    def _copy(self):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.lsf.toPlainText())
        self.win.log("腳本已複製到剪貼簿")

    def _save_lsf(self):
        p, _ = QFileDialog.getSaveFileName(self, "另存腳本", self.win.p["project"]["name"] + ".lsf", "Lumerical script (*.lsf)")
        if p:
            with open(p, "w", encoding="utf-8") as f:
                f.write(self.lsf.toPlainText())

    def _pick_fsp(self):
        p, _ = QFileDialog.getOpenFileName(self, "選 .fsp", self.win.p["project"].get("folder", ""), "Lumerical FDTD (*.fsp)")
        if p:
            self.ex_path.setText(p)

    def _export(self):
        p = self.ex_path.text().strip()
        if not p or not os.path.exists(p):
            QMessageBox.warning(self, "匯出", "請先選一個存在的 .fsp 檔")
            return
        self.win.start_export(p)


# ==========================================================================
# 8 說明
# ==========================================================================
class HelpPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        v = QVBoxLayout(self)
        v.addWidget(title("說明"))
        row = QHBoxLayout()
        self.which = QComboBox()
        self.docs = {}
        for fn, lab in (("使用說明.md", "使用說明"), ("疑難排解.md", "疑難排解(踩過的坑與解法)")):
            p = self._find(fn)
            if p:
                self.docs[lab] = p
                self.which.addItem(lab)
        self.which.currentTextChanged.connect(self.show_doc)
        row.addWidget(self.which)
        row.addStretch(1)
        v.addLayout(row)
        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(True)
        v.addWidget(self.view, 1)
        if self.which.count():
            self.show_doc(self.which.currentText())

    @staticmethod
    def _find(fn):
        import sys
        here = os.path.dirname(os.path.abspath(__file__))
        for d in (os.path.join(getattr(sys, "_MEIPASS", ""), "docs"), os.path.join(here, "..", "..", "docs"),
                  os.path.join(os.path.dirname(sys.executable), "docs")):
            p = os.path.join(d, fn)
            if os.path.exists(p):
                return os.path.normpath(p)
        return None

    def show_doc(self, lab):
        p = self.docs.get(lab)
        if p:
            with open(p, encoding="utf-8") as f:
                self.view.setMarkdown(f.read())

    def refresh(self):
        pass
