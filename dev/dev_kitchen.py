"""把所有形狀、光源、監視器、材料種類、CAD 匯入都放進一個 3D 專案(只建模測試)。"""
import pathlib
import numpy as np
from lumeasy import model as M

here = pathlib.Path(__file__).resolve().parent


def make_dxf():
    import ezdxf
    doc = ezdxf.new()
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (0.6, 0), (0.6, 0.2), (0, 0.2)], close=True, dxfattribs={"layer": "A"})
    msp.add_circle((1.2, 0.5), 0.15, dxfattribs={"layer": "A"})
    msp.add_lwpolyline([(0, 0), (1, 1)], dxfattribs={"layer": "B"})   # 不封閉:要被略過
    p = here / "test.dxf"
    doc.saveas(p)
    return str(p)


def kitchen():
    p = M.new_project()
    p["project"].update(name="kitchen_3D", dimension="3D")
    wl = np.linspace(400, 800, 41)
    p["materials"] = [
        {"name": "MyNK", "kind": "const_nk", "n": 2.1, "k": 0.01, "color": "#E15759"},
        {"name": "MyEps", "kind": "const_eps", "e1": -10.0, "e2": 1.0, "color": "#C0C4CC"},
        {"name": "MyFile", "kind": "file", "wl_nm": wl.tolist(), "n": (3.5 + 0.0 * wl).tolist(),
         "k": (0.01 + 0 * wl).tolist(), "fit_tol": 0.001, "max_coef": 10, "color": "#59A14F"},
        {"name": "Al_fit", "kind": "builtin_copy", "base": "Al (Aluminium) - Palik", "fit_tol": 0.001, "max_coef": 12},
    ]
    objs = []
    o = M.new_object("box", "sub"); o.update(material="SiO2 (Glass) - Palik", H=500, dz=-500, through=True); objs.append(o)
    o = M.new_object("box", "blk"); o.update(material="MyNK", Lx=300, Ly=200, H=100, dx=-800, rot=20); objs.append(o)
    o = M.new_object("cylinder", "cyl"); o.update(material="MyFile", r=80, H=200, dx=-400, nx=2, ny=3, px=200, py=200); objs.append(o)
    o = M.new_object("ellipse", "ell"); o.update(material="MyNK", rx=120, ry=60, H=100, dx=0, dy=600); objs.append(o)
    o = M.new_object("ring", "rng"); o.update(material="MyEps", r_out=200, r_in=120, H=80, dx=400, mesh_order=1); objs.append(o)
    o = M.new_object("sphere", "sph"); o.update(material="Al_fit", r=60, dx=800, on_top="@prev"); objs.append(o)
    o = M.new_object("pyramid", "pyr"); o.update(material="MyNK", dx=0, dy=-700); objs.append(o)
    o = M.new_object("regpoly", "hex"); o.update(material="MyNK", N=6, R=100, dx=-800, dy=-700); objs.append(o)
    o = M.new_object("polygon", "tri"); o.update(material="etch", dx=800, dy=-700); objs.append(o)
    o = M.new_object("stl", "stlpart"); o.update(material="MyNK", file=str(here / "test.stl"), file_unit="um", dx=0, dy=1500, anchor="bottom_center"); objs.append(o)
    o = M.new_object("gds", "gdspart"); o.update(material="MyNK", file=str(here / "test.gds"), layer="1", H=150, dx=1500, dy=1500); objs.append(o)
    o = M.new_object("dxf", "dxfpart"); o.update(material="MyNK", file=make_dxf(), layer="A", file_unit="um", H=120, dx=-1500, dy=1500); objs.append(o)
    p["objects"] = objs
    p["mesh"] = [dict(M.defaults(M.MESH_FIELDS), name="m_cyl", target="cyl", dx=10, dy=10, dz=10)]
    p["region"].update(bc_x="Bloch", bc_y="PML", sim_time=200)
    srcs = []
    for t in M.SOURCE_TYPES:
        s = M.new_source(t, "s_" + t); srcs.append(s)
    p["sources"] = srcs
    mons = []
    for kind, _ in M.MON_KINDS:
        for orient in ("z", "x", "y", "point", "lx", "3d"):
            if kind == "movie" and orient not in ("x", "y", "z"):
                continue
            if kind == "index" and orient in ("point", "lx"):
                continue
            mons.append(M.new_monitor(f"m_{kind}_{orient}", kind=kind, orient=orient, z=100, fpoints=5 if kind != "time" else 0, downsample=2))
    p["monitors"] = mons
    return p
