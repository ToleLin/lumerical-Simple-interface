"""專案資料模型:欄位定義(介面依這裡自動產生表單)、預設值、物件擺放與包圍盒。

座標慣例(使用者看到的):
  * 原點 (0,0,0),z 朝上。所有長度以專案單位(nm 或 µm)輸入,內部一律存 nm。
  * 3D:照字面。
  * 2D:使用者畫的是 x-z 截面(沿 y 無限長)。Lumerical 的 2D 只做 x-y 平面,
    轉換在 lsf.py 處理(我們的 z → Lumerical 的 y),使用者不用管。
"""
from __future__ import annotations

import copy
import json
import math
from typing import Any

PROJECT_VERSION = 1
UNIT_NM = {"nm": 1.0, "um": 1000.0}

# --------------------------------------------------------------------------
# 欄位定義
# --------------------------------------------------------------------------

def F(key, label, kind, default=None, **kw):
    d = {"key": key, "label": label, "kind": kind, "default": default}
    d.update(kw)
    return d


ANCHORS = [
    ("bottom_center", "底面中心"),
    ("center", "幾何中心"),
    ("corner", "底面角落 (x、y、z 最小處)"),
    ("file", "原始座標 (多邊形頂點 / CAD 檔案座標照原樣)"),
]

SHAPES: dict[str, dict] = {
    "box": {"label": "長方體", "fields": [
        F("Lx", "長 Lx(x 方向)", "len", 500.0),
        F("Ly", "寬 Ly(y 方向)", "len", 500.0, dims="3D"),
        F("H", "高 H(z 方向)", "len", 200.0),
        F("through", "貫穿模擬區", "bool", False),
    ]},
    "cylinder": {"label": "圓柱", "fields": [
        F("r", "半徑 r", "len", 100.0),
        F("H", "高 H", "len", 300.0),
    ]},
    "ellipse": {"label": "橢圓柱", "fields": [
        F("rx", "x 半軸 rx", "len", 150.0),
        F("ry", "y 半軸 ry", "len", 80.0, dims="3D"),
        F("H", "高 H", "len", 300.0),
    ]},
    "ring": {"label": "圓環柱", "fields": [
        F("r_out", "外半徑", "len", 300.0),
        F("r_in", "內半徑", "len", 200.0),
        F("H", "高 H", "len", 200.0),
        F("theta0", "起始角(度)", "angle", 0.0, dims="3D"),
        F("theta1", "結束角(度)", "angle", 360.0, dims="3D"),
    ]},
    "sphere": {"label": "球", "fields": [
        F("r", "半徑 r", "len", 100.0),
    ]},
    "pyramid": {"label": "梯形台 / 斜側壁柱", "fields": [
        F("Lx0", "底部 x 寬", "len", 400.0),
        F("Ly0", "底部 y 寬", "len", 400.0, dims="3D"),
        F("Lx1", "頂部 x 寬", "len", 300.0),
        F("Ly1", "頂部 y 寬", "len", 300.0, dims="3D"),
        F("H", "高 H", "len", 300.0),
    ]},
    "regpoly": {"label": "正多邊形柱", "fields": [
        F("N", "邊數", "int", 6, min=3, max=128),
        F("R", "外接圓半徑", "len", 150.0),
        F("H", "高 H", "len", 200.0, dims="3D"),
    ]},
    "polygon": {"label": "自訂多邊形柱(特殊形狀)", "fields": [
        F("vertices", "頂點(每行一個)", "vertices",
          "0, 0\n400, 0\n200, 300"),
        F("H", "高 H", "len", 200.0, dims="3D"),
    ]},
    "stl": {"label": "CAD 匯入:STL 立體", "fields": [
        F("file", "STL 檔案", "file", "", filter="STL (*.stl)"),
        F("file_unit", "檔案的長度單位", "choice", "um",
          choices=[("nm", "nm"), ("um", "µm"), ("mm", "mm"), ("m", "m")]),
    ]},
    "gds": {"label": "CAD 匯入:GDSII 版圖(擠出成柱)", "fields": [
        F("file", "GDS 檔案", "file", "", filter="GDSII (*.gds *.gds2 *.gdsii)"),
        F("cell", "Cell 名稱(空白 = 最上層)", "text", ""),
        F("layer", "圖層(例 1 或 1:0)", "text", "1"),
        F("H", "擠出高度 H(2D 不用)", "len", 200.0, dims="3D"),
    ]},
    "dxf": {"label": "CAD 匯入:DXF 封閉多邊形(擠出成柱)", "fields": [
        F("file", "DXF 檔案", "file", "", filter="DXF (*.dxf)"),
        F("layer", "圖層(空白 = 全部)", "text", ""),
        F("file_unit", "檔案的長度單位", "choice", "um",
          choices=[("nm", "nm"), ("um", "µm"), ("mm", "mm"), ("m", "m")]),
        F("H", "擠出高度 H(2D 不用)", "len", 200.0, dims="3D"),
    ]},
}

ARRAYABLE = {"box", "cylinder", "ellipse", "ring", "sphere", "pyramid", "regpoly", "polygon"}
CAD_SHAPES = {"stl", "gds", "dxf"}
FILE_UNIT_NM = {"nm": 1.0, "um": 1e3, "mm": 1e6, "m": 1e9}

OBJECT_COMMON = [
    F("name", "名稱", "text", "obj"),
    F("enabled", "啟用", "bool", True),
    F("material", "材料", "material", "SiO2 (Glass) - Palik"),
    F("anchor", "對齊點", "choice", "bottom_center", choices=ANCHORS),
    F("dx", "偏移 x", "len", 0.0),
    F("dy", "偏移 y", "len", 0.0, dims="3D"),
    F("dz", "偏移 z", "len", 0.0),
    F("on_top", "疊在…的頂面上", "objtop", ""),
    F("rot", "旋轉角", "angle", 0.0),
    F("nx", "陣列:x 方向個數", "int", 1, min=1, max=10000),
    F("ny", "陣列:y 方向個數", "int", 1, min=1, max=10000, dims="3D"),
    F("px", "陣列:x 週期", "len", 500.0),
    F("py", "陣列:y 週期", "len", 500.0, dims="3D"),
    F("mesh_order", "網格優先順序", "int", 2, min=1, max=20),
]

SOURCE_TYPES: dict[str, dict] = {
    "planewave": {"label": "平面波", "fields": [
        F("axis", "注入方向的軸", "choice", "z", choices=[("z", "z"), ("x", "x"), ("y", "y(只限 3D)")]),
        F("direction", "傳播方向", "choice", "neg", choices=[("neg", "往負方向(例:由上往下)"), ("pos", "往正方向(例:由下往上)")]),
        F("pwtype", "平面波種類", "choice", "Bloch/periodic", choices=[
            ("Bloch/periodic", "Bloch / 週期(一般用這個)"), ("BFAST", "BFAST(週期結構寬頻斜入射)"),
            ("Diffracting", "會繞射的有限平面波")]),
        F("pol", "偏振角", "angle", 0.0),
        F("pol2d", "2D 偏振", "choice", "TE", dims="2D", choices=[
            ("TE", "TE / s:E 沿 y(垂直截面)"), ("TM", "TM / p:E 在 x-z 截面內")]),
        F("theta", "入射角 θ", "angle", 0.0),
        F("phi", "方位角 φ", "angle", 0.0, dims="3D"),
    ]},
    "gaussian": {"label": "高斯光束", "fields": [
        F("axis", "注入方向的軸", "choice", "z", choices=[("z", "z"), ("x", "x"), ("y", "y(只限 3D)")]),
        F("direction", "傳播方向", "choice", "neg", choices=[("neg", "往負方向"), ("pos", "往正方向")]),
        F("w0", "束腰半徑 w0", "len", 1000.0),
        F("focus", "到束腰距離", "len", 0.0),
        F("pol", "偏振角", "angle", 0.0),
        F("pol2d", "2D 偏振", "choice", "TE", dims="2D", choices=[
            ("TE", "TE / s:E 沿 y"), ("TM", "TM / p:E 在 x-z 截面內")]),
        F("theta", "入射角 θ", "angle", 0.0),
        F("phi", "方位角 φ", "angle", 0.0, dims="3D"),
    ]},
    "mode": {"label": "波導模態光源", "fields": [
        F("axis", "注入方向的軸", "choice", "x", choices=[("x", "x"), ("y", "y(只限 3D)"), ("z", "z")]),
        F("direction", "傳播方向", "choice", "pos", choices=[("pos", "往正方向"), ("neg", "往負方向")]),
        F("mode", "模態", "choice", "fundamental TE mode", choices=[
            ("fundamental mode", "基模"), ("fundamental TE mode", "基模 TE"),
            ("fundamental TM mode", "基模 TM"), ("user select", "自己指定第幾個")]),
        F("mode_num", "第幾個模態", "int", 1, min=1, max=50),
    ]},
    "dipole": {"label": "偶極子點光源", "fields": [
        F("dtype", "種類", "choice", "Electric dipole", choices=[
            ("Electric dipole", "電偶極"), ("Magnetic dipole", "磁偶極")]),
        F("theta", "偶極方向 θ", "angle", 90.0),
        F("phi", "偶極方向 φ", "angle", 0.0, dims="3D"),
    ]},
    "tfsf": {"label": "TFSF 散射光源(包住粒子)", "fields": [
        F("axis", "注入方向的軸", "choice", "z", choices=[("z", "z"), ("x", "x"), ("y", "y(只限 3D)")]),
        F("direction", "傳播方向", "choice", "neg", choices=[("neg", "往負方向"), ("pos", "往正方向")]),
        F("pol", "偏振角", "angle", 0.0),
        F("pol2d", "2D 偏振", "choice", "TE", dims="2D", choices=[
            ("TE", "TE / s:E 沿 y"), ("TM", "TM / p:E 在 x-z 截面內")]),
        F("theta", "入射角 θ", "angle", 0.0),
    ]},
}

SOURCE_COMMON = [
    F("name", "名稱", "text", "source"),
    F("enabled", "啟用", "bool", True),
    F("x", "中心 x", "len", 0.0),
    F("y", "中心 y", "len", 0.0, dims="3D"),
    F("z", "中心 z", "len", 600.0),
    F("sx", "x 範圍", "autolen", None),
    F("sy", "y 範圍", "autolen", None, dims="3D"),
    F("sz", "z 範圍", "autolen", None),
]

MON_KINDS = [
    ("power", "頻域場與功率(穿透 / 反射、場圖都能用)"),
    ("profile", "頻域場剖面(場圖專用,會內插到網格點)"),
    ("index", "折射率剖面(檢查結構用)"),
    ("time", "時域(看場隨時間變化 / 共振)"),
    ("movie", "動畫(只存成影片)"),
]
MON_ORIENTS = [
    ("z", "水平面 XY(法向 z:上方 / 下方)"),
    ("x", "直立面 YZ(法向 x:左 / 右)"),
    ("y", "直立面 XZ(法向 y:前 / 後)"),
    ("point", "點"),
    ("lx", "線(沿 x)"),
    ("ly", "線(沿 y)"),
    ("lz", "線(沿 z)"),
    ("3d", "立體(3D 體積)"),
]
FIELD_OUTPUTS = ["Ex", "Ey", "Ez", "Hx", "Hy", "Hz", "Px", "Py", "Pz", "power"]

MONITOR_FIELDS = [
    F("name", "名稱", "text", "monitor"),
    F("enabled", "啟用", "bool", True),
    F("kind", "監視器種類", "choice", "power", choices=MON_KINDS),
    F("orient", "形狀 / 方向", "choice", "z", choices=MON_ORIENTS),
    F("x", "中心 x", "len", 0.0),
    F("y", "中心 y", "len", 0.0, dims="3D"),
    F("z", "中心 z(高度)", "len", 0.0),
    F("sx", "x 範圍(橫向)", "autolen", None),
    F("sy", "y 範圍(縱向)", "autolen", None, dims="3D"),
    F("sz", "z 範圍", "autolen", None),
    F("outputs", "記錄的場", "outputs", list(FIELD_OUTPUTS)),
    F("fpoints", "頻率點數", "int", 0, min=0, max=10000),
    F("downsample", "空間降取樣", "int", 1, min=1, max=50),
    F("movie_comp", "動畫顯示的分量", "choice", "Ey", choices=[(c, c) for c in
        ["Ex", "Ey", "Ez", "Hx", "Hy", "Hz"]]),
    F("plot_field", "畫場圖", "bool", True),
    F("plot_spectrum", "畫頻譜", "bool", True),
]

MESH_FIELDS = [
    F("name", "名稱", "text", "mesh"),
    F("enabled", "啟用", "bool", True),
    F("target", "套用到物件", "objref", ""),
    F("buffer", "物件外多包一圈", "len", 20.0),
    F("x", "手動中心 x", "len", 0.0), F("y", "手動中心 y", "len", 0.0, dims="3D"),
    F("z", "手動中心 z", "len", 0.0),
    F("sx", "手動 x 範圍", "len", 500.0), F("sy", "手動 y 範圍", "len", 500.0, dims="3D"),
    F("sz", "手動 z 範圍", "len", 500.0),
    F("dx", "最大網格 dx", "len", 10.0), F("dy", "最大網格 dy", "len", 10.0, dims="3D"),
    F("dz", "最大網格 dz", "len", 10.0),
]

BCS = [("PML", "PML(吸收,開放空間)"), ("Periodic", "週期"), ("Bloch", "Bloch(週期 + 斜入射)"),
       ("Symmetric", "對稱"), ("Anti-Symmetric", "反對稱"), ("Metal", "金屬(完美導體)"),
       ("PMC", "PMC(完美磁導體)")]
BCS_Z = [b for b in BCS if b[0] not in ("Symmetric", "Anti-Symmetric")]

REGION_FIELDS = [
    F("x_mode", "x 範圍", "choice", "auto", choices=[("auto", "自動(物件範圍 + 邊距)"), ("manual", "手動")]),
    F("x_margin", "x 每邊邊距", "len", 500.0),
    F("x_center", "x 手動中心", "len", 0.0), F("x_span", "x 手動範圍", "len", 2000.0),
    F("y_mode", "y 範圍", "choice", "auto", dims="3D", choices=[("auto", "自動(物件範圍 + 邊距)"), ("manual", "手動")]),
    F("y_margin", "y 每邊邊距", "len", 500.0, dims="3D"),
    F("y_center", "y 手動中心", "len", 0.0, dims="3D"), F("y_span", "y 手動範圍", "len", 2000.0, dims="3D"),
    F("z_mode", "z 範圍", "choice", "auto", choices=[("auto", "自動(物件範圍 + 邊距)"), ("manual", "手動")]),
    F("z_margin_top", "z 上方邊距", "len", 800.0), F("z_margin_bot", "z 下方邊距", "len", 500.0),
    F("z_center", "z 手動中心", "len", 0.0), F("z_span", "z 手動範圍", "len", 2000.0),
    F("bc_x", "x 邊界", "choice", "PML", choices=BCS),
    F("bc_y", "y 邊界", "choice", "PML", choices=BCS, dims="3D"),
    F("bc_zmin", "z 下邊界", "choice", "PML", choices=BCS_Z),
    F("bc_zmax", "z 上邊界", "choice", "PML", choices=BCS_Z),
    F("sim_time", "模擬時間(fs)", "float", 1000.0, min=1),
    F("mesh_acc", "網格精度", "int", 2, min=1, max=8),
    F("bg_index", "背景折射率", "float", 1.0, min=0.01),
    F("shutoff", "自動停止門檻", "float", 1e-5, min=0),
    F("pml_layers", "PML 層數", "int", 12, min=4, max=128),
    F("pml_type", "PML 種類", "choice", "stretched coordinate PML", choices=[
        ("stretched coordinate PML", "標準(stretched coordinate)"),
        ("uniaxial anisotropic PML (legacy)", "舊版 UPML(色散材料發散時試這個)")]),
    F("min_mesh", "最小網格(nm)", "float", 0.0, min=0),
]

GLOBAL_FIELDS = [
    F("wl_start", "波長起點(nm)", "float", 400.0, min=1),
    F("wl_stop", "波長終點(nm)", "float", 700.0, min=1),
    F("fpoints", "監視器頻率點數", "int", 101, min=1, max=20000),
]

OUTPUT_FORMATS = [
    ("npz", "NumPy .npz"), ("mat", "MATLAB .mat"), ("h5", "HDF5 .h5"),
    ("csv", "CSV(Excel/Origin)"), ("txt", "TXT(Tab 分隔)"), ("png", "PNG 圖"),
    ("json", "JSON 摘要"),
]

RUN_FIELDS = [
    F("formats", "輸出格式", "formats", ["npz", "csv", "png", "json"]),
    F("field_wl", "場圖波長(nm)", "text", "center"),
    F("processes", "CPU 行程數", "int", 4, min=0, max=128),
    F("overwrite", "同名直接覆寫", "bool", False),
    F("open_gui", "建好後開 Lumerical", "bool", False),
    F("open_timeout", "連線逾時(秒)", "int", 300, min=30, max=3600),
]


def defaults(fields: list[dict]) -> dict:
    return {f["key"]: copy.deepcopy(f["default"]) for f in fields}


def object_fields(shape: str) -> list[dict]:
    return OBJECT_COMMON[:3] + SHAPES[shape]["fields"] + OBJECT_COMMON[3:]


def source_fields(stype: str) -> list[dict]:
    return SOURCE_COMMON[:2] + SOURCE_TYPES[stype]["fields"] + SOURCE_COMMON[2:]


def new_object(shape: str, name: str) -> dict:
    d = defaults(object_fields(shape))
    d["shape"] = shape
    d["name"] = name
    return d


def new_source(stype: str, name: str) -> dict:
    d = defaults(source_fields(stype))
    d["type"] = stype
    d["name"] = name
    if stype in ("mode", "dipole"):
        d["z"] = 0.0
    return d


def new_monitor(name: str, **kw) -> dict:
    d = defaults(MONITOR_FIELDS)
    d["name"] = name
    d.update(kw)
    return d


def new_project() -> dict:
    return {
        "version": PROJECT_VERSION,
        "project": {"name": "my_simulation", "folder": "", "unit": "nm", "dimension": "3D",
                    "lumerical_dir": "", "notes": ""},
        "materials": [],
        "objects": [],
        "sources": [],
        "region": defaults(REGION_FIELDS),
        "global": defaults(GLOBAL_FIELDS),
        "mesh": [],
        "monitors": [],
        "run": defaults(RUN_FIELDS),
    }


def upgrade(p: dict) -> dict:
    """讀舊專案時補齊新欄位。"""
    base = new_project()
    for k, v in base.items():
        if k not in p:
            p[k] = v
        elif isinstance(v, dict):
            for kk, vv in v.items():
                p[k].setdefault(kk, vv)
    for o in p["objects"]:
        if o.pop("stack", False) and not o.get("on_top"):
            o["on_top"] = "@prev"
        for kk, vv in defaults(object_fields(o.get("shape", "box"))).items():
            o.setdefault(kk, vv)
    for s in p["sources"]:
        for kk, vv in defaults(source_fields(s.get("type", "planewave"))).items():
            s.setdefault(kk, vv)
    for m in p["monitors"]:
        for kk, vv in defaults(MONITOR_FIELDS).items():
            m.setdefault(kk, vv)
    for m in p["mesh"]:
        for kk, vv in defaults(MESH_FIELDS).items():
            m.setdefault(kk, vv)
    return p


def save_project(p: dict, path: str):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False, indent=1)


def load_project(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return upgrade(json.load(f))


def is2d(p: dict) -> bool:
    return p["project"].get("dimension", "3D") == "2D"


# --------------------------------------------------------------------------
# 多邊形 / CAD 讀取(只在需要時 import,讓 worker 不必載入 gdstk / ezdxf)
# --------------------------------------------------------------------------

def parse_vertices(text: str) -> list[tuple[float, float]]:
    pts = []
    for line in str(text).replace(";", "\n").splitlines():
        line = line.strip().replace("(", "").replace(")", "")
        if not line or line.startswith("#"):
            continue
        parts = [s for s in line.replace("\t", ",").replace(" ", ",").split(",") if s]
        if len(parts) < 2:
            raise ValueError(f"頂點格式錯誤:「{line}」(要寫成 x, y)")
        pts.append((float(parts[0]), float(parts[1])))
    if len(pts) < 3:
        raise ValueError("多邊形至少要 3 個頂點")
    return pts


def regpoly_vertices(N: int, R: float) -> list[tuple[float, float]]:
    N = max(3, int(N))
    a0 = math.pi / 2 - math.pi / N if N % 2 == 0 else math.pi / 2
    return [(R * math.cos(a0 + 2 * math.pi * i / N), R * math.sin(a0 + 2 * math.pi * i / N)) for i in range(N)]


_cad_cache: dict = {}


def cad_polygons(obj: dict, unit_nm: float) -> list[list[tuple[float, float]]]:
    """GDS / DXF 物件 → 多邊形清單(nm,原始檔案座標)。"""
    from lumeasy import cadio
    key = (obj["shape"], obj.get("file"), obj.get("cell"), obj.get("layer"), obj.get("file_unit"),
           cadio.mtime(obj.get("file")))
    if key not in _cad_cache:
        if obj["shape"] == "gds":
            _cad_cache[key] = cadio.gds_polygons(obj["file"], obj.get("cell", ""), obj.get("layer", "1"))
        else:
            _cad_cache[key] = cadio.dxf_polygons(obj["file"], obj.get("layer", ""),
                                                 FILE_UNIT_NM[obj.get("file_unit", "um")])
    return _cad_cache[key]


def stl_bbox_nm(obj: dict):
    from lumeasy import cadio
    key = ("stl", obj.get("file"), obj.get("file_unit"), cadio.mtime(obj.get("file")))
    if key not in _cad_cache:
        v = cadio.read_stl(obj["file"]) * FILE_UNIT_NM[obj.get("file_unit", "um")]
        _cad_cache[key] = (v, (v[:, 0].min(), v[:, 0].max(), v[:, 1].min(), v[:, 1].max(),
                               v[:, 2].min(), v[:, 2].max()))
    return _cad_cache[key]


# --------------------------------------------------------------------------
# 擺放:每個物件 → 世界座標(nm)。2D 時用 (x, z),y 固定 0。
# --------------------------------------------------------------------------

def local_shape(obj: dict, dim2: bool):
    """回傳 (kind, data, bbox)。bbox = (x0,x1,y0,y1,z0,z1),是物件「原生座標」下的包圍盒。
    kind 決定預覽與 LSF 怎麼畫:rect / circle / ellipse / ring / sphere / poly / pyramid / stl / polys。"""
    s = obj["shape"]
    g = lambda k: float(obj.get(k) or 0.0)
    if s == "box":
        Lx, Ly, H = g("Lx"), g("Ly"), g("H")
        return "rect", {"Lx": Lx, "Ly": Ly, "H": H}, (-Lx / 2, Lx / 2, -Ly / 2, Ly / 2, 0, H)
    if s == "cylinder":
        r, H = g("r"), g("H")
        return "circle", {"r": r, "H": H}, (-r, r, -r, r, 0, H)
    if s == "ellipse":
        rx, ry, H = g("rx"), g("ry"), g("H")
        return "ellipse", {"rx": rx, "ry": ry, "H": H}, (-rx, rx, -ry, ry, 0, H)
    if s == "ring":
        ro, H = g("r_out"), g("H")
        return "ring", {"ro": ro, "ri": g("r_in"), "H": H, "t0": g("theta0"), "t1": g("theta1")}, (-ro, ro, -ro, ro, 0, H)
    if s == "sphere":
        r = g("r")
        return "sphere", {"r": r}, (-r, r, -r, r, 0, 2 * r)
    if s == "pyramid":
        Lx0, Ly0, Lx1, Ly1, H = g("Lx0"), g("Ly0"), g("Lx1"), g("Ly1"), g("H")
        wx, wy = max(Lx0, Lx1), max(Ly0, Ly1)
        return "pyramid", {"Lx0": Lx0, "Ly0": Ly0, "Lx1": Lx1, "Ly1": Ly1, "H": H}, (-wx / 2, wx / 2, -wy / 2, wy / 2, 0, H)
    if s in ("regpoly", "polygon"):
        if s == "regpoly":
            pts = regpoly_vertices(int(obj.get("N", 6)), g("R"))
        else:
            pts = parse_vertices(obj.get("vertices", ""))
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        if dim2:   # 2D:頂點就是 (x, z)
            return "poly", {"pts": pts, "H": 0.0}, (min(xs), max(xs), 0, 0, min(ys), max(ys))
        H = g("H")
        return "poly", {"pts": pts, "H": H}, (min(xs), max(xs), min(ys), max(ys), 0, H)
    if s == "stl":
        if not obj.get("file"):
            raise ValueError(f"{obj['name']}:還沒選 STL 檔案")
        v, bb = stl_bbox_nm(obj)
        return "stl", {"verts": v}, bb
    if s in ("gds", "dxf"):
        if not obj.get("file"):
            raise ValueError(f"{obj['name']}:還沒選 CAD 檔案")
        polys = cad_polygons(obj, 1.0)
        if not polys:
            raise ValueError(f"{obj['name']}:檔案裡找不到這個圖層的多邊形")
        xs = [p[0] for poly in polys for p in poly]
        ys = [p[1] for poly in polys for p in poly]
        if dim2:
            return "polys", {"polys": polys, "H": 0.0}, (min(xs), max(xs), 0, 0, min(ys), max(ys))
        H = g("H")
        return "polys", {"polys": polys, "H": H}, (min(xs), max(xs), min(ys), max(ys), 0, H)
    raise ValueError(f"未知形狀 {s}")


def place_objects(p: dict) -> list[dict]:
    """依序擺放所有物件。回傳每個物件的擺放結果(含停用的,enabled 欄位照抄):
       shift = 原生座標要加的位移 (sx, sy, sz),copies = 陣列每個複本的額外位移,
       bbox = 世界座標包圍盒(含陣列),error = 有問題時的訊息。"""
    dim2 = is2d(p)
    out = []
    prev_top = 0.0
    tops: dict[str, float] = {}
    for obj in p["objects"]:
        r = {"obj": obj, "enabled": bool(obj.get("enabled", True)), "error": None}
        try:
            kind, data, lb = local_shape(obj, dim2)
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            r["error"] = msg if msg.startswith(obj["name"]) else f"{obj['name']}:{msg}"
            out.append(r)
            continue
        x0, x1, y0, y1, z0, z1 = lb
        dx, dy = float(obj.get("dx") or 0), (0.0 if dim2 else float(obj.get("dy") or 0))
        ref = (obj.get("on_top") or "").strip()
        if ref == "@prev":
            base_z = prev_top
        elif ref:
            if ref not in tops:
                r["error"] = f"{obj['name']}:要疊上去的物件「{ref}」必須是啟用的、而且排在這個物件前面"
                out.append(r)
                continue
            base_z = tops[ref]
        else:
            base_z = 0.0
        dz = float(obj.get("dz") or 0) + base_z
        a = obj.get("anchor", "bottom_center")
        if a == "bottom_center":
            sh = (dx - (x0 + x1) / 2, dy - (y0 + y1) / 2, dz - z0)
        elif a == "center":
            sh = (dx - (x0 + x1) / 2, dy - (y0 + y1) / 2, dz - (z0 + z1) / 2)
        elif a == "corner":
            sh = (dx - x0, dy - y0, dz - z0)
        else:
            sh = (dx, dy, dz)
        nx = int(obj.get("nx") or 1) if obj["shape"] in ARRAYABLE else 1
        ny = (1 if dim2 else int(obj.get("ny") or 1)) if obj["shape"] in ARRAYABLE else 1
        px, py = float(obj.get("px") or 0), float(obj.get("py") or 0)
        copies = [((i - (nx - 1) / 2) * px, (j - (ny - 1) / 2) * py)
                  for i in range(nx) for j in range(ny)]
        cxs = [c[0] for c in copies]
        cys = [c[1] for c in copies]
        bb = (x0 + sh[0] + min(cxs), x1 + sh[0] + max(cxs),
              y0 + sh[1] + min(cys), y1 + sh[1] + max(cys),
              z0 + sh[2], z1 + sh[2])
        if dim2:
            bb = (bb[0], bb[1], 0.0, 0.0, bb[4], bb[5])
        r.update(kind=kind, data=data, local=lb, shift=sh, copies=copies, nx=nx, ny=ny, bbox=bb,
                 through=bool(obj.get("through")) and obj["shape"] == "box")
        if r["enabled"]:
            prev_top = bb[5]
            tops[obj["name"]] = bb[5]
        out.append(r)
    return out


def copy_names(obj: dict, nx: int, ny: int) -> list[str]:
    n = obj["name"]
    if nx * ny == 1:
        return [n]
    if ny == 1:
        return [f"{n}_{i}" for i in range(nx)]
    return [f"{n}_{i}_{j}" for i in range(nx) for j in range(ny)]


def compute_region(p: dict, placed: list[dict] | None = None) -> dict:
    """模擬區(nm):{x:(min,max), y:(min,max), z:(min,max)}。"""
    placed = placed if placed is not None else place_objects(p)
    reg = p["region"]
    ok = [r for r in placed if r["enabled"] and not r["error"]]
    solid = [r for r in ok if not r["through"]]
    thru = [r for r in ok if r["through"]]
    out = {}
    for ax, i in (("x", 0), ("y", 2)):
        if ax == "y" and is2d(p):
            out["y"] = (0.0, 0.0)
            continue
        if reg.get(f"{ax}_mode") == "manual":
            c, s = float(reg[f"{ax}_center"]), float(reg[f"{ax}_span"])
            out[ax] = (c - s / 2, c + s / 2)
            continue
        # 貫穿模擬區的基板 / 薄膜會自動延伸,不拿來決定橫向範圍
        m = float(reg.get(f"{ax}_margin", 500))
        if solid:
            lo = min(r["bbox"][i] for r in solid)
            hi = max(r["bbox"][i + 1] for r in solid)
        else:
            lo, hi = -500.0, 500.0
        out[ax] = (lo - m, hi + m)
    if reg.get("z_mode") == "manual":
        c, s = float(reg["z_center"]), float(reg["z_span"])
        out["z"] = (c - s / 2, c + s / 2)
    else:
        lows = [r["bbox"][4] for r in solid] + [r["bbox"][5] for r in thru]
        highs = [r["bbox"][5] for r in ok]
        lo = min(lows) if lows else -500.0
        hi = max(highs) if highs else 500.0
        out["z"] = (lo - float(reg.get("z_margin_bot", 500)), hi + float(reg.get("z_margin_top", 800)))
    return out


def struct_top(p: dict, placed=None) -> float:
    placed = placed if placed is not None else place_objects(p)
    tops = [r["bbox"][5] for r in placed if r["enabled"] and not r["error"]]
    return max(tops) if tops else 0.0


def struct_bottom(p: dict, placed=None) -> float:
    placed = placed if placed is not None else place_objects(p)
    lows = [r["bbox"][4] for r in placed if r["enabled"] and not r["error"] and not r["through"]]
    if not lows:
        lows = [r["bbox"][5] for r in placed if r["enabled"] and not r["error"]]
    return min(lows) if lows else 0.0


def all_names(p: dict) -> list[str]:
    names = []
    for r in place_objects(p):
        if r.get("error"):
            names.append(r["obj"]["name"])
        elif r["kind"] == "polys":
            names += [f"{r['obj']['name']}_{k + 1}" for k in range(len(r["data"]["polys"]))] \
                if r["obj"]["shape"] == "dxf" else [r["obj"]["name"]]
        else:
            names += copy_names(r["obj"], r["nx"], r["ny"])
    names += [s["name"] for s in p["sources"]] + [m["name"] for m in p["monitors"]] + [m["name"] for m in p["mesh"]]
    return names


def unique_name(p: dict, base: str) -> str:
    used = {o["name"] for o in p["objects"]} | {s["name"] for s in p["sources"]} | \
           {m["name"] for m in p["monitors"]} | {m["name"] for m in p["mesh"]} | \
           {m["name"] for m in p["materials"]}
    if base not in used:
        return base
    i = 2
    while f"{base}{i}" in used:
        i += 1
    return f"{base}{i}"


# 欄位的滑鼠提示(長說明放這裡,欄位名稱保持簡短)
TIPS = {
    '疊在…的頂面上': '選一個物件,偏移 z 就從那個物件的頂面開始算;那個物件改高度時,這個會跟著移動。',
    '對齊點': '物件的哪一點要放在下面的「偏移 x, y, z」位置。底面中心最直覺:疊層時偏移 z = 底面高度。',
    '網格優先順序': '物件重疊時,數字小的蓋過數字大的(預設 2)。挖孔物件設 1。',
    '貫穿模擬區': '基板 / 薄膜用:x、y 方向自動延伸穿過模擬區與 PML,不用自己算長度。',
    '頂點(每行一個)': '3D:每行 x, y(俯視的形狀,往上擠出高度 H);2D:每行 x, z(直接就是截面)。',
    '高 H': '只在 3D 用;2D 的頂點已經包含 z。',
    '旋轉角': '繞物件自己的中心、沿 z 軸轉(度,逆時針)。2D 時是在 x-z 截面內轉。',
    '偏振角': '度。z 方向注入時 0° = 電場沿 x。',
    '入射角 θ': '度。垂直(z)注入時 θ > 0 = 光往 +x 偏。',
    '方位角 φ': '度,只限 3D。',
    '到束腰距離': '> 0 表示焦點在光源的傳播方向前方多遠。',
    'x 範圍': '勾「自動」= 比模擬區再大一點(平面波一定要蓋滿模擬區)。注入方向的範圍會被忽略。',
    '偶極方向 θ': '度,與 z 軸的夾角(90° = 水平)。',
    '偶極方向 φ': '度。',
    '第幾個模態': '選「自己指定」時才用。',
    '中心 x': '相對原點 (0,0,0)。',
    '中心 z(高度)': '相對原點往上多高(負的 = 原點下方)。',
    'x 範圍(橫向)': '勾「自動」= 蓋滿整個模擬區。',
    'y 範圍(縱向)': '勾「自動」= 蓋滿整個模擬區。',
    '記錄的場': '勾選要存的電場 E、磁場 H、坡印廷向量 P 分量;power = 穿透率要用的功率。少勾一點可以省記憶體。',
    '頻率點數': '0 = 跟「光源」頁的全域設定。',
    '空間降取樣': '每 n 格存一格;大的 3D 監視器用 2–3 可以省很多記憶體。1 = 不降。',
    '畫場圖': '跑完自動畫 |E|²、|H|² 分布圖(波長在「執行與輸出」頁設定)。',
    '畫頻譜': '跑完自動畫穿透率 T(λ)。',
    '套用到物件': '選一個物件:網格覆寫區自動包住它(再多包「物件外多包一圈」)。不選就用下面的手動範圍。',
    'x 手動範圍': '週期結構請填一個週期的長度,並把 x 邊界設成週期 / Bloch。',
    '網格精度': '1 最粗 … 8 最細;一般 2–3。每加 1,3D 的格子數大約多 1.5–2 倍。',
    '背景折射率': '沒有物件的地方的折射率;空氣 = 1。etch(挖孔)也是這個值。',
    '自動停止門檻': '模擬區裡剩下的能量比例低於這個值就提早停止。',
    '最小網格(nm)': '0 = Lumerical 預設。',
    '輸出格式': '可以複選;PNG 會畫場圖與頻譜。',
    '場圖波長(nm)': '逗號分隔,例如 450, 550, 650;center = 波長範圍的中心;all = 均勻挑 12 個。',
    'CPU 行程數': '0 = 不更改 Lumerical 目前的設定。注意:這是 Lumerical 的全域偏好,會留給之後開的 Lumerical。建議 = 實體核心數 − 1 或 − 2。',
    '同名直接覆寫': '不勾 = 自動加 _01、_02…,舊檔不會被蓋掉。',
    '建好後開 Lumerical': '建好(或跑完)後用 Lumerical 的視窗打開 .fsp,方便目視檢查。',
    '連線逾時(秒)': '開 Lumerical 超過這麼久沒回應,就關掉這次開的 Lumerical 自動重來一次(當天第一次開或午夜前後偶爾會卡)。',
}


# --------------------------------------------------------------------------
# 簡易模式:哪些欄位是進階的、哪些欄位要看別的欄位才顯示
# --------------------------------------------------------------------------
ADVANCED = {
    "object": {"enabled", "anchor", "rot", "mesh_order"},
    "source": {"enabled", "x", "y", "sx", "sy", "sz", "phi", "pwtype", "focus"},
    "monitor": {"enabled", "x", "y", "fpoints", "downsample"},
    "mesh": {"enabled", "buffer"},
    "region": {"bg_index", "shutoff", "pml_layers", "pml_type", "min_mesh", "x_center", "y_center", "z_center"},
    "global": {"fpoints"},
    "run": {"processes", "overwrite", "open_timeout"},
}
_MON_AXES = {"z": "xy", "x": "yz", "y": "xz", "point": "", "lx": "x", "ly": "y", "lz": "z", "3d": "xyz"}
SHOW_IF = {
    "monitor": {
        "sx": lambda d: "x" in _MON_AXES.get(d.get("orient"), ""),
        "sy": lambda d: "y" in _MON_AXES.get(d.get("orient"), ""),
        "sz": lambda d: "z" in _MON_AXES.get(d.get("orient"), ""),
        "outputs": lambda d: d.get("kind") in ("power", "profile", "time"),
        "fpoints": lambda d: d.get("kind") in ("power", "profile", "index"),
        "plot_field": lambda d: d.get("kind") in ("power", "profile"),
        "plot_spectrum": lambda d: d.get("kind") in ("power", "profile"),
        "movie_comp": lambda d: d.get("kind") == "movie",
        "downsample": lambda d: d.get("kind") != "movie",
    },
    "region": {
        "x_margin": lambda d: d.get("x_mode") != "manual",
        "x_center": lambda d: d.get("x_mode") == "manual", "x_span": lambda d: d.get("x_mode") == "manual",
        "y_margin": lambda d: d.get("y_mode") != "manual",
        "y_center": lambda d: d.get("y_mode") == "manual", "y_span": lambda d: d.get("y_mode") == "manual",
        "z_margin_top": lambda d: d.get("z_mode") != "manual", "z_margin_bot": lambda d: d.get("z_mode") != "manual",
        "z_center": lambda d: d.get("z_mode") == "manual", "z_span": lambda d: d.get("z_mode") == "manual",
    },
    "source": {
        "mode_num": lambda d: d.get("mode") == "user select",
    },
    "object": {
        "Lx": lambda d: not d.get("through"), "Ly": lambda d: not d.get("through"),
        "py": lambda d: int(d.get("ny") or 1) > 1, "px": lambda d: int(d.get("nx") or 1) > 1 or int(d.get("ny") or 1) > 1,
    },
    "mesh": {
        "x": lambda d: not d.get("target"), "y": lambda d: not d.get("target"), "z": lambda d: not d.get("target"),
        "sx": lambda d: not d.get("target"), "sy": lambda d: not d.get("target"), "sz": lambda d: not d.get("target"),
        "buffer": lambda d: bool(d.get("target")),
    },
}


SECTIONS = {
    "object": [({"name", "enabled", "material"}, "基本"), ({"anchor", "dx", "dy", "dz", "on_top", "rot"}, "位置"),
               ({"nx", "ny", "px", "py"}, "陣列(重複排列)"), ({"mesh_order"}, "進階"), (None, "尺寸")],
    "source": [({"name", "enabled"}, "基本"), ({"x", "y", "z", "sx", "sy", "sz"}, "位置與範圍"), (None, "光的設定")],
    "monitor": [({"name", "enabled", "kind", "orient"}, "種類"), ({"x", "y", "z", "sx", "sy", "sz"}, "位置(以原點為參考)"),
                (None, "記錄與輸出")],
    "region": [({"bc_x", "bc_y", "bc_zmin", "bc_zmax"}, "邊界"), ({"sim_time", "mesh_acc"}, "精度與時間"),
               ({"bg_index", "shutoff", "pml_layers", "pml_type", "min_mesh"}, "進階"), (None, "範圍")],
    "run": [({"formats", "field_wl"}, "輸出"), (None, "執行")],
    "mesh": [({"name", "enabled", "target", "buffer"}, "套用對象"), ({"dx", "dy", "dz"}, "網格大小"), (None, "手動範圍")],
}


def tag_fields(fields, group, stype=None):
    """複製欄位定義,加上 adv(進階)、show(條件顯示)與 sec(表單段落)。"""
    adv = set(ADVANCED.get(group, ()))
    if group == "source" and stype in ("mode", "dipole"):
        adv -= {"x", "y"}
    if group == "source" and stype == "mode":
        adv -= {"sy", "sz", "sx"}
    out = []
    for f in fields:
        g = dict(f)
        if g["key"] in adv:
            g["adv"] = True
        fn = SHOW_IF.get(group, {}).get(g["key"])
        if fn:
            g["show"] = fn
        for keys, sec in SECTIONS.get(group, []):
            if keys is None or g["key"] in keys:
                g["sec"] = sec
                break
        if g["key"] in LUMPROP.get(group, {}):
            g["lum"] = LUMPROP[group][g["key"]]
        out.append(g)
    return out


# 滑鼠提示裡的「對應 Lumerical 的哪個設定」
LUMPROP = {
    "object": {
        "name": '物件的 "name"', "enabled": "沒勾就不建這個物件", "material": '"material"(etch = 背景折射率,用來挖孔)',
        "Lx": '"x span"', "Ly": '"y span"', "H": '"z span"(2D 時是 "y span")', "through": '"x span" / "y span" 自動設成模擬區的 2 倍以上',
        "r": '"radius"', "rx": '"radius"(make ellipsoid = 1)', "ry": '"radius 2"', "r_out": '"outer radius"', "r_in": '"inner radius"',
        "theta0": '"theta start"', "theta1": '"theta stop"', "Lx0": '"x span bottom"', "Ly0": '"y span bottom"',
        "Lx1": '"x span top"', "Ly1": '"y span top"', "N": '程式算好頂點後寫進 polygon 的 "vertices"', "R": "多邊形的外接圓半徑",
        "vertices": 'polygon 物件的 "vertices"', "file": "stlimport / gdsimport(DXF 由程式轉成 polygon)",
        "file_unit": "stlimport 的單位倍率", "cell": "gdsimport 的 cell 名稱", "layer": "gdsimport 的圖層(layer:datatype)",
        "anchor": '程式依對齊點換算成 Lumerical 的中心座標 "x" "y" "z"', "dx": '"x"', "dy": '"y"', "dz": '"z"(2D 時是 "y")',
        "on_top": "程式自動算 z(Lumerical 沒有這個概念)", "rot": '"first axis" = z、"rotation 1"',
        "nx": "Lumerical 腳本用 copy() 迴圈複製", "ny": "Lumerical 腳本用 copy() 迴圈複製", "px": "copy() 的 x 位移",
        "py": "copy() 的 y 位移", "mesh_order": '"override mesh order from material database" + "mesh order"',
    },
    "source": {
        "name": '"name"', "enabled": "沒勾就不建", "axis": '"injection axis"', "direction": '"direction"(Forward / Backward)',
        "pwtype": '"plane wave type"', "pol": '"polarization angle"', "pol2d": '"polarization angle"(TE = 90°、TM = 0°,實測過)',
        "theta": '"angle theta"(程式已統一正負號)', "phi": '"angle phi"', "w0": '"waist radius w0"', "focus": '"distance from waist"',
        "mode": '"mode selection"', "mode_num": '"selected mode number"', "dtype": '"dipole type"',
        "x": '"x"', "y": '"y"', "z": '"z"(2D 時是 "y")', "sx": '"x span"', "sy": '"y span"', "sz": '"z span"',
    },
    "monitor": {
        "name": '"name"', "enabled": "沒勾就不建", "kind": "addpower / addprofile / addindex / addtime / addmovie",
        "orient": '"monitor type"(2D Z-normal、Linear X …;2D 模擬時程式自動換軸)', "x": '"x"', "y": '"y"', "z": '"z"(2D 時是 "y")',
        "sx": '"x span"', "sy": '"y span"', "sz": '"z span"', "outputs": '"output Ex" … "output Pz"、"output power"',
        "fpoints": '"override global monitor settings" + "frequency points"', "downsample": '"down sample X / Y / Z"',
        "movie_comp": '"field component"', "plot_field": "LumEasy 跑完自己畫(不是 Lumerical 的設定)",
        "plot_spectrum": 'LumEasy 跑完用 getresult(…, "T") 畫',
    },
    "region": {
        "x_mode": 'FDTD 的 "x" / "x span"', "x_margin": 'FDTD 的 "x span"(程式算)', "x_center": 'FDTD 的 "x"', "x_span": 'FDTD 的 "x span"',
        "y_mode": 'FDTD 的 "y" / "y span"', "y_margin": 'FDTD 的 "y span"(程式算)', "y_center": 'FDTD 的 "y"', "y_span": 'FDTD 的 "y span"',
        "z_mode": 'FDTD 的 "z" / "z span"(2D 時是 y)', "z_margin_top": 'FDTD 的 "z max"(程式算)', "z_margin_bot": 'FDTD 的 "z min"(程式算)',
        "z_center": 'FDTD 的 "z"', "z_span": 'FDTD 的 "z span"', "bc_x": '"x min bc" / "x max bc"', "bc_y": '"y min bc" / "y max bc"',
        "bc_zmin": '"z min bc"(2D 時是 "y min bc")', "bc_zmax": '"z max bc"(2D 時是 "y max bc")', "sim_time": '"simulation time"',
        "mesh_acc": '"mesh accuracy"', "bg_index": '"index"', "shutoff": '"auto shutoff min"', "pml_layers": '"pml layers"',
        "pml_type": '"pml type"', "min_mesh": '"min mesh step"',
    },
    "global": {"wl_start": 'setglobalsource("wavelength start")', "wl_stop": 'setglobalsource("wavelength stop")',
               "fpoints": 'setglobalmonitor("frequency points")'},
    "mesh": {"name": '"name"', "enabled": "沒勾就不建", "target": "mesh 物件的範圍自動包住這個物件", "buffer": "包圍範圍再多加的距離",
             "x": '"x"', "y": '"y"', "z": '"z"', "sx": '"x span"', "sy": '"y span"', "sz": '"z span"',
             "dx": '"override x mesh" + "dx"', "dy": '"override y mesh" + "dy"', "dz": '"override z mesh" + "dz"'},
    "run": {"formats": "LumEasy 用 getresult 取資料後自己存檔", "field_wl": "LumEasy 畫場圖時挑的波長",
            "processes": 'setresource("FDTD", 1, "processes", N)', "overwrite": "LumEasy 的存檔規則",
            "open_gui": "用 fdtd-solutions.exe 開啟存好的 .fsp", "open_timeout": "LumEasy 的看門狗(只關自己開的 Lumerical)"},
}
