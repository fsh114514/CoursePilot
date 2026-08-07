# 网课视频播放助手 · CoursePilot

<p><img src="assets/coursepilot-icon.png" alt="CoursePilot 图标" width="112"></p>

> 视频看到一半，弹出“我还在看”又要手动点？
>
> CoursePilot 会在你选定的课程窗口中，用本地 OCR 识别白名单提示，并点击对应的继续观看按钮。选窗口、点启动，减少重复确认对学习过程的打断。

CoursePilot 是一个面向 macOS 和 Windows 的本地屏幕识别工具。它不装浏览器插件、不注入网页，也不上传屏幕内容；只处理用户明确选择的窗口和提示词。

它不依赖油猴脚本、浏览器插件或特定网站适配器，屏幕内容只在本机处理，适合重复出现观看确认弹窗的课程播放场景。

> 当前状态：Windows 版已在 Windows 11 虚拟机完整验证（窗口选择、预览、OCR 识别、自动点击均可用）；macOS 打包版因屏幕录制权限需 Apple 开发者证书，暂以源码运行方式提供。

## 功能特点

- 本地 AI/OCR 识别屏幕中的继续观看提示。
- 支持 Chrome、哔哩哔哩及其他可捕获的普通窗口。
- 只识别白名单提示词，不处理提交、交卷、支付、购买、删除等操作。
- 支持用户添加自定义按钮文字，并在设置页面显示内置提示词。
- 不上传屏幕内容，不注入网页，不修改网页代码。
- macOS 使用 Apple Vision 和 ScreenCaptureKit 本地处理。
- Windows 使用原生窗口列表、截图和鼠标输入控制；OCR 依赖本机 Tesseract。

## 搜索关键词

网课辅助、刷课辅助、课程播放自动化、自动处理继续观看、AI 屏幕识别、本地 OCR、自动点击提示、视频播放助手、macOS、Windows、CoursePilot。

## macOS 使用教程

> **注意**：macOS 打包版（.app/dmg）的屏幕录制权限依赖 Apple 开发者证书。未签名打包版权限可能不稳定。**推荐用源码运行方式**（终端有权限，稳定可用）。

### 1. 从源码运行（推荐，稳定）

```sh
git clone https://github.com/fsh114514/CoursePilot.git
cd CoursePilot
python3 -m venv .venv
.venv/bin/pip install -e '.[macos]'
./run_macos.command
```

也可以直接双击 `run_macos.command` 启动。

### 2. 打包版（可能需要手动授权）

在 GitHub Releases 下载 `CoursePilot-macOS-arm64.zip` 解压运行。若屏幕录制权限不稳定（重启后失效），请到“系统设置 → 隐私与安全性 → 屏幕录制”重新勾选，并完全退出后重启应用。

### 3. 第一次使用

1. 启动 CoursePilot，若提示权限，点“请求屏幕录制和辅助功能权限”，允许 CoursePilot。
2. 授权后**完全退出并重启**应用（macOS 权限在启动时生效）。
3. 把课程窗口放到当前台前调度组，并点击“刷新窗口”。
4. 从列表选择课程窗口，确认预览正确。
5. 点击“开始监控”。

### 4. 添加自定义提示词

只填写按钮上实际显示的文字，例如：

- 继续学习
- 继续播放课程
- 我还在学习

不要填写“提交”“交卷”“支付”“购买”“删除”等页面操作词。程序自带的提示词会在设置页面直接列出，不需要重复添加。

### macOS 注意事项

- 台前调度收起的窗口可能无法提供完整画面，请把目标窗口放回当前调度组。
- 某些受系统保护的窗口可能无法捕获。
- 程序只会点击白名单提示词附近的按钮，不会自动答题或修改学习记录。

## Windows 使用教程

Windows 版提供原生窗口列表、窗口预览、截图识别和鼠标点击功能。**OCR 使用 Windows 系统自带识别引擎（Windows.Media.Ocr），无需安装任何额外组件**；内置 Tesseract 作为兜底备用。

1. 在 Release 下载 `CoursePilot-Windows-x64.zip`（解压版）或 `CoursePilot-Windows-x64.exe`（单文件免解压版）。
2. 启动 `CoursePilot.exe`。
3. 点击“刷新窗口”，选择课程视频窗口并确认预览。
4. 确认提示词后点击“开始监控”。

> 架构说明：`CoursePilot-Windows-x64.zip` / `.exe` 是 x64 架构，可在 64 位 Windows 上原生运行，也能在 Windows on ARM（如骁龙本）的 x64 模拟层下运行。

## 本地测试页

运行下面的命令会启动本地测试页：

```sh
./run_test_site.command
```

页面会在几秒后显示“我还在看”，用于验证窗口预览、OCR 识别和按钮点击。测试页只在 `127.0.0.1` 本机运行。

## 当前 Release

每个版本提供 Windows 和 macOS 两套独立安装包（含解压版与免解压版）：

- Windows x64：
  - `CoursePilot-Windows-x64.zip`（解压版，含内置 Tesseract OCR）
  - `CoursePilot-Windows-x64.exe`（单文件免解压版）
  - 各自的 `.sha256` 校验文件
- macOS arm64：
  - `CoursePilot-macOS-arm64.zip`（解压版）
  - `CoursePilot-macOS-arm64.dmg`（磁盘镜像免解压版）
  - 各自的 `.sha256` 校验文件

## 构建 Release

前置：macOS 用 Apple Vision 识别，无需额外依赖；Windows 版用系统自带 OCR（需 Python 3.12，因 winsdk 只提供到 cp312 的 wheel），同时内置 Tesseract 引擎兜底，构建前由脚本自动获取 Tesseract。

```sh
# Windows（在 Windows 或能跑 bash 的环境执行）
./scripts/fetch_tesseract_win.sh   # 获取并裁剪 Tesseract 引擎到 vendor/tesseract/
./build_windows.ps1                # 产出 zip（解压版）和 exe（单文件版）+ sha256

# macOS（在 Apple Silicon Mac 上执行）
./build_macos.command              # 产出 zip 和 dmg + sha256
```

发布到 GitHub Releases：

```sh
gh release create v0.2.0 \
  dist/CoursePilot-Windows-x64.zip dist/CoursePilot-Windows-x64.zip.sha256 \
  dist/CoursePilot-Windows-x64.exe dist/CoursePilot-Windows-x64.exe.sha256 \
  dist/CoursePilot-macOS-arm64.zip dist/CoursePilot-macOS-arm64.zip.sha256 \
  dist/CoursePilot-macOS-arm64.dmg dist/CoursePilot-macOS-arm64.dmg.sha256 \
  --title "CoursePilot v0.2.0" --notes "..."`

## 隐私与安全

- 屏幕内容默认只在本机处理。
- 不要求登录、不上传截图、不收集课程账号信息。
- 只允许用户配置继续观看类白名单词。
- 不提供隐藏自动化行为、绕过平台风控或规避反作弊检测的功能。

## 开发状态

```text
Windows：已完整验证（窗口选择、预览、OCR、自动点击均可用）—— 主推平台
macOS：源码运行可用；打包版需 Apple 开发者证书才能稳定使用屏幕录制权限
Linux：暂不计划
```

## 许可证

本项目使用 [MIT License](LICENSE)。
