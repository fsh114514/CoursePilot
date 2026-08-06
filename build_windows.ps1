$ErrorActionPreference = "Stop"

python -m pip install --upgrade pip
python -m pip install ".[windows]" pyinstaller

Remove-Item -Recurse -Force build, dist, assets/CoursePilot.ico -ErrorAction SilentlyContinue
python -c "from PIL import Image; Image.open('assets/coursepilot-icon.png').save('assets/CoursePilot.ico', format='ICO', sizes=[(16,16),(32,32),(48,48),(256,256)])"
python -m PyInstaller --noconfirm --clean --windowed --name CoursePilot --icon assets/CoursePilot.ico --paths src src/coursepilot_launcher.py
Compress-Archive -Path dist/CoursePilot -DestinationPath dist/CoursePilot-Windows-x64.zip -Force
(Get-FileHash dist/CoursePilot-Windows-x64.zip -Algorithm SHA256).Hash.ToLower() + "  CoursePilot-Windows-x64.zip" | Set-Content dist/CoursePilot-Windows-x64.zip.sha256
