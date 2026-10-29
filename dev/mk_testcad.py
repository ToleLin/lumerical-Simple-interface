import gdstk, numpy as np, struct, pathlib
here = pathlib.Path(__file__).parent
lib = gdstk.Library(unit=1e-6, precision=1e-9)
c = lib.new_cell("TOP")
c.add(gdstk.rectangle((-0.5, -0.5), (0.5, 0.5), layer=1))
c.add(gdstk.regular_polygon((1.5, 0), 0.4, 6, layer=2))
lib.write_gds(here / "test.gds")
# binary STL: a tetrahedron (units um)
v = np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1]], float)
faces = [(0,2,1),(0,1,3),(0,3,2),(1,2,3)]
with open(here / "test.stl", "wb") as f:
    f.write(b"\0"*80); f.write(struct.pack("<I", len(faces)))
    for a,b,cc in faces:
        n = np.cross(v[b]-v[a], v[cc]-v[a]); n = n/np.linalg.norm(n)
        f.write(struct.pack("<12fH", *n, *v[a], *v[b], *v[cc], 0))
print("ok")
