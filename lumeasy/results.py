"""跑完之後:從 Lumerical 取資料、存成各種格式、畫場圖與頻譜、檢查有沒有發散。

自動處理的陷阱:
  * Lumerical 回傳的波長陣列是遞減的(內部以頻率遞增存)→ 一律先依波長排序再輸出。
  * 向量資料集只有 "E" / "H" / "P"(最後一軸是 x、y、z 分量),沒有 "Ex"。
  * 很多數值是 complex dtype(虛部 0)→ 存 JSON 前取實部。
  * 2D 模擬:Lumerical 的 x-y 換回使用者的 x-z(座標與場分量都換)。
  * 引擎發散不會讓 run() 失敗 → 讀引擎 log 判斷。
"""
from __future__ import annotations

import json
import math
import os
import re

import numpy as np

C0 = 299792458.0


# --------------------------------------------------------------------------
# 取資料
# --------------------------------------------------------------------------

def list_monitors(fdtd) -> list[tuple[str, str]]:
    fdtd.eval('lemlist = ""; selectall; lemn = getnumber; '
              'for(lemi=1:lemn){ lemlist = lemlist + get("name",lemi) + "|" + get("type",lemi) + endl; }')
    s = str(fdtd.getv("lemlist"))
    out = []
    for line in s.splitlines():
        if "|" in line:
            n, t = line.split("|", 1)
            if "monitor" in t.lower() or t in ("DFTMonitor", "IndexMonitor", "TimeMonitor", "MovieMonitor"):
                out.append((n.strip(), t.strip()))
    return out


def _clean(d) -> dict:
    out = {}
    if not isinstance(d, dict):
        return {"value": np.asarray(d)}
    for k, v in d.items():
        if k == "Lumerical_dataset":
            continue
        if isinstance(v, dict):
            continue
        a = np.asarray(v)
        if np.iscomplexobj(a) and np.all(a.imag == 0):
            a = a.real
        out[k] = a
    return out


def to_user_coords(ds: dict, d2: bool) -> dict:
    """2D:Lumerical (x, y, z) → 我們的 (x, z, y)。"""
    if not d2:
        return ds
    out = dict(ds)
    if "y" in ds:
        out["z"] = ds["y"]
        out["y"] = ds.get("z", np.zeros(1))
    for k in ("E", "H", "P"):
        a = ds.get(k)
        if a is not None and a.ndim == 5:
            a = np.swapaxes(a, 1, 2)
            if a.shape[-1] == 3:
                a = a[..., [0, 2, 1]]
            out[k] = a
    if "index_y" in ds and "index_z" in ds:
        out["index_y"], out["index_z"] = ds["index_z"], ds["index_y"]
    for k in ("index_x", "index_y", "index_z"):
        a = out.get(k)
        if a is not None and a.ndim >= 3:
            out[k] = np.swapaxes(a, 1, 2)
    return out


def extract(fdtd, wanted: list[str] | None, d2: bool, log=print) -> dict:
    """回傳 {監視器: {資料集: {鍵: 陣列}}}。wanted=None → 全部有結果的監視器。"""
    mons = list_monitors(fdtd)
    names = [n for n, _ in mons] if wanted is None else wanted
    types = dict(mons)
    out = {}
    for name in names:
        try:
            has = int(np.real(fdtd.haveresult(name)))
        except Exception:  # noqa: BLE001
            has = 0
        if not has:
            log(f"監視器 {name} 沒有結果(可能被停用、在模擬區外,或模擬沒有跑完)")
            continue
        try:
            dsn = [s.strip() for s in str(fdtd.getresult(name)).splitlines() if s.strip()]
        except Exception as e:  # noqa: BLE001
            log(f"監視器 {name} 讀不到資料清單:{e}")
            continue
        res = {"_type": types.get(name, "")}
        for ds in dsn:
            # 只取需要的資料集:farfield 會觸發遠場計算(隱藏模式下會停住),Ex… 是 E 的重複
            if ds not in ("E", "H", "P", "T", "index"):
                continue
            try:
                res[ds] = to_user_coords(_clean(fdtd.getresult(name, ds)), d2)
            except Exception as e:  # noqa: BLE001
                log(f"  {name}/{ds} 讀取失敗:{str(e)[:120]}")
        if "T" not in res and types.get(name) == "DFTMonitor":
            try:
                T = np.real(np.asarray(fdtd.transmission(name))).ravel()
                f = np.real(np.asarray(fdtd.getdata(name, "f"))).ravel()
                res["T"] = {"T": T, "f": f, "lambda": C0 / f}
            except Exception:  # noqa: BLE001
                pass
        out[name] = res
        log(f"取得 {name}:{', '.join(k for k in res if not k.startswith('_'))}")
    return out


# --------------------------------------------------------------------------
# 引擎 log 檢查
# --------------------------------------------------------------------------

PROG = re.compile(r"([\d.]+)% complete\. Max time remaining: ([^.]*)\. Auto Shutoff: ([-+\deE.]+)")


def engine_log_path(fsp: str) -> str:
    return os.path.splitext(fsp)[0] + "_p0.log"


def check_engine_log(fsp: str, shutoff_min: float = 1e-5) -> dict:
    p = engine_log_path(fsp)
    info = {"log": p, "status": "unknown", "messages": []}
    if not os.path.isfile(p):
        info["messages"].append("找不到引擎 log(_p0.log)")
        return info
    with open(p, encoding="utf-8", errors="replace") as f:
        txt = f.read()
    shut = [float(m.group(3)) for m in PROG.finditer(txt)]
    m = re.search(r"Simulation size in gridpoints: ([^\n]+)", txt)
    if m:
        info["gridpoints"] = m.group(1).strip()
    m = re.search(r"Overall wall time measurements in seconds: ([\d.]+)", txt)
    if m:
        info["wall_s"] = float(m.group(1))
    low = txt.lower()
    if "diverg" in low:
        info["status"] = "diverged"
        info["messages"].append("引擎報告場在發散(fields are diverging):結果不可信。常見原因:色散材料擬合 × PML、"
                                "網格太細、金屬下方放 PML。可試:延伸進 PML 的色散層改固定 n、換舊版 UPML、改網格。")
    elif "sufficient memory" in low:
        info["status"] = "memory"
        info["messages"].append("記憶體不足:監視器資料沒存到。請降取樣監視器、縮小監視器或減少頻率點。")
    elif shut and shut[-1] > 10:
        info["status"] = "diverged"
        info["messages"].append(f"Auto Shutoff 最後 = {shut[-1]:.3g}(> 10),幾乎確定發散。")
    elif "simulation completed successfully" in low:
        info["status"] = "ok"
        if shut and shut[-1] > max(100 * shutoff_min, 1e-3):
            info["status"] = "not_converged"
            info["messages"].append(f"模擬時間跑滿了但能量還剩 {shut[-1]:.2g}(沒衰減完):頻譜可能有截斷漣漪,"
                                    "窄共振附近的數字偏差較大。可以加長模擬時間。")
    else:
        info["messages"].append("引擎 log 沒有寫「Simulation completed successfully」:模擬可能沒有正常結束。")
    if shut:
        info["final_shutoff"] = shut[-1]
    return info


def check_power(data: dict) -> list[str]:
    w = []
    for mon, res in data.items():
        T = res.get("T", {}).get("T")
        if T is not None and np.size(T) and np.nanmax(np.abs(T)) > 1.02:
            w.append(f"監視器 {mon} 的 |T| 最大 {np.nanmax(np.abs(T)):.3f} > 1:可能發散、監視器擺在光源旁邊,"
                     "或 PML 設定把功率參考弄壞了。")
    return w


# --------------------------------------------------------------------------
# 存檔
# --------------------------------------------------------------------------

def _safe(s: str, n=60) -> str:
    s = re.sub(r"[^0-9A-Za-z_]", "_", s)
    if not s or not s[0].isalpha():
        s = "m_" + s
    return s[:n]


def _wl_sorted(ds: dict):
    """回傳(依波長遞增的索引, 波長 nm)。"""
    if "lambda" in ds:
        wl = np.real(np.asarray(ds["lambda"])).ravel() * 1e9
    elif "f" in ds:
        wl = C0 / np.real(np.asarray(ds["f"])).ravel() * 1e9
    else:
        return None, None
    o = np.argsort(wl)
    return o, wl[o]


def save_all(data: dict, out_dir: str, base: str, formats: list[str], field_wl: str,
             unit: str, d2: bool, summary_extra: dict | None = None, log=print,
             plot_cfg: dict | None = None) -> list[str]:
    """plot_cfg = {監視器: {"field": bool, "spectrum": bool}};沒列的監視器兩種都畫。"""
    plot_cfg = plot_cfg or {}
    os.makedirs(out_dir, exist_ok=True)
    files = []
    flat = {}
    for mon, res in data.items():
        for ds, d in res.items():
            if ds.startswith("_"):
                continue
            for k, v in d.items():
                flat[(mon, ds, k)] = v
    if "npz" in formats and flat:
        p = os.path.join(out_dir, f"{base}_results.npz")
        np.savez_compressed(p, **{f"{m}__{d}__{k}": v for (m, d, k), v in flat.items()})
        files.append(p)
    if "mat" in formats and flat:
        from scipy.io import savemat
        nested = {}
        for (m, d, k), v in flat.items():
            nested.setdefault(_safe(m), {}).setdefault(_safe(d), {})[_safe(k, 30)] = v
        p = os.path.join(out_dir, f"{base}_results.mat")
        savemat(p, nested, do_compression=True, long_field_names=True)
        files.append(p)
    if "h5" in formats and flat:
        try:
            import h5py
            p = os.path.join(out_dir, f"{base}_results.h5")
            with h5py.File(p, "w") as h:
                h.attrs["coords"] = "x-z (2D)" if d2 else "x-y-z"
                for (m, d, k), v in flat.items():
                    h.create_dataset(f"{m}/{d}/{k}", data=v, compression="gzip")
            files.append(p)
        except ImportError:
            log("沒有安裝 h5py,略過 .h5")
    text_fmts = [f for f in ("csv", "txt") if f in formats]
    scale = 1e9 if unit == "nm" else 1e6
    for mon, res in data.items():
        T = res.get("T")
        if T is not None and "T" in T:
            o, wl = _wl_sorted(T)
            if o is not None:
                tt = np.real(np.asarray(T["T"])).ravel()[o]
                arr = np.column_stack([wl, C0 / (wl * 1e-9) / 1e12, tt])
                for fm in text_fmts:
                    p = os.path.join(out_dir, f"{base}_{mon}_spectrum.{fm}")
                    np.savetxt(p, arr, delimiter="," if fm == "csv" else "\t",
                               header="wavelength_nm,frequency_THz,T".replace(",", "," if fm == "csv" else "\t"),
                               comments="", fmt="%.8g")
                    files.append(p)
    # 場圖(PNG)與場的文字檔
    wls_req = _parse_wls(field_wl)
    plots = []
    for mon, res in data.items():
        if not plot_cfg.get(mon, {}).get("field", True):
            continue
        for comp in ("E", "H"):
            ds = res.get(comp)
            if ds is None or comp not in ds:
                continue
            o, wl = _wl_sorted(ds)
            A = np.asarray(ds[comp])
            if A.ndim != 5:
                continue
            I = np.sum(np.abs(A) ** 2, axis=-1)          # (nx, ny, nz, nf)
            if wl is None:
                continue
            idxs = _pick(wl, wls_req)
            for j in idxs:
                fi = o[j]
                I2 = I[..., fi]
                for fm in text_fmts:
                    p = _field_text(I2, ds, out_dir, f"{base}_{mon}_{comp}2_{wl[j]:.1f}nm.{fm}", fm, scale, comp)
                    if p:
                        files.append(p)
                plots.append((mon, comp, wl[j], I2, ds))
    if "png" in formats:
        files += _plots(data, plots, out_dir, base, unit, plot_cfg)
    if "json" in formats:
        summ = {"monitors": {}, "coords": "x-z (2D,已由 Lumerical 的 x-y 換回)" if d2 else "x-y-z"}
        for mon, res in data.items():
            e = {"type": res.get("_type", ""), "datasets": {}}
            for ds, d in res.items():
                if ds.startswith("_"):
                    continue
                e["datasets"][ds] = {k: list(np.shape(v)) for k, v in d.items()}
            T = res.get("T")
            if T is not None and "T" in T:
                o, wl = _wl_sorted(T)
                tt = np.real(np.asarray(T["T"])).ravel()[o]
                e["T_min"], e["T_max"] = float(np.min(tt)), float(np.max(tt))
                e["T_at_center"] = float(np.interp((wl[0] + wl[-1]) / 2, wl, tt))
            summ["monitors"][mon] = e
        if summary_extra:
            summ.update(summary_extra)
        p = os.path.join(out_dir, f"{base}_summary.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(summ, f, ensure_ascii=False, indent=1, default=lambda o: float(np.real(o)))
        files.append(p)
    return files


def _parse_wls(spec: str):
    spec = (spec or "center").strip().lower()
    if spec in ("", "center", "中心"):
        return ["center"]
    if spec in ("all", "全部"):
        return ["all"]
    out = []
    for t in re.split(r"[,\s;]+", spec):
        if not t:
            continue
        if t in ("center", "中心"):
            out.append("center")
            continue
        try:
            out.append(float(t))
        except ValueError:
            pass
    return out or ["center"]


def _pick(wl, req):
    idx = []
    for r in req:
        if r == "all":
            step = max(1, len(wl) // 12)
            idx += list(range(0, len(wl), step))
        elif r == "center":
            idx.append(int(np.argmin(np.abs(wl - (wl[0] + wl[-1]) / 2))))
        else:
            idx.append(int(np.argmin(np.abs(wl - r))))
    return sorted(set(idx))


def _axes_of(I2, ds):
    """找出非單點的空間軸。回傳 [(名稱, 座標陣列, 軸 index)]。"""
    ax = []
    for i, k in enumerate(("x", "y", "z")):
        c = np.real(np.asarray(ds.get(k, np.zeros(1)))).ravel()
        if I2.shape[i] > 1:
            ax.append((k, c, i))
    return ax


def _field_text(I2, ds, out_dir, fname, fm, scale, comp):
    ax = _axes_of(I2, ds)
    if len(ax) > 2:
        return None      # 3D 體積資料不輸出文字檔(太大),請用 npz / mat / h5
    sq = np.squeeze(I2)
    sep = "," if fm == "csv" else "\t"
    p = os.path.join(out_dir, fname)
    if len(ax) == 0:
        arr = np.array([[float(sq)]])
        hdr = f"|{comp}|^2"
    elif len(ax) == 1:
        arr = np.column_stack([ax[0][1] * scale, sq])
        hdr = sep.join([ax[0][0], f"|{comp}|^2"])
    else:
        (n1, c1, _), (n2, c2, _) = ax
        G1, G2 = np.meshgrid(c1 * scale, c2 * scale, indexing="ij")
        arr = np.column_stack([G1.ravel(), G2.ravel(), sq.ravel()])
        hdr = sep.join([n1, n2, f"|{comp}|^2"])
    np.savetxt(p, arr, delimiter=sep, header=hdr, comments="", fmt="%.6g")
    return p


def _figsize(c1, c2):
    w, h = float(np.ptp(c1)) or 1.0, float(np.ptp(c2)) or 1.0
    r = min(max(w / h, 0.35), 3.0)
    return (min(3.2 + 4.2 * r, 11), 4.8) if r >= 1 else (3.4 + 4.2 * r, 4.8 + 1.5 * (1 - r))


def _plots(data, plots, out_dir, base, unit, plot_cfg=None):
    plot_cfg = plot_cfg or {}
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    _cjk_font(plt)
    files = []
    scale = 1e9 if unit == "nm" else 1e6
    ul = "nm" if unit == "nm" else "µm"
    for mon, comp, wl, I2, ds in plots:
        ax = _axes_of(I2, ds)
        fig, a = plt.subplots(figsize=_figsize(ax[0][1], ax[1][1]) if len(ax) >= 2 else (6.4, 4.0), dpi=130)
        sq = np.squeeze(I2)
        if len(ax) == 2:
            (n1, c1, _), (n2, c2, _) = ax
            im = a.pcolormesh(c1 * scale, c2 * scale, sq.T, shading="auto", cmap="inferno")
            a.set_xlabel(f"{n1} ({ul})")
            a.set_ylabel(f"{n2} ({ul})")
            a.set_aspect("equal")
            fig.colorbar(im, ax=a, label=f"|{comp}|²")
        elif len(ax) == 1:
            a.plot(ax[0][1] * scale, sq)
            a.set_xlabel(f"{ax[0][0]} ({ul})")
            a.set_ylabel(f"|{comp}|²")
        elif len(ax) == 3:   # 體積:中間的 z 切面
            k = sq.shape[2] // 2
            c1, c2 = ax[0][1], ax[1][1]
            im = a.pcolormesh(c1 * scale, c2 * scale, sq[:, :, k].T, shading="auto", cmap="inferno")
            a.set_xlabel(f"x ({ul})")
            a.set_ylabel(f"y ({ul})")
            a.set_aspect("equal")
            fig.colorbar(im, ax=a, label=f"|{comp}|²(z 中間切面)")
        else:
            plt.close(fig)
            continue
        a.set_title(f"{mon}  |{comp}|²  λ = {wl:.1f} nm")
        fig.tight_layout()
        p = os.path.join(out_dir, f"{base}_{mon}_{comp}2_{wl:.1f}nm.png")
        fig.savefig(p, bbox_inches="tight")
        plt.close(fig)
        files.append(p)
    for mon, res in data.items():
        T = res.get("T")
        if T is not None and "T" in T and plot_cfg.get(mon, {}).get("spectrum", True):
            o, wl = _wl_sorted(T)
            if o is None:
                continue
            tt = np.real(np.asarray(T["T"])).ravel()[o]
            fig, a = plt.subplots(figsize=(6.4, 4.0), dpi=130)
            a.plot(wl, tt, lw=1.6)
            a.set_xlabel("波長 (nm)")
            a.set_ylabel("T(對光源功率正規化;負號 = 往負方向流)")
            a.set_title(f"{mon} 穿透率頻譜")
            a.grid(alpha=0.3)
            fig.tight_layout()
            p = os.path.join(out_dir, f"{base}_{mon}_spectrum.png")
            fig.savefig(p, bbox_inches="tight")
            plt.close(fig)
            files.append(p)
        idx = res.get("index")
        if idx is not None:
            key = next((k for k in ("index_x", "index_y", "index_z") if k in idx), None)
            if key:
                A = np.real(np.asarray(idx[key]))
                A = A[..., 0] if A.ndim == 4 else A
                ax = [(k, np.real(np.asarray(idx.get(k, np.zeros(1)))).ravel(), i)
                      for i, k in enumerate(("x", "y", "z")) if A.shape[i] > 1]
                sq = np.squeeze(A)
                if len(ax) == 2 and sq.ndim == 2:
                    fig, a = plt.subplots(figsize=_figsize(ax[0][1], ax[1][1]), dpi=130)
                    im = a.pcolormesh(ax[0][1] * scale, ax[1][1] * scale, sq.T, shading="auto", cmap="viridis")
                    a.set_xlabel(f"{ax[0][0]} ({ul})")
                    a.set_ylabel(f"{ax[1][0]} ({ul})")
                    a.set_aspect("equal")
                    fig.colorbar(im, ax=a, label="Re(n)")
                    a.set_title(f"{mon} 折射率分布(檢查結構)")
                    fig.tight_layout()
                    p = os.path.join(out_dir, f"{base}_{mon}_index.png")
                    fig.savefig(p, bbox_inches="tight")
                    plt.close(fig)
                    files.append(p)
    return files


def _cjk_font(plt):
    from matplotlib import font_manager
    have = {f.name for f in font_manager.fontManager.ttflist}
    for name in ("Microsoft JhengHei", "Microsoft YaHei", "PingFang TC", "Noto Sans CJK TC", "SimHei"):
        if name in have:
            plt.rcParams["font.sans-serif"] = [name, "DejaVu Sans"]
            plt.rcParams["axes.unicode_minus"] = False
            return
