"""不開視窗地跑一遍介面:每一頁切過去、載入範例、在草圖畫幾個形狀,每頁存一張截圖。"""
import os, sys, pathlib, traceback
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
here = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(here.parent))
os.environ["LUMEASY_HOME"] = str(here / "appdata_test")
from PySide6.QtWidgets import QApplication
from lumeasy.gui.app import STYLE
app = QApplication(sys.argv)
from PySide6.QtGui import QFontDatabase
for f in ("msjh.ttc", "msjhbd.ttc", "consola.ttf", "segoeui.ttf"):
    QFontDatabase.addApplicationFont("C:/Windows/Fonts/" + f)
from lumeasy.gui.app import _quick_tip_style
app.setStyle(_quick_tip_style()("Fusion")); app.setStyleSheet(STYLE)
errors = []
sys.excepthook = lambda t, v, tb: (errors.append("".join(traceback.format_exception(t, v, tb))), print(errors[-1], flush=True))
from lumeasy.gui.mainwin import MainWindow
from lumeasy import examples
w = MainWindow(); w.resize(1480, 920); w.show()
shots = here / "shots"; shots.mkdir(exist_ok=True)
def snap(name):
    app.processEvents(); w.preview.redraw(); app.processEvents()
    w.grab().save(str(shots / f"{name}.png"))
which = sys.argv[1] if len(sys.argv) > 1 else "pillar"
w.load_example(examples.pillar_unit_cell_3d if which == "pillar" else examples.grating_2d)
for i in range(w.nav.count()):
    w.nav.setCurrentRow(i); app.processEvents()
    snap(f"{which}_{i}")
# 草圖:畫一個矩形、一個圓、一個多邊形,再挖一個孔
w.nav.setCurrentRow(2); app.processEvents()
geo = w.page_objs[2]; geo.tabs.setCurrentIndex(1); app.processEvents()
sk = geo.sketch
sk._drawn("rect", (-150, -100, 150, 100)) if which == "grating" else None
sk.op.setCurrentIndex(1)
sk._drawn("circle", (0, 0, 40) if which == "pillar" else (0, 400, 60))
sk.op.setCurrentIndex(0)
sk._drawn("polygon", [(-150, -150), (-50, -150), (-100, -60)] if which == "pillar" else [(500, 300), (700, 300), (600, 500)])
snap(f"{which}_sketch")
geo.tabs.setCurrentIndex(0); app.processEvents(); snap(f"{which}_geom_after")
w.nav.setCurrentRow(6); app.processEvents(); snap(f"{which}_run_after")
w.show_log(True); snap(f"{which}_run_log")
w.set_unit("um"); app.processEvents(); w.nav.setCurrentRow(2); app.processEvents(); snap(f"{which}_um")
print("objects:", [(o["name"], o["shape"], o["material"], o.get("on_top"), o.get("dz"), o.get("mesh_order")) for o in w.p["objects"]])
from lumeasy import lsf
print("validate:", lsf.validate(w.p, w.builtin))
print("ERRORS:", len(errors))
for e in errors[:5]: print(e)
w._autosave_timer.stop(); w.close()
