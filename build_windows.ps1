$ErrorActionPreference = "Stop"

# 前置：确保 Tesseract 引擎已就绪（Windows 版内置 OCR，用户免安装）
if (-not (Test-Path "vendor/tesseract/tesseract.exe")) {
    Write-Host "未找到 vendor/tesseract。正在运行 scripts/fetch_tesseract_win.sh 获取 Tesseract 引擎..." -ForegroundColor Yellow
    if ($IsWindows) {
        # Windows 上用 Git Bash 或 WSL 的 sh；若都没有则提示手动获取
        if (Get-Command bash -ErrorAction SilentlyContinue) {
            bash scripts/fetch_tesseract_win.sh
        } else {
            Write-Error "需要 Tesseract 引擎。请在能运行 bash 的环境下先执行 scripts/fetch_tesseract_win.sh。"
        }
    } else {
        sh scripts/fetch_tesseract_win.sh
    }
}

# Windows 版必须用 Python 3.12（winsdk 只提供到 cp312 的 wheel）
$PythonExe = if (Test-Path "C:\Python312\python.exe") { "C:\Python312\python.exe" } else { "python" }
Write-Host "使用 Python: $PythonExe ($(& $PythonExe --version))" -ForegroundColor Cyan

& $PythonExe -m pip install --upgrade pip
& $PythonExe -m pip install ".[windows]" pyinstaller

Remove-Item -Recurse -Force build, dist, assets/CoursePilot.ico -ErrorAction SilentlyContinue
& $PythonExe -c "from PIL import Image; Image.open('assets/coursepilot-icon.png').save('assets/CoursePilot.ico', format='ICO', sizes=[(16,16),(32,32),(48,48),(256,256)])"

# winsdk hidden imports（Windows 自带 OCR 依赖）
$WinSDKHiddenImports = @(
    "winsdk.windows.media.ocr",
    "winsdk.windows.globalization",
    "winsdk.windows.graphics.imaging",
    "winsdk.windows.storage.streams",
    "winsdk.windows.foundation"
) | ForEach-Object { "--hidden-import", $_ }

# === 1) 目录版（onedir）：启动快，zip 分发 ===
# 注：用 --add-data 而非 --add-binary，避免 PyInstaller 对 tesseract.exe
#     做 PE 依赖分析而报缺 DLL；整个目录当作数据拷进 _internal/tesseract/
& $PythonExe -m PyInstaller --noconfirm --clean --windowed --name CoursePilot `
    --icon assets/CoursePilot.ico --paths src `
    @WinSDKHiddenImports `
    --add-data "vendor/tesseract;tesseract" `
    src/coursepilot_launcher.py

# 目录版 zip + sha256
Compress-Archive -Path dist/CoursePilot -DestinationPath dist/CoursePilot-Windows-x64.zip -Force
(Get-FileHash dist/CoursePilot-Windows-x64.zip -Algorithm SHA256).Hash.ToLower() + "  CoursePilot-Windows-x64.zip" | Set-Content dist/CoursePilot-Windows-x64.zip.sha256

# === 2) 单文件版（onefile）：免解压，双击即用 ===
# 用独立名称避免与 onedir 产物冲突
& $PythonExe -m PyInstaller --noconfirm --clean --windowed --onefile --name CoursePilot `
    --icon assets/CoursePilot.ico --paths src `
    @WinSDKHiddenImports `
    --add-data "vendor/tesseract;tesseract" `
    src/coursepilot_launcher.py

# 单文件 exe（免解压版）
Copy-Item dist/CoursePilot.exe dist/CoursePilot-Windows-x64.exe -Force
(Get-FileHash dist/CoursePilot-Windows-x64.exe -Algorithm SHA256).Hash.ToLower() + "  CoursePilot-Windows-x64.exe" | Set-Content dist/CoursePilot-Windows-x64.exe.sha256

Write-Host "已生成：" -ForegroundColor Green
Get-ChildItem dist | ForEach-Object { Write-Host ("{0}  {1:N1} MB" -f $_.Name, ($_.Length / 1MB)) }
