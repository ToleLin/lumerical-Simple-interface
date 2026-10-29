"""從介面按「建模並執行」(不開視窗),等背景工作結束,列出結果。存放資料夾故意用中文路徑。"""
import os, sys, pathlib, time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
here = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(here.parent))
os.environ["LUMEASY_HOME"] = str(here / "appdata_test")
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QEventLoop, QTimer
app = QApplication(sys.argv)
msgs = []
QMessageBox.warning = staticmethod(lambda *a, **k: msgs.append(("warning", a[1:3])) or QMessageBox.Ok)
QMessageBox.question = staticmethod(lambda *a, **k: msgs.append(("question", a[1:3])) or QMessageBox.Yes)
QMessageBox.information = staticmethod(lambda *a, **k: msgs.append(("info", a[1:3])) or QMessageBox.Ok)
from lumeasy.gui.mainwin import MainWindow
from lumeasy import examples
w = MainWindow()
which = sys.argv[1] if len(sys.argv) > 1 else "grating"
action = sys.argv[2] if len(sys.argv) > 2 else "build_run"
w.load_example(examples.grating_2d if which == "grating" else examples.pillar_unit_cell_3d)
w.p["project"]["folder"] = str(here / "out_gui" / "中文資料夾 測試")
w.p["run"]["processes"] = 0
w.p["run"]["formats"] = ["npz", "mat", "csv", "png", "json"]
loop = QEventLoop()
done = {}
w.runner.finished.connect(lambda ok, res: (done.update(ok=ok, res=res), loop.quit()))
t0 = time.time()
if action == "probe":
    w.probe()
else:
    w.start_job(action)
QTimer.singleShot(900_000, loop.quit)
loop.exec()
print(f"finished in {time.time() - t0:.1f}s ok={done.get('ok')}")
print("log tail:")
print("\n".join(w.logbox.toPlainText().splitlines()[-25:]))
print("dialogs:", msgs)
r = done.get("res") or {}
for k in ("fsp", "out_dir", "geometry_mismatch", "engine"):
    print(k, "=", r.get(k))
print("builtin count", len(w.builtin))
