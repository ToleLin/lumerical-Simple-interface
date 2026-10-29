"""程式進入點。

    LumEasy.exe                 開啟介面
    LumEasy.exe --worker job    (內部用)在獨立行程裡和 Lumerical 溝通
    LumEasy.exe --selftest      不開視窗自我測試(不需要 Lumerical),結果寫到 %TEMP%/lumeasy_selftest.txt
"""
import sys


def main():
    # 繁中 Windows 的主控台是 cp950,印到不認得的字元(例如 ⇄、µ)會整個當掉 → 一律替換掉
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except Exception:  # noqa: BLE001
            pass
    if len(sys.argv) >= 3 and sys.argv[1] == "--worker":
        from lumeasy.worker import main as worker_main
        sys.exit(worker_main(sys.argv[2]))
    if len(sys.argv) >= 2 and sys.argv[1] == "--selftest":
        from lumeasy.selftest import main as st_main
        sys.exit(st_main())
    from lumeasy.gui.app import main as gui_main
    sys.exit(gui_main())


if __name__ == "__main__":
    main()
