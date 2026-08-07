#!/bin/sh
# 获取 Windows 版 Tesseract OCR 引擎（含中文 chi_sim 语言包），输出到 vendor/tesseract/。
#
# 背景：Windows 版 CoursePilot 用 pytesseract 做 OCR，需要 tesseract 引擎。
# 为了让用户免安装，我们把 tesseract 运行时直接打包进安装包。
# 本脚本把官方安装器解包，裁剪出运行时所需文件，并补上下载中文语言包。
#
# 依赖：
#   - curl
#   - 新版 7-Zip（brew install sevenzip；旧版 p7zip 解不开新版 NSIS 安装器）
#   - GitHub 访问慢时，使用 gh-proxy.com 加速（本机已验证可达）
#
# 用法：./scripts/fetch_tesseract_win.sh

set -eu

TESSERACT_VERSION="5.5.0.20241111"
SETUP_URL="https://gh-proxy.com/https://github.com/tesseract-ocr/tesseract/releases/download/5.5.0/tesseract-ocr-w64-setup-${TESSERACT_VERSION}.exe"
CHI_SIM_URL="https://gh-proxy.com/https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/chi_sim.traineddata"
ENG_URL="https://gh-proxy.com/https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/eng.traineddata"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

echo "==> 下载 Tesseract ${TESSERACT_VERSION} 安装器"
curl -sL --retry 5 --retry-delay 2 -o "$TMP_DIR/tesseract-setup.exe" "$SETUP_URL"

echo "==> 解包安装器（需新版 7-Zip）"
if command -v 7z >/dev/null 2>&1; then
    SEVENZIP=7z
else
    SEVENZIP=$(command -v 7za || true)
fi
if [ -z "${SEVENZIP:-}" ]; then
    echo "错误：未找到 7z / 7za。请先安装新版 7-Zip：brew install sevenzip" >&2
    exit 1
fi
"$SEVENZIP" x -y -o"$TMP_DIR/extract" "$TMP_DIR/tesseract-setup.exe" >/dev/null

echo "==> 下载 chi_sim 中文语言包（tessdata_fast 版，速度快、体积小）"
curl -sL --retry 5 --retry-delay 2 -o "$TMP_DIR/extract/tessdata/chi_sim.traineddata" "$CHI_SIM_URL"
echo "==> 下载 eng 英文语言包"
curl -sL --retry 5 --retry-delay 2 -o "$TMP_DIR/extract/tessdata/eng.traineddata" "$ENG_URL"

echo "==> 裁剪并输出到 vendor/tesseract/"
VENDOR_DIR="$ROOT_DIR/vendor/tesseract"
rm -rf "$VENDOR_DIR"
mkdir -p "$VENDOR_DIR"

# tesseract.exe + 全部 DLL（libtesseract/libleptonica 及其可选依赖，删了会崩）
cp "$TMP_DIR/extract/tesseract.exe" "$VENDOR_DIR/"
cp "$TMP_DIR/extract/"*.dll "$VENDOR_DIR/"

# tessdata：chi_sim 语言包 + configs/tessconfigs（tesseract 运行时需要）
cp -R "$TMP_DIR/extract/tessdata" "$VENDOR_DIR/"

# 剔除训练工具、文档、jar 等非运行时文件（保留 tesseract.exe 和 DLL）
find "$VENDOR_DIR" -maxdepth 1 -name '*.exe' ! -name 'tesseract.exe' -delete
rm -rf "$VENDOR_DIR"/doc

echo "==> 完成。vendor/tesseract 大小："
du -sh "$VENDOR_DIR"
echo "    chi_sim 语言包："
ls -la "$VENDOR_DIR/tessdata/chi_sim.traineddata"
