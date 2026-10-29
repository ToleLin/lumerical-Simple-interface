import sys, pathlib, numpy as np
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from lumeasy import lumenv
lumapi = lumenv.load_lumapi(lumenv.resolve_root())
out = pathlib.Path(__file__).resolve().parent / "out"
def case(dim, direction, theta):
    fdtd = lumapi.FDTD(hide=True)
    try:
        fdtd.addfdtd(); fdtd.set("dimension", dim); fdtd.set("x span", 0.6e-6); fdtd.set("y span", 0.6e-6 if dim=="3D" else 1.2e-6)
        if dim == "3D": fdtd.set("z span", 1.2e-6)
        fdtd.set("mesh accuracy", 1); fdtd.set("simulation time", 150e-15)
        fdtd.set("x min bc", "Bloch")
        if dim == "3D": fdtd.set("y min bc", "Bloch")
        fdtd.set("set based on source angle", 1)
        fdtd.addplane(); ax = "z-axis" if dim == "3D" else "y-axis"; fdtd.set("injection axis", ax); fdtd.set("direction", direction)
        fdtd.set("x span", 1.2e-6)
        if dim == "3D": fdtd.set("y span", 1.2e-6); fdtd.set("z", 0.4e-6 if direction=="Backward" else -0.4e-6)
        else: fdtd.set("y", 0.4e-6 if direction=="Backward" else -0.4e-6)
        fdtd.set("angle theta", theta); fdtd.set("wavelength start", 600e-9); fdtd.set("wavelength stop", 600e-9)
        fdtd.addprofile(); fdtd.set("name", "mon")
        if dim == "3D": fdtd.set("monitor type", "2D Z-normal"); fdtd.set("x span", 0.6e-6); fdtd.set("y span", 0.6e-6)
        else: fdtd.set("monitor type", "Linear X"); fdtd.set("x span", 0.6e-6)
        fdtd.save(str(out / f"theta_{dim}_{direction}.fsp").replace("\\","/")); fdtd.run()
        E = fdtd.getresult("mon", "E")["E"]; x = fdtd.getresult("mon", "E")["x"].ravel()
        row = E[:, 0, 0, 0, :]; c = int(np.argmax(np.sum(abs(row)**2, axis=0))); r = row[:, c]
        k = np.polyfit(x, np.unwrap(np.angle(r)), 1)[0]; k0 = 2*np.pi/600e-9
        print(f"{dim} {direction:8s} theta={theta:+.0f}: kx/k0 = {k/k0:+.3f}", flush=True)
    finally:
        fdtd.close()
for dim in ("2D", "3D"):
    for d in ("Backward", "Forward"):
        case(dim, d, 10)
