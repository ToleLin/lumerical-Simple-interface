"""主視窗:左邊步驟、中間頁面、右邊預覽、下面紀錄與進度。"""
from __future__ import annotations

import copy
import datetime as dt
import json
import os
import shutil

from PySide6.QtCore import QProcess, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow,
                               QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QSplitter, QStackedWidget,
                               QToolBar, QToolButton, QMenu, QVBoxLayout, QWidget)

from lumeasy import APP_NAME, __version__, lumenv
from lumeasy import examples as EX
from lumeasy import materials as MAT
from lumeasy import model as M
from lumeasy.gui import pages as P
from lumeasy.gui.preview import Preview
from lumeasy.gui.runner import Runner

AUTOSAVE = os.path.join(lumenv.APPDATA, "autosave.json")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {__version__} — Lumerical FDTD 一站式建模")
        self.resize(1480, 920)
        self.settings = lumenv.load_settings()
        self.builtin = self.settings.get("builtin_materials") or list(MAT.DEFAULT_BUILTINS)
        self.project_path = None
        self.selected = None
        self.last = {}
        restored = False
        try:
            with open(AUTOSAVE, encoding="utf-8") as f:
                self.p = M.upgrade(json.load(f))
            restored = True
        except (OSError, ValueError):
            self.p = M.new_project()
            self.p["project"]["folder"] = self.settings.get("last_folder", "")
        self.runner = Runner(self)
        self.runner.event.connect(self._on_event)
        self.runner.finished.connect(self._on_finished)
        self._build_ui()
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(250)
        self._preview_timer.timeout.connect(self._update_preview)
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(1500)
        self._autosave_timer.timeout.connect(self._autosave)
        self.refresh_all()
        self.log(f"{APP_NAME} {__version__} 已啟動。" + ("已還原上次的編輯內容。" if restored else "")
                 + " 不知道從哪開始?工具列「範例」載入一個現成模型看看。")
        if geo := self.settings.get("geometry"):
            try:
                self.restoreGeometry(bytes.fromhex(geo))
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        tb = QToolBar("主要")
        tb.setMovable(False)
        tb.setObjectName("mainbar")
        self.addToolBar(tb)

        def menu_button(text, tip, items):
            bt = QToolButton()
            bt.setText(text)
            bt.setToolTip(tip)
            bt.setPopupMode(QToolButton.InstantPopup)
            m = QMenu(self)
            for lab, fn, key in items:
                a = m.addAction(lab, fn)
                if key:
                    a.setShortcut(QKeySequence(key))
                    self.addAction(a)          # 快捷鍵在整個視窗都有效
            bt.setMenu(m)
            tb.addWidget(bt)
            return bt
        menu_button("檔案", "新專案、開啟、儲存專案檔(.json)。編輯內容也會自動暫存,關掉再開會還原。",
                    [("新專案", self.new_project, "Ctrl+N"), ("開啟專案…", self.open_project, "Ctrl+O"),
                     ("儲存", self.save_project, "Ctrl+S"), ("另存新檔…", lambda: self.save_project(as_=True), None)])
        menu_button("範例", "載入一個現成的模型,看看各頁怎麼填。",
                    [(lab, (lambda fn=fn: self.load_example(fn)), None) for lab, fn in EX.EXAMPLES.items()])
        tb.addSeparator()

        def seg(options, tip, on):
            box = QWidget()
            h = QHBoxLayout(box)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(0)
            grp = []
            for i, (val, lab) in enumerate(options):
                bt = QPushButton(lab)
                bt.setCheckable(True)
                bt.setObjectName("segL" if i == 0 else "segR")
                bt.setToolTip(tip)
                bt.clicked.connect(lambda _=None, val=val: on(val))
                h.addWidget(bt)
                grp.append((val, bt))
            tb.addWidget(box)
            return grp
        self.seg_unit = seg([("nm", "nm"), ("um", "µm")], "長度單位:一鍵切換,所有數值自動換算,模型不會變。", self.set_unit)
        tb.addWidget(QLabel("  "))
        self.seg_dim = seg([("3D", "3D"), ("2D", "2D")], "3D 立體,或 2D(x-z 截面、沿 y 無限長,算得很快)。", self.set_dimension)
        tb.addWidget(QLabel("  "))
        self.simple_btn = QPushButton()
        self.simple_btn.setCheckable(True)
        self.simple_btn.setObjectName("toggle")
        self.simple_btn.setToolTip("簡易模式:只顯示常用欄位(功能都還在)。\n進階模式:顯示所有 Lumerical 設定,例如 PML 層數、網格優先順序、降取樣。")
        self.simple_btn.clicked.connect(self.toggle_simple)
        tb.addWidget(self.simple_btn)
        spacer = QWidget()
        from PySide6.QtWidgets import QSizePolicy
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)
        self.btn_build = QPushButton("建立模型")
        self.btn_build.setObjectName("primaryBig")
        self.btn_build.setToolTip("在 Lumerical 裡建好模型、存成 .fsp(不跑模擬)。\n會先自動檢查設定,並讀回位置尺寸核對。")
        self.btn_build.clicked.connect(lambda: self.start_job("build"))
        tb.addWidget(self.btn_build)
        self.btn_run = QPushButton("執行模擬")
        self.btn_run.setObjectName("primaryBig")
        self.btn_run.setToolTip("建模 → 跑 FDTD → 取出監視器資料 → 依「執行與輸出」頁的格式存檔、畫場圖。\n"
                                "跑完會自動檢查引擎有沒有發散。")
        self.btn_run.clicked.connect(lambda: self.start_job("build_run"))
        tb.addWidget(self.btn_run)
        self.btn_stop = QPushButton("停止")
        self.btn_stop.setObjectName("danger")
        self.btn_stop.setToolTip("中斷目前的工作:只關掉這次開的 Lumerical(不影響別的程式,也不碰授權)。")
        self.btn_stop.clicked.connect(self.stop_job)
        self.btn_stop.setVisible(False)
        tb.addWidget(self.btn_stop)

        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setFixedWidth(150)
        self.pages = QStackedWidget()
        specs = [("1  專案", P.ProjectPage, "檔名、存放資料夾、2D / 3D、Lumerical 連線"),
                 ("2  材料", P.MaterialsPage, "自訂材料:固定 n,k、固定 ε、匯入頻譜檔"),
                 ("3  結構", P.GeometryPage, "輸入尺寸建模,或切到「草圖畫圖」用滑鼠畫"),
                 ("4  光源", P.SourcePage, "波長範圍、平面波 / 高斯光 / 模態 / 偶極子"),
                 ("5  模擬區", P.RegionPage, "FDTD 範圍、邊界條件、網格"),
                 ("6  監視器", P.MonitorPage, "要記錄哪裡的光,勾選電場 / 磁場"),
                 ("7  執行與輸出", P.RunPage, "檢查、建模、執行,輸出格式"),
                 ("說明", P.HelpPage, "使用說明與疑難排解")]
        self.page_objs = []
        for lab, cls, tip in specs:
            it = QListWidgetItem(lab, self.nav)
            it.setToolTip(tip)
            pg = cls(self)
            self.page_objs.append(pg)
            self.pages.addWidget(pg)
        self.run_page = self.page_objs[6]
        self.nav.currentRowChanged.connect(self._nav)
        self.preview = Preview()
        center = QSplitter(Qt.Horizontal)
        mid = QWidget()
        ml = QHBoxLayout(mid)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(0)
        ml.addWidget(self.nav)
        ml.addWidget(self.pages, 1)
        center.addWidget(mid)
        center.addWidget(self.preview)
        center.setStretchFactor(0, 3)
        center.setStretchFactor(1, 2)
        center.setSizes([1030, 450])
        # 下方:一條狀態列,紀錄預設收起來
        bottom = QWidget()
        bottom.setObjectName("statusArea")
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(10, 4, 10, 4)
        row = QHBoxLayout()
        self.stage = QLabel("待命")
        self.stage.setObjectName("stage")
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setValue(0)
        self.bar.setFormat("")
        self.bar.setFixedHeight(16)
        self.lastmsg = QLabel("")
        self.lastmsg.setObjectName("lastmsg")
        self.log_btn = QPushButton("顯示紀錄")
        self.log_btn.setObjectName("flat")
        self.log_btn.setToolTip("展開 / 收起詳細紀錄(每一步做了什麼、警告、錯誤)。出錯時會自動展開。")
        self.log_btn.clicked.connect(lambda: self.show_log(not self.logbox.isVisible()))
        row.addWidget(self.stage)
        row.addWidget(self.bar, 1)
        row.addWidget(self.lastmsg, 2)
        row.addWidget(self.log_btn)
        bl.addLayout(row)
        self.logbox = QPlainTextEdit()
        self.logbox.setReadOnly(True)
        self.logbox.setObjectName("log")
        self.logbox.setMaximumBlockCount(5000)
        bl.addWidget(self.logbox, 1)
        self.vs = QSplitter(Qt.Vertical)
        self.vs.addWidget(center)
        self.vs.addWidget(bottom)
        self.vs.setStretchFactor(0, 5)
        self.vs.setStretchFactor(1, 0)
        self.vs.setCollapsible(1, False)
        self.setCentralWidget(self.vs)
        self.show_log(bool(self.settings.get("show_log", False)))
        self.nav.setCurrentRow(0)

    def show_log(self, on):
        self.logbox.setVisible(on)
        self.log_btn.setText("收起紀錄" if on else "顯示紀錄")
        self.settings["show_log"] = on
        total = sum(self.vs.sizes()) or 900
        self.vs.setSizes([total - (200 if on else 34), 200 if on else 34])

    def simple(self):
        return bool(self.settings.get("simple", True))

    def toggle_simple(self):
        self.settings["simple"] = not self.simple()
        self.log("切換成" + ("簡易模式:只顯示常用欄位(改過的進階設定仍會顯示)" if self.simple() else "進階模式:顯示所有設定"))
        self.refresh_all()

    def _nav(self, i):
        self.pages.setCurrentIndex(i)
        pg = self.page_objs[i]
        if hasattr(pg, "refresh"):
            pg.refresh()

    # ------------------------------------------------------------------ ctx(給表單用)
    def unit(self):
        return self.p["project"].get("unit", "nm")

    def unit_label(self):
        return "nm" if self.unit() == "nm" else "µm"

    def dim(self):
        return self.p["project"].get("dimension", "3D")

    def materials(self):
        return [m["name"] for m in self.p["materials"]], self.builtin

    def objects(self, exclude=None, before=None):
        out = []
        for o in self.p["objects"]:
            if before is not None and o is before:
                break
            if o.get("name") != exclude:
                out.append(o["name"])
        return out

    def files_dir(self):
        return self.settings.get("last_cad_dir") or self.p["project"].get("folder") or ""

    # ------------------------------------------------------------------ 狀態
    def changed(self, preview=True):
        if preview:
            self._preview_timer.start()
        self._autosave_timer.start()
        self._update_title()

    def _update_title(self):
        n = self.p["project"]["name"]
        f = f" — {os.path.basename(self.project_path)}" if self.project_path else ""
        self.setWindowTitle(f"{APP_NAME} {__version__} — {n}{f}")
        for val, bt in self.seg_unit:
            bt.setChecked(val == self.unit())
        for val, bt in self.seg_dim:
            bt.setChecked(val == self.dim())
        self.simple_btn.setChecked(self.simple())
        self.simple_btn.setText("簡易模式" if self.simple() else "進階模式")

    def _update_preview(self):
        self.preview.set_project(self.p, self.selected)

    def set_selected(self, name):
        self.selected = name
        self._preview_timer.start()

    def refresh_all(self):
        for pg in self.page_objs:
            if hasattr(pg, "refresh"):
                pg.refresh()
        self._update_title()
        self._update_preview()

    def set_unit(self, u):
        if u == self.unit():
            return
        self.p["project"]["unit"] = u
        self.log(f"長度單位改成 {self.unit_label()}(所有數值已換算,模型沒有變)")
        self.refresh_all()
        self.changed()

    def set_dimension(self, d):
        if d == self.dim():
            return
        self.p["project"]["dimension"] = d
        self.log("切換成 2D:畫的是 x-z 截面(沿 y 無限長),y 方向的設定會被忽略。" if d == "2D" else "切換成 3D。")
        self.refresh_all()
        self.changed()

    def _autosave(self):
        try:
            os.makedirs(lumenv.APPDATA, exist_ok=True)
            M.save_project(self.p, AUTOSAVE)
            lumenv.save_settings(self.settings)
        except OSError:
            pass

    def log(self, msg, level="log"):
        t = dt.datetime.now().strftime("%H:%M:%S")
        if hasattr(self, "lastmsg"):
            short = msg.splitlines()[0] if msg else ""
            self.lastmsg.setText(short[:120])
            self.lastmsg.setStyleSheet({"warn": "color:#b26b00", "error": "color:#c00000", "ok": "color:#007a33"}.get(level, ""))
            if level == "error" and not self.logbox.isVisible():
                self.show_log(True)
        color = {"warn": "#b26b00", "error": "#c00000", "ok": "#007a33"}.get(level)
        if color:
            self.logbox.appendHtml(f"<span style='color:{color}'>[{t}] {msg}</span>".replace("\n", "<br>"))
        else:
            self.logbox.appendPlainText(f"[{t}] {msg}")

    # ------------------------------------------------------------------ 專案檔
    def new_project(self):
        if QMessageBox.question(self, "新專案", "清空目前的模型、開一個新專案?(目前的內容可以先「儲存」)") != QMessageBox.Yes:
            return
        folder = self.p["project"].get("folder", "")
        lum = self.p["project"].get("lumerical_dir", "")
        self.p = M.new_project()
        self.p["project"].update(folder=folder, lumerical_dir=lum)
        self.project_path = None
        self.refresh_all()
        self.changed()

    def load_example(self, fn):
        folder = self.p["project"].get("folder", "")
        lum = self.p["project"].get("lumerical_dir", "")
        self.p = fn()
        self.p["project"].update(folder=folder, lumerical_dir=lum)
        self.project_path = None
        self.refresh_all()
        self.changed()
        self.log(f"已載入範例「{self.p['project']['name']}」。看右邊預覽,再到「7 執行與輸出」按「建模並執行」。")

    def open_project(self):
        p, _ = QFileDialog.getOpenFileName(self, "開啟專案", self.settings.get("last_project_dir", ""),
                                           "LumEasy 專案 (*.json)")
        if not p:
            return
        try:
            self.p = M.load_project(p)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "開不了", str(e))
            return
        self.project_path = p
        self.settings["last_project_dir"] = os.path.dirname(p)
        self.refresh_all()
        self.changed()
        self.log(f"已開啟 {p}")

    def save_project(self, as_=False):
        path = self.project_path
        if as_ or not path:
            start = os.path.join(self.p["project"].get("folder") or "", self.p["project"]["name"] + ".lumeasy.json")
            path, _ = QFileDialog.getSaveFileName(self, "儲存專案", start, "LumEasy 專案 (*.json)")
            if not path:
                return
        M.save_project(self.p, path)
        self.project_path = path
        self.settings["last_project_dir"] = os.path.dirname(path)
        self._update_title()
        self.log(f"專案已存:{path}", "ok")

    # ------------------------------------------------------------------ Lumerical 工作
    def _busy(self):
        if self.runner.busy():
            QMessageBox.information(self, "忙碌中", "上一個工作還在跑。要中斷請按「停止」。")
            return True
        return False

    def probe(self):
        if self._busy():
            return
        self.log("連線測試:開一次 Lumerical(背景、看不到視窗),約 10–30 秒…")
        self._job_kind = "probe"
        self.runner.start({"action": "probe", "lumerical_dir": self.p["project"].get("lumerical_dir", "")},
                          open_timeout=int(self.p["run"].get("open_timeout") or 300))

    def start_job(self, action):
        if self._busy():
            return
        from lumeasy import estimate, lsf
        res = lsf.validate(self.p, self.builtin)
        errs = [m for lv, m in res if lv == "error"]
        if errs:
            QMessageBox.warning(self, "設定有錯誤", "請先修正:\n\n• " + "\n• ".join(errs[:15]))
            self.nav.setCurrentRow(self.page_objs.index(self.run_page))
            return
        for lv, m in res:
            self.log(m, "warn")
        if not self.p["project"].get("folder"):
            d = QFileDialog.getExistingDirectory(self, "選擇存放資料夾", self.settings.get("last_folder", os.path.expanduser("~")))
            if not d:
                return
            self.p["project"]["folder"] = os.path.normpath(d)
            self.settings["last_folder"] = d
            self.refresh_all()
        folder = self.p["project"]["folder"]
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError as e:
            QMessageBox.warning(self, "資料夾", f"建不了資料夾:{e}")
            return
        if action == "build_run":
            if not any(s.get("enabled", True) for s in self.p["sources"]):
                QMessageBox.warning(self, "缺光源", "執行模擬一定要有光源(「4 光源」新增一個)。")
                return
            e = estimate.estimate(self.p)
            if e["total_gb"] > 0.6 * e["free_gb"]:
                if QMessageBox.question(self, "記憶體可能不夠",
                                        f"粗估需要 {e['total_gb']:.1f} GB,目前可用 {e['free_gb']:.1f} GB。\n"
                                        "記憶體不足時 Lumerical 會在背景卡住。建議縮小模擬區、降低網格精度、"
                                        "監視器降取樣或減少頻率點。\n\n還是要跑嗎?") != QMessageBox.Yes:
                    return
            free = shutil.disk_usage(folder).free / 1024 ** 3
            if free < e["fsp_gb"] + 1:
                if QMessageBox.question(self, "磁碟空間", f"存放位置只剩 {free:.1f} GB,模型檔估計 {e['fsp_gb']:.1f} GB。"
                                                         "磁碟滿了 Lumerical 會在最後寫檔時失敗。還是要跑嗎?") != QMessageBox.Yes:
                    return
        self.p["project"]["lumerical_dir"] = self.p["project"].get("lumerical_dir") or ""
        self._job_kind = action
        self.bar.setValue(0)
        self.log(("建模並執行" if action == "build_run" else "只建模型") + f":{self.p['project']['name']} → {folder}")
        self.runner.start({"action": action, "project": copy.deepcopy(self.p)},
                          open_timeout=int(self.p["run"].get("open_timeout") or 300))

    def start_export(self, fsp):
        if self._busy():
            return
        self._job_kind = "export"
        r = self.p["run"]
        self.log(f"匯出 {fsp} 的監視器資料…")
        self.runner.start({"action": "export", "fsp": fsp, "formats": r.get("formats"), "field_wl": r.get("field_wl"),
                           "unit": self.unit(), "lumerical_dir": self.p["project"].get("lumerical_dir", "")},
                          open_timeout=int(r.get("open_timeout") or 300))

    def stop_job(self):
        if not self.runner.busy():
            return
        self.runner.stop()
        self.log("已送出停止:關掉這次開的 Lumerical 與背景程式(不影響其他程式開的 Lumerical,也不碰授權)。", "warn")

    def _set_busy(self, busy):
        self.btn_stop.setVisible(busy)
        self.btn_build.setEnabled(not busy)
        self.btn_run.setEnabled(not busy)

    def _on_event(self, e):
        self._set_busy(True)
        t = e.get("t")
        if t == "log":
            self.log(e.get("msg", ""))
        elif t == "warn":
            self.log(e.get("msg", ""), "warn")
        elif t == "error":
            self.log("錯誤:" + e.get("msg", ""), "error")
        elif t == "stage":
            names = {"start": "啟動背景程式", "open": "開啟 Lumerical…", "opened": "已連線", "build": "建模中",
                     "run": "模擬中", "extract": "取資料、存檔、畫圖", "load": "載入 .fsp"}
            self.stage.setText(names.get(e.get("name"), e.get("name", "")))
            if e.get("name") == "run":
                self.bar.setValue(0)
        elif t == "progress":
            self.bar.setValue(int(10 * float(e.get("pct", 0))))
            self.bar.setFormat(e.get("msg", ""))

    def _on_finished(self, ok, res):
        self._set_busy(False)
        kind = getattr(self, "_job_kind", "")
        self.stage.setText("完成" if ok else "失敗")
        self.bar.setFormat("")
        if not ok:
            self.bar.setValue(0)
            msg = res.get("error", "未知錯誤")
            self.log("工作失敗:" + msg, "error")
            QMessageBox.warning(self, "沒有完成", msg + "\n\n(詳細過程在下方紀錄;常見問題見「說明 / 疑難排解」)")
            return
        self.bar.setValue(1000)
        if kind == "probe":
            mats = res.get("materials") or []
            if mats:
                self.builtin = mats
                self.settings["builtin_materials"] = mats
            self.settings["lumerical_version"] = res.get("version")
            self._autosave()
            pg = self.page_objs[0]
            pg.lum_status.setText(f"<span style='color:#007a33'>✔ 連線成功:{res.get('version')},內建材料 {len(mats)} 種,"
                                  f"目前 CPU 行程設定 {res.get('processes')}</span>")
            self.log("連線測試成功", "ok")
            return
        self.last = res
        if res.get("fsp"):
            self.settings["last_fsp"] = res["fsp"]
        msgs = [f"模型檔:{res.get('fsp')}"] if res.get("fsp") else []
        if res.get("geometry_mismatch"):
            msgs.append(f"⚠ 幾何核對有 {len(res['geometry_mismatch'])} 個不一致(見紀錄)")
        eng = res.get("engine")
        if eng:
            msgs.append(f"引擎狀態:{ {'ok': '正常', 'diverged': '發散!結果不可信', 'not_converged': '沒有完全衰減', 'memory': '記憶體不足', 'unknown': '不明'}.get(eng['status'], eng['status'])}")
        if res.get("files"):
            msgs.append(f"輸出 {len(res['files'])} 個檔案 → {res.get('out_dir')}")
        self.log("完成。" + ";".join(msgs), "ok")
        if kind in ("build", "build_run") and self.p["run"].get("open_gui") and res.get("fsp"):
            self.open_in_lumerical(res["fsp"], res.get("root"))

    # ------------------------------------------------------------------ 開檔
    def open_in_lumerical(self, fsp, root=None):
        try:
            root = root or lumenv.resolve_root(self.p["project"].get("lumerical_dir", ""))
        except FileNotFoundError as e:
            QMessageBox.warning(self, "找不到 Lumerical", str(e))
            return
        exe = lumenv.gui_exe(root)
        if not os.path.exists(exe):
            QMessageBox.warning(self, "找不到 Lumerical", exe)
            return
        QProcess.startDetached(exe, [fsp])
        self.log(f"用 Lumerical 開啟 {fsp}")

    def open_last_in_lumerical(self):
        f = (self.last or {}).get("fsp") or self.settings.get("last_fsp")
        if not f or not os.path.exists(f):
            f, _ = QFileDialog.getOpenFileName(self, "選 .fsp", self.p["project"].get("folder", ""), "Lumerical FDTD (*.fsp)")
            if not f:
                return
        self.open_in_lumerical(f)

    def open_last_folder(self):
        d = (self.last or {}).get("out_dir") or self.p["project"].get("folder")
        self.open_path(d)

    def open_path(self, d):
        if d and os.path.exists(d):
            QDesktopServices.openUrl(QUrl.fromLocalFile(d))

    def closeEvent(self, e):
        if self.runner.busy():
            if QMessageBox.question(self, "還在跑", "背景工作還沒結束,要停止它並關閉嗎?") != QMessageBox.Yes:
                e.ignore()
                return
            self.runner.stop()
        self.settings["geometry"] = bytes(self.saveGeometry()).hex()
        self._autosave()
        e.accept()
