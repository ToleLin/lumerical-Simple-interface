"""內建範例(介面「範例」選單與測試共用)。"""
from __future__ import annotations

from lumeasy import model as M


def pillar_unit_cell_3d() -> dict:
    """玻璃基板上的一根 TiO2 圓柱,週期 400 nm 的單位晶胞,平面波由上往下打。"""
    p = M.new_project()
    p["project"].update(name="example_pillar_3D", dimension="3D", unit="nm")
    p["materials"] = [{"name": "TiO2_const", "kind": "const_nk", "n": 2.4, "k": 0.0, "color": "#E15759"}]
    sub = M.new_object("box", "substrate")
    sub.update(material="SiO2 (Glass) - Palik", H=1000.0, dz=-1000.0, through=True)
    pil = M.new_object("cylinder", "pillar")
    pil.update(material="TiO2_const", r=100.0, H=300.0)
    p["objects"] = [sub, pil]
    p["region"].update(x_mode="manual", x_span=400.0, y_mode="manual", y_span=400.0,
                       bc_x="Periodic", bc_y="Periodic", z_margin_top=800.0, z_margin_bot=500.0,
                       sim_time=500.0, mesh_acc=2)
    p["global"].update(wl_start=450.0, wl_stop=650.0, fpoints=51)
    src = M.new_source("planewave", "light")
    src.update(z=700.0, direction="neg")
    p["sources"] = [src]
    p["monitors"] = [
        M.new_monitor("R_top", kind="power", orient="z", z=950.0, outputs=["Ex", "Ey", "Ez", "Hx", "Hy", "Hz", "Px", "Py", "Pz", "power"], plot_field=False),
        M.new_monitor("T_bottom", kind="power", orient="z", z=-300.0, plot_field=False),
        M.new_monitor("field_XZ", kind="profile", orient="y", y=0.0, z=150.0, plot_spectrum=False),
        M.new_monitor("index_XZ", kind="index", orient="y", y=0.0, z=150.0, plot_spectrum=False),
    ]
    p["run"].update(formats=["npz", "csv", "png", "json"], field_wl="center")
    return p


def grating_2d() -> dict:
    """2D(x-z 截面):玻璃上的 Si3N4 薄膜 + 5 條梯形光柵,10° 斜入射。"""
    p = M.new_project()
    p["project"].update(name="example_grating_2D", dimension="2D", unit="nm")
    sub = M.new_object("box", "substrate")
    sub.update(material="SiO2 (Glass) - Palik", H=1000.0, dz=-1000.0, through=True)
    film = M.new_object("box", "film")
    film.update(material="Si3N4 (Silicon Nitride) - Phillip", H=150.0, through=True)
    gr = M.new_object("pyramid", "tooth")
    gr.update(material="Si3N4 (Silicon Nitride) - Phillip", Lx0=220.0, Lx1=160.0, H=120.0, on_top="film",
              nx=5, px=400.0)
    p["objects"] = [sub, film, gr]
    p["region"].update(x_mode="auto", x_margin=600.0, z_margin_top=900.0, z_margin_bot=600.0,
                       sim_time=600.0, mesh_acc=2)
    p["global"].update(wl_start=500.0, wl_stop=700.0, fpoints=41)
    src = M.new_source("gaussian", "beam")
    src.update(z=800.0, direction="neg", w0=800.0, theta=10.0, pol2d="TE")
    p["sources"] = [src]
    p["monitors"] = [
        M.new_monitor("top", kind="power", orient="z", z=1000.0, plot_field=False),
        M.new_monitor("bottom", kind="power", orient="z", z=-450.0, plot_field=False),
        M.new_monitor("field", kind="profile", orient="y", z=200.0, plot_spectrum=False),
    ]
    p["run"].update(formats=["npz", "csv", "png", "json"], field_wl="center")
    return p


EXAMPLES = {
    "3D 單位晶胞:玻璃上的 TiO2 圓柱(週期邊界、平面波)": pillar_unit_cell_3d,
    "2D 截面:Si3N4 薄膜 + 梯形光柵(高斯光斜入射)": grating_2d,
}
