#!/bin/sh
set -eu

cd "$(dirname "$0")"

if [ ! -x ".venv/bin/pyinstaller" ]; then
    echo "请先运行：.venv/bin/pip install -r requirements-dev.txt"
    exit 1
fi

rm -rf assets/CoursePilot.iconset
mkdir -p assets/CoursePilot.iconset
for size in 16 32 128 256 512; do
    sips -z "$size" "$size" assets/coursepilot-icon.png \
        --out "assets/CoursePilot.iconset/icon_${size}x${size}.png" >/dev/null
    double=$((size * 2))
    sips -z "$double" "$double" assets/coursepilot-icon.png \
        --out "assets/CoursePilot.iconset/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns assets/CoursePilot.iconset -o assets/CoursePilot.icns

rm -rf build dist
.venv/bin/pyinstaller \
    --noconfirm \
    --clean \
    --windowed \
    --name CoursePilot \
    --icon assets/CoursePilot.icns \
    --paths src \
    --hidden-import AppKit \
    --hidden-import ApplicationServices \
    --hidden-import CoreMedia \
    --hidden-import Foundation \
    --hidden-import Quartz \
    --hidden-import ScreenCaptureKit \
    --hidden-import Vision \
    src/coursepilot_launcher.py

ditto -c -k --sequesterRsrc --keepParent \
    dist/CoursePilot.app dist/CoursePilot-macOS-arm64.zip
shasum -a 256 dist/CoursePilot-macOS-arm64.zip > dist/CoursePilot-macOS-arm64.zip.sha256
echo "已生成：dist/CoursePilot-macOS-arm64.zip"
