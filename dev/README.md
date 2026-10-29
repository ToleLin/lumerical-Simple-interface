# dev/ 開發用腳本

| 檔案 | 用途 |
|---|---|
| `gui_smoke.py` | 不開視窗跑一遍介面、每頁截圖到 `dev/shots/`(不需要 Lumerical) |
| `gui_run_test.py` | 從介面按「建模並執行」,存放資料夾故意用中文路徑(需要 Lumerical) |
| `run_job.py` | 直接把範例丟給 worker:`python dev/run_job.py pillar build_run` |
| `dev_kitchen.py` | 所有形狀、光源、監視器、材料種類、CAD 匯入放在同一個模型(只建模測試) |
| `probe_v202.py` | 逐一測試 Lumerical 腳本指令與屬性名稱在這個版本能不能用 |
| `probe_theta.py` | 實測入射角 θ 的正負號(2D / 3D × 往上 / 往下) |
| `mk_testcad.py` | 產生測試用的 `test.gds`、`test.stl` |
