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

# 屏幕录制权限：重新签名带 entitlements（adhoc 签名 + 权限声明）
codesign --force --deep --sign - --entitlements entitlements.mac.plist \
    dist/CoursePilot.app 2>/dev/null || echo "注意：重新签名失败，权限可能受影响"

ditto -c -k --sequesterRsrc --keepParent \
    dist/CoursePilot.app dist/CoursePilot-macOS-arm64.zip
shasum -a 256 dist/CoursePilot-macOS-arm64.zip > dist/CoursePilot-macOS-arm64.zip.sha256

# 免解压版：dmg 磁盘镜像（标准"拖到 Applications"安装界面）
# 方案：先用 osascript 在临时目录配置 Finder 图标布局生成 .DS_Store，
#       再放进 staging 一起打包成 dmg。
rm -rf dist/dmg-staging
mkdir -p dist/dmg-staging
cp -R dist/CoursePilot.app dist/dmg-staging/
ln -s /Applications dist/dmg-staging/Applications

# 用 AppleScript 生成含"拖到 Applications"布局的 .DS_Store
# 原理：把 staging 目录用 Finder 以图标视图打开，设置图标位置后，
#       Finder 会写出 .DS_Store；再把该 .DS_Store 放进最终 dmg。
cat > /tmp/coursepilot_layout.scpt <<'APPLESCRIPT'
tell application "Finder"
    set targetFolder to POSIX file "/tmp/coursepilot-dmg-staging" as alias
    open targetFolder
    delay 1
    tell window of targetFolder
        set current view to icon view
        set toolbar visible to false
        set statusbar visible to false
        set bounds to {0, 0, 640, 480}
        set icon view options
        set icon size of icon view options to 128
    end tell
    delay 1
    close window of targetFolder
    delay 0.5
end tell
APPLESCRIPT

# 用 staging 的副本配置布局（避免污染最终打包）
rm -rf /tmp/coursepilot-dmg-staging
cp -R dist/dmg-staging /tmp/coursepilot-dmg-staging
osascript /tmp/coursepilot_layout.scpt 2>/dev/null || true

# 取出配置好的 .DS_Store（含图标布局）
if [ -f /tmp/coursepilot-dmg-staging/.DS_Store ]; then
    cp /tmp/coursepilot-dmg-staging/.DS_Store dist/dmg-staging/.DS_Store
fi
rm -rf /tmp/coursepilot-dmg-staging

# 创建带安装界面的 dmg
hdiutil create \
    -volname CoursePilot \
    -srcfolder dist/dmg-staging \
    -ov -format UDZO \
    dist/CoursePilot-macOS-arm64.dmg
rm -rf dist/dmg-staging
shasum -a 256 dist/CoursePilot-macOS-arm64.dmg > dist/CoursePilot-macOS-arm64.dmg.sha256

echo "已生成："
ls -lh dist/CoursePilot-macOS-arm64.*
