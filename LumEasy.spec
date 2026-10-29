# PyInstaller 設定:打包成單一 LumEasy.exe(不用裝 Python)。
# 用法:build_exe.bat(或 .venv\Scripts\pyinstaller LumEasy.spec --noconfirm)
# Lumerical 的 lumapi 不打包進來:執行時從使用者電腦上的 Lumerical 安裝資料夾載入。
hidden = ["matplotlib.backends.backend_qtagg", "matplotlib.backends.backend_agg", "scipy.io", "scipy.io.matlab",
          "h5py", "gdstk", "ezdxf"]

a = Analysis(
    ["lumeasy/__main__.py"],
    pathex=["."],
    datas=[("docs/使用說明.md", "docs"), ("docs/疑難排解.md", "docs"), ("assets/icon.ico", "assets")],
    hiddenimports=hidden,
    excludes=["tkinter", "PyQt5", "PyQt6", "IPython", "pandas", "pytest", "PySide6.QtWebEngineCore",
              "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore", "PySide6.QtQuick", "PySide6.QtQml",
              "PySide6.QtMultimedia", "PySide6.QtPdf", "PySide6.QtCharts", "PySide6.QtDataVisualization"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="LumEasy",
    icon="assets/icon.ico",
    console=False,
    upx=False,
    runtime_tmpdir=None,
)
