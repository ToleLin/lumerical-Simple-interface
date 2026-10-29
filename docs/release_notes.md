## LumEasy — Lumerical FDTD 一站式建模介面

不用學 Lumerical 的介面:直接輸入尺寸(或用滑鼠在格子上畫),就能自動建好 FDTD 模型、放好監視器、跑模擬、輸出資料與場圖。
只透過 Lumerical 官方的 Python API 溝通,不碰授權、不碰授權伺服器。

### 下載與執行

- 下載下面的 **`LumEasy.exe`**,雙擊執行,不用裝 Python。第一次開啟約 10–20 秒(解壓)。
- Windows 如果跳出「Windows 已保護您的電腦」(程式沒有數位簽章):按「其他資訊」→「仍要執行」。
- 檔案核對:`LumEasy.exe.sha256`(PowerShell:`Get-FileHash LumEasy.exe`)。

### 需求

- Windows 10 / 11(64 位元)
- 已安裝 Ansys Lumerical FDTD(含 Python API)與有效授權;已在 2020 R2 測試建模、執行、輸出全流程

### 功能

- 直譯式建模:長方體、圓柱、橢圓柱、圓環、球、梯形台、正多邊形、自訂多邊形;從原點起疊、疊在物件頂面上、陣列複製
- 草圖建模:格子上畫矩形 / 圓 / 多邊形 → 擠出或挖孔
- CAD 匯入:STL(一鍵切換單位)、GDSII、DXF
- 材料:固定 n,k / ε、匯入 n,k 或 ε 頻譜檔(自動換算)、複製內建材料調擬合
- 監視器一鍵放置、勾選電場 / 磁場分量;平面波、高斯光、模態、偶極子、TFSF;2D / 3D
- 一鍵輸出 npz / mat / h5 / csv / txt / png / json,自動畫場圖、頻譜、折射率分布
- 每個欄位的滑鼠提示附對應的 Lumerical 設定;簡易 / 進階模式
- 自動避坑:中文路徑、Lumerical 卡住自動重開、發散偵測、記憶體估計、建模後讀回幾何核對

這個 EXE 由 GitHub Actions 在雲端打包,打包後跑過自我測試(`LumEasy.exe --selftest`)。
在有 Lumerical 的電腦上可以跑完整測試:`LumEasy.exe --selftest run`(結果在 `%TEMP%\lumeasy_selftest.txt`)。
