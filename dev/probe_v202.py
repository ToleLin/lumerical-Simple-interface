"""Probe which LSF commands / property names work in this Lumerical version.
Run with the venv python. Prints one line per block: OK / ERR <message>."""
import json, sys, time, pathlib
here = pathlib.Path(__file__).parent.resolve()
sys.path.insert(0, str(here.parent))
from lumeasy import lumenv
lumapi = lumenv.load_lumapi(lumenv.resolve_root())

gds = str(here / "test.gds").replace("\\", "/")
stl = str(here / "test.stl").replace("\\", "/")
out = str(here / "probe_out.fsp").replace("\\", "/")

blocks = {
 "fdtd": 'addfdtd; set("name","FDTD"); set("dimension","3D"); set("x",0); set("x span",3e-6); set("y",0); set("y span",3e-6); set("z",0); set("z span",3e-6); set("simulation time",500e-15); set("mesh accuracy",2); set("x min bc","PML"); set("x max bc","PML"); set("y min bc","Periodic"); set("z min bc","PML"); set("index",1.0); set("auto shutoff min",1e-5);',
 "fdtd_pml_layers": 'select("FDTD"); set("pml layers",12);',
 "fdtd_pml_profile": 'select("FDTD"); set("pml profile",2);',
 "fdtd_symm": 'select("FDTD"); set("allow symmetry on all boundaries",1);',
 "fdtd_meshtype": 'select("FDTD"); set("mesh type","auto non-uniform");',
 "fdtd_minstep": 'select("FDTD"); set("min mesh step",0.25e-9);',
 "fdtd_bloch": 'select("FDTD"); set("y min bc","Bloch"); set("set based on source angle",1);',
 "mat_nk": 'm1 = addmaterial("(n,k) Material"); setmaterial(m1,"name","MyNK"); setmaterial("MyNK","Refractive Index",2.4); setmaterial("MyNK","Imaginary Refractive Index",0.01);',
 "mat_color": 'setmaterial("MyNK","color",[1,0.2,0.2,1]);',
 "mat_sampled": 'm2 = addmaterial("Sampled 3D data"); setmaterial(m2,"name","MySamp"); ff=[4e14;5e14;6e14;7e14]; ee=[2.1+0.01i;2.12+0.012i;2.15+0.015i;2.2+0.02i]; setmaterial("MySamp","sampled data",[ff,ee]);',
 "mat_fit": 'setmaterial("MySamp","tolerance",0.001); setmaterial("MySamp","max coefficients",12);',
 "mat_sampled_name_with_space": 'm3 = addmaterial("Sampled 3D data"); setmaterial(m3,"name","a-Si (mine)"); setmaterial("a-Si (mine)","sampled data",[ff,ee]);',
 "mat_getindex": 'nn = getindex("MySamp", 5e14);',
 "mat_list": 'matlist = getmaterial();',
 "rect": 'addrect; set("name","box1"); set("x",0); set("x span",1e-6); set("y",0); set("y span",1e-6); set("z",0.1e-6); set("z span",0.2e-6); set("material","MyNK");',
 "rect_rot": 'select("box1"); set("first axis","z"); set("rotation 1",30);',
 "rect_meshorder": 'select("box1"); set("override mesh order from material database",1); set("mesh order",1);',
 "rect_alpha": 'select("box1"); set("alpha",0.5);',
 "circle": 'addcircle; set("name","cyl"); set("x",0); set("y",0); set("z",0.3e-6); set("z span",0.2e-6); set("radius",0.2e-6); set("material","SiO2 (Glass) - Palik");',
 "ellipse": 'addcircle; set("name","ell"); set("make ellipsoid",1); set("radius",0.2e-6); set("radius 2",0.1e-6); set("z span",0.2e-6); set("material","MyNK");',
 "ring": 'addring; set("name","ring1"); set("outer radius",0.4e-6); set("inner radius",0.2e-6); set("z span",0.1e-6); set("theta start",0); set("theta stop",360); set("material","MyNK");',
 "sphere": 'addsphere; set("name","sph"); set("radius",0.2e-6); set("material","MyNK");',
 "poly": 'addpoly; set("name","poly1"); set("vertices",[0,0;1e-6,0;0.5e-6,0.8e-6]); set("z",0); set("z span",0.1e-6); set("material","MyNK");',
 "pyramid": 'addpyramid; set("name","pyr"); set("x span bottom",1e-6); set("y span bottom",1e-6); set("x span top",0.5e-6); set("y span top",0.5e-6); set("z span",0.3e-6); set("material","MyNK");',
 "etch": 'addrect; set("name","hole"); set("x span",0.2e-6); set("y span",0.2e-6); set("z span",0.2e-6); set("material","etch");',
 "gds": 'gdsimport("' + gds + '","TOP",1,"MyNK",0,0.2e-6);',
 "gds_layer2": 'gdsimport("' + gds + '","TOP",2,"MySamp",0.2e-6,0.4e-6);',
 "stl": 'stlimport("' + stl + '");',
 "stl_units": 'stlimport("' + stl + '","microns");',
 "planarsolid": 'addplanarsolid; set("name","ps"); vtx=[0,1e-6,0,0;0,0,1e-6,0;0,0,0,1e-6]; fct=cell(4); fct{1}=cell(1); fct{1}{1}=[1,3,2]; fct{2}=cell(1); fct{2}{1}=[1,2,4]; fct{3}=cell(1); fct{3}{1}=[1,4,3]; fct{4}=cell(1); fct{4}{1}=[2,3,4]; set("vertices",vtx); set("facets",fct); set("material","MyNK");',
 "src_plane": 'addplane; set("name","pw"); set("injection axis","z-axis"); set("direction","Backward"); set("x",0); set("x span",3e-6); set("y",0); set("y span",3e-6); set("z",1e-6); set("wavelength start",400e-9); set("wavelength stop",700e-9); set("polarization angle",0); set("angle theta",10); set("angle phi",0);',
 "src_plane_type": 'select("pw"); set("plane wave type","Bloch/periodic");',
 "src_plane_bfast": 'select("pw"); set("plane wave type","BFAST");',
 "src_plane_diff": 'select("pw"); set("plane wave type","Diffracting");',
 "src_gauss": 'addgaussian; set("name","gs"); set("injection axis","z-axis"); set("direction","Backward"); set("z",1e-6); set("x span",3e-6); set("y span",3e-6); set("waist radius w0",0.8e-6); set("distance from waist",0); set("wavelength start",500e-9); set("wavelength stop",600e-9);',
 "src_gauss_na": 'select("gs"); set("use scalar approximation",0); set("source shape","Gaussian");',
 "src_dipole": 'adddipole; set("name","dp"); set("dipole type","Electric dipole"); set("theta",90); set("phi",0); set("wavelength start",500e-9); set("wavelength stop",600e-9);',
 "src_mode": 'addmode; set("name","md"); set("injection axis","x-axis"); set("direction","Forward"); set("x",-1e-6); set("y span",2e-6); set("z span",2e-6); set("mode selection","fundamental TE mode");',
 "src_mode_num": 'select("md"); set("mode selection","user select"); set("selected mode number",1);',
 "src_tfsf": 'addtfsf; set("name","tf"); set("injection axis","z-axis"); set("x span",1e-6); set("y span",1e-6); set("z span",1e-6);',
 "global": 'setglobalsource("wavelength start",400e-9); setglobalsource("wavelength stop",700e-9); setglobalmonitor("frequency points",51);',
 "mon_power": 'addpower; set("name","top"); set("monitor type","2D Z-normal"); set("x",0); set("x span",3e-6); set("y",0); set("y span",3e-6); set("z",1.2e-6); set("override global monitor settings",1); set("frequency points",31); set("output Ex",1); set("output Hx",0); set("output Px",1); set("output power",1);',
 "mon_power_wl": 'select("top"); set("use source limits",0); set("minimum wavelength",450e-9); set("maximum wavelength",650e-9);',
 "mon_power_xn": 'addpower; set("name","left"); set("monitor type","2D X-normal"); set("x",-1.2e-6); set("y span",3e-6); set("z span",3e-6);',
 "mon_power_lin": 'addpower; set("name","lin"); set("monitor type","Linear X"); set("x span",3e-6);',
 "mon_power_pt": 'addpower; set("name","pt"); set("monitor type","Point");',
 "mon_power_3d": 'addpower; set("name","vol"); set("monitor type","3D"); set("x span",1e-6); set("y span",1e-6); set("z span",1e-6);',
 "mon_profile": 'addprofile; set("name","xz"); set("monitor type","2D Y-normal"); set("x span",3e-6); set("z span",3e-6); set("output Hy",1);',
 "mon_time": 'addtime; set("name","t1"); set("monitor type","point"); set("x",0.1e-6);',
 "mon_time_2": 'select("t1"); set("output Ex",1); set("output Hz",0);',
 "mon_index": 'addindex; set("name","idx"); set("monitor type","2D Y-normal"); set("x span",3e-6); set("z span",3e-6);',
 "mon_movie": 'addmovie; set("name","mov"); set("monitor type","2D Y-normal"); set("x span",3e-6); set("z span",3e-6); set("component","Ey");',
 "mon_down": 'select("top"); set("down sample X",2); set("down sample Y",2);',
 "mon_apod": 'select("top"); set("apodization","End"); set("apodization center",300e-15); set("apodization time width",60e-15);',
 "mesh": 'addmesh; set("name","mesh1"); set("based on a structure",1); set("structure","box1"); set("override x mesh",1); set("dx",10e-9); set("override y mesh",1); set("dy",10e-9); set("override z mesh",1); set("dz",5e-9);',
 "group": 'addstructuregroup; set("name","grp");',
 "addtogroup": 'select("box1"); addtogroup("grp");',
 "resource": 'nres = getresource("FDTD",1,"processes");',
 "save": 'save("' + out + '");',
}

t0 = time.time()
fdtd = lumapi.FDTD(hide=True)
print(f"session open {time.time()-t0:.1f}s", flush=True)
res = {}
for k, code in blocks.items():
    try:
        fdtd.eval(code)
        res[k] = "OK"
    except Exception as e:
        res[k] = "ERR " + str(e).replace("\n", " ")[:200]
    print(f"{k:28s} {res[k]}", flush=True)
for v in ("matlist", "nn", "nres"):
    try:
        val = fdtd.getv(v)
        s = str(val)
        print(v, "=", s[:3000].replace("\n", " | "))
    except Exception as e:
        print(v, "ERR", e)
# read back some props
for obj, prop in [("box1","z"),("pyr","z span"),("FDTD","index"),("pw","angle theta"),("top","frequency points"),("MyNK","Refractive Index")]:
    try:
        if obj in ("MyNK",):
            print(obj, prop, fdtd.getmaterial(obj, prop))
        else:
            print(obj, prop, fdtd.getnamed(obj, prop))
    except Exception as e:
        print(obj, prop, "ERR", e)
try:
    fdtd.eval('selectall; objs = "";')
    fdtd.eval('nobj = getnumber;')
    print("nobj", fdtd.getv("nobj"))
except Exception as e:
    print("count ERR", e)
fdtd.close()
json.dump(res, open(here / "probe_result.json", "w"), indent=1)
