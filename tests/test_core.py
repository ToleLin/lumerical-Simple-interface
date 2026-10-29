"""不需要 Lumerical 的單元測試:python -m pytest tests"""
import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lumeasy import examples, lsf, materials as MAT, model as M  # noqa: E402


def test_nk_eps_roundtrip():
    for n, k in ((1.45, 0), (4.0, 0.3), (0.05, 4.2)):        # 玻璃、矽、銀
        e1, e2 = MAT.nk_to_eps(n, k)
        assert abs(e1 - (n * n - k * k)) < 1e-12 and abs(e2 - 2 * n * k) < 1e-12
        n2, k2 = MAT.eps_to_nk(e1, e2)
        assert abs(n2 - n) < 1e-9 and abs(k2 - k) < 1e-9


def test_x_units():
    assert abs(MAT.x_to_wl_nm(0.5, "um") - 500) < 1e-9
    assert abs(MAT.x_to_wl_nm(599.585, "THz") - 500) < 1e-3
    assert abs(MAT.x_to_wl_nm(2.4797, "eV") - 500) < 0.05


def test_to_nk_sorts_and_converts_eps(tmp_path):
    f = tmp_path / "m.txt"
    # (THz, ε1, ε2),頻率遞增 → 波長遞減
    f.write_text("600 2.25 0\n500 2.30 0.01\n400 2.40 0.02\n")
    hdr, data, _ = MAT.read_table(str(f))
    wl, n, k, _ = MAT.to_nk(data, "THz", "eps")
    assert np.all(np.diff(wl) > 0)
    assert abs(n[0] - 1.5) < 1e-6                  # 600 THz → 500 nm,ε1 2.25 → n 1.5
    assert abs(n[-1] - math.sqrt(2.40)) < 1e-3     # 400 THz → 749 nm,ε1 2.40(ε2 很小)


def test_refractiveindex_info_format(tmp_path):
    f = tmp_path / "ri.csv"
    f.write_text("wl,n\n0.4,1.47\n0.6,1.46\n0.8,1.45\n\nwl,k\n0.4,0.001\n0.8,0.0\n")
    hdr, data, note = MAT.read_table(str(f))
    assert data.shape == (3, 3) and "refractiveindex" in note
    xu, yk, msg, sure = MAT.guess_format(hdr, data)
    assert xu == "um" and yk == "nk"


def test_negative_imag_flipped():
    data = np.array([[500, 2.0, -0.1], [600, 2.0, -0.2]])
    wl, n, k, notes = MAT.to_nk(data, "nm", "nk")
    assert np.all(k > 0) and notes


def test_place_stack_on_top():
    p = M.new_project()
    a = M.new_object("box", "film"); a.update(H=100)
    b = M.new_object("cylinder", "pil"); b.update(H=300, on_top="film")
    p["objects"] = [a, b]
    placed = M.place_objects(p)
    assert placed[1]["bbox"][4] == pytest.approx(100) and placed[1]["bbox"][5] == pytest.approx(400)
    a["H"] = 250       # 下層變厚,上層跟著移動
    assert M.place_objects(p)[1]["bbox"][4] == pytest.approx(250)


def test_anchor_corner_and_array():
    p = M.new_project()
    o = M.new_object("box", "b"); o.update(Lx=100, Ly=50, H=10, anchor="corner", nx=3, px=200)
    p["objects"] = [o]
    r = M.place_objects(p)[0]
    # 陣列以偏移點為中心排開:第一個複本在 -200
    assert r["bbox"][0] == pytest.approx(-200) and r["bbox"][1] == pytest.approx(300)
    assert M.copy_names(o, 3, 1) == ["b_0", "b_1", "b_2"]


def test_region_auto_ignores_through_layers():
    p = examples.pillar_unit_cell_3d()
    p["region"].update(x_mode="auto", x_margin=100, y_mode="auto", y_margin=100)
    reg = M.compute_region(p)
    assert reg["x"] == pytest.approx((-200, 200))      # 只看柱子(r=100)+ 邊距,不看基板


def test_examples_validate_and_generate():
    for f in examples.EXAMPLES.values():
        p = f()
        errs = [m for lv, m in lsf.validate(p, MAT.DEFAULT_BUILTINS) if lv == "error"]
        assert not errs, errs
        sc = lsf.generate(p, "C:/x.fsp")
        assert sc.stmts[-1].code.startswith("save(")


def test_2d_maps_z_to_y():
    p = examples.grating_2d()
    codes = [s.code for s in lsf.generate(p).stmts]
    assert 'set("dimension","2D");' in codes
    assert not any('"z span"' in c for c in codes if "addfdtd" not in c)
    assert 'set("injection axis","y-axis");' in codes


@pytest.mark.parametrize("d2,direction,expect", [(False, "neg", -10), (False, "pos", 10), (True, "neg", 10), (True, "pos", -10)])
def test_theta_sign_convention(d2, direction, expect):
    """實測(2020 R2):統一成「垂直注入 θ > 0 = 往 +x 偏」需要的 Lumerical θ。"""
    p = examples.grating_2d() if d2 else examples.pillar_unit_cell_3d()
    s = p["sources"][0]
    s.update(theta=10, direction=direction, axis="z")
    codes = [c.code for c in lsf.generate(p).stmts if "angle theta" in c.code]
    assert codes == [f'set("angle theta",{expect});']


def test_sampled_material_uses_permittivity():
    p = examples.pillar_unit_cell_3d()
    p["materials"].append({"name": "m", "kind": "file", "wl_nm": [500, 600], "n": [2.0, 2.0], "k": [0.1, 0.1]})
    codes = [s.code for s in lsf.generate(p).stmts if s.code.startswith("leme")]
    assert "3.99+0.4i" in codes[0]     # (2 + 0.1i)² = 3.99 + 0.4i


def test_validate_catches_duplicates_and_missing_material():
    p = examples.pillar_unit_cell_3d()
    p["objects"][1]["name"] = "substrate"
    p["objects"][0]["material"] = "NoSuchMaterial"
    msgs = " ".join(m for lv, m in lsf.validate(p, MAT.DEFAULT_BUILTINS) if lv == "error")
    assert "名稱重複" in msgs and "NoSuchMaterial" in msgs


def test_calc_expressions():
    from lumeasy.gui.forms import calc
    assert calc("2*150") == 300 and calc("(400-80)/2") == 160 and calc("-3^2") == -9
    with pytest.raises(ValueError):
        calc("__import__('os')")
