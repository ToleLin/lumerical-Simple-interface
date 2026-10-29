"""不開視窗的自我測試(不需要 Lumerical):打包後確認 EXE 每個部分都能動。
結果寫到 %TEMP%/lumeasy_selftest.txt,全部通過回傳 0。"""
from __future__ import annotations

import os
import sys
import tempfile
import traceback


def main() -> int:
    out = os.path.join(tempfile.gettempdir(), "lumeasy_selftest.txt")
    lines, ok = [], True

    def check(name, fn):
        nonlocal ok
        try:
            r = fn()
            lines.append(f"PASS  {name}" + (f"  ({r})" if r else ""))
        except Exception:  # noqa: BLE001
            ok = False
            lines.append(f"FAIL  {name}\n{traceback.format_exc()}")

    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ.setdefault("LUMEASY_HOME", os.path.join(tempfile.gettempdir(), "lumeasy_selftest_home"))
    from lumeasy import examples, lsf, materials, model, results, estimate, lumenv, cadio  # noqa: F401

    def gen():
        n = 0
        for f in examples.EXAMPLES.values():
            p = f()
            assert not [m for lv, m in lsf.validate(p, materials.DEFAULT_BUILTINS) if lv == "error"]
            n += len(lsf.generate(p, "C:/x.fsp").stmts)
        return f"{n} 行腳本"
    check("範例產生 Lumerical 腳本", gen)

    def mat():
        e1, e2 = materials.nk_to_eps(2.0, 0.1)
        n, k = materials.eps_to_nk(e1, e2)
        assert abs(n - 2.0) < 1e-12 and abs(k - 0.1) < 1e-12
        return "n,k ⇄ ε"
    check("材料換算", mat)
    check("找 Lumerical", lambda: ", ".join(lumenv.find_installs()) or "這台沒有裝 Lumerical(介面仍可用)")
    check("記憶體估計", lambda: f"{estimate.estimate(examples.pillar_unit_cell_3d())['total_gb']:.2f} GB")

    def libs():
        import gdstk  # noqa: F401
        import ezdxf  # noqa: F401
        import h5py  # noqa: F401
        import scipy.io  # noqa: F401
        import matplotlib
        matplotlib.use("Agg")
        return "gdstk / ezdxf / h5py / scipy / matplotlib"
    check("函式庫", libs)

    def gui():
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication(sys.argv)
        from lumeasy.gui.app import STYLE, _quick_tip_style
        app.setStyle(_quick_tip_style()("Fusion"))
        app.setStyleSheet(STYLE)
        from lumeasy.gui.mainwin import MainWindow
        w = MainWindow()
        w.show()
        for fn in examples.EXAMPLES.values():
            w.load_example(fn)
            for i in range(w.nav.count()):
                w.nav.setCurrentRow(i)
                app.processEvents()
            geo = w.page_objs[2]
            geo.tabs.setCurrentIndex(1)
            app.processEvents()
            geo.sketch._drawn("rect", (-100, -50, 100, 50))
            geo.tabs.setCurrentIndex(0)
            app.processEvents()
        w.preview.redraw()
        helpdocs = w.page_objs[-1].which.count()
        assert helpdocs == 2, f"說明文件只找到 {helpdocs} 份"
        w._autosave_timer.stop()
        w.close()
        return f"{w.nav.count()} 頁,說明文件 {helpdocs} 份"
    check("介面", gui)

    def full_run():
        """真的開 Lumerical 跑 2D 範例(約 30 秒):介面 → 背景程式 → Lumerical → 輸出。"""
        from PySide6.QtCore import QEventLoop, QTimer
        from PySide6.QtWidgets import QApplication, QMessageBox
        app = QApplication.instance()
        QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)
        QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
        QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
        from lumeasy.gui.mainwin import MainWindow
        w = MainWindow()
        w.load_example(examples.grating_2d)
        w.p["project"]["folder"] = os.path.join(tempfile.gettempdir(), "lumeasy_selftest_run", "中文路徑測試")
        w.p["run"].update(processes=0, overwrite=True, formats=["npz", "csv", "png", "json"])
        loop, done = QEventLoop(), {}
        w.runner.finished.connect(lambda ok, res: (done.update(ok=ok, res=res), loop.quit()))
        w.start_job("build_run")
        QTimer.singleShot(900_000, loop.quit)
        loop.exec()
        w._autosave_timer.stop()
        res = done.get("res") or {}
        assert done.get("ok"), res.get("error", "逾時")
        assert res.get("engine", {}).get("status") == "ok", res.get("engine")
        assert not res.get("geometry_mismatch"), res.get("geometry_mismatch")
        assert len(res.get("files", [])) >= 5, res.get("files")
        return f"{len(res['files'])} 個輸出檔,{res['fsp']}"
    if "run" in sys.argv[2:]:
        check("完整執行(開 Lumerical 跑 2D 範例)", full_run)
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n" + ("全部通過" if ok else "有失敗") + "\n")
    if sys.stdout:
        print("\n".join(lines))
    return 0 if ok else 1
