# CoursePilot · 网课播放自动化助手

> 网课看一半，又弹"我还在看"？
> CoursePilot 用**本地 OCR** 识别屏幕上的观看确认弹窗并**自动点击**——
> 选好窗口、点一下开始，挂机播放不中断，双手彻底解放。

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Platform: macOS / Windows](https://img.shields.io/badge/Platform-macOS%20%7C%20Windows-lightgrey)]()

CoursePilot 是一个**纯本地**运行的网课播放自动化工具：识别视频播放中反复出现的"继续观看"确认提示，自动替你点掉，再也不用每隔几分钟手动确认一次。支持 macOS 和 Windows。

---

## 核心卖点

- **⚡ 自动点掉"我还在看"**：识别 `继续学习 / 继续播放课程 / 我还在学习` 等确认弹窗并自动点击，观看过程零打断
- **📺 挂机播放不中断**：视频自己往下放，不用一直守在屏幕前
- **🔒 完全本地、不上传**：屏幕内容只在你的设备上处理，不要求登录、不上传截图、不收集账号信息
- **🎯 只点白名单按钮**：仅处理你配置的"继续观看"类文字，**绝不触碰**提交 / 交卷 / 支付 / 购买 / 删除等操作
- **🪟 窗口级精确控制**：支持 Chrome、B 站及任意可捕获窗口，你选哪个窗口就只动哪个窗口

> 📸 演示 GIF（补录中）：弹窗出现 → 自动点击 → 视频继续

## 快速开始

**macOS（推荐源码运行，稳定）**

```sh
git clone https://github.com/fsh114514/CoursePilot.git
cd CoursePilot
python3 -m venv .venv
.venv/bin/pip install -e '.[macos]'
./run_macos.command
```

**Windows（免配置，下载即用）**

到 [Releases](https://github.com/fsh114514/CoursePilot/releases) 下载 `CoursePilot-Windows-x64.zip`（解压版）或 `CoursePilot-Windows-x64.exe`（免解压版），启动即用，无需安装任何额外组件。

## 首次使用

1. 启动 CoursePilot，若提示权限，点"请求屏幕录制和辅助功能权限"。
2. 授权后**完全退出并重启**应用（macOS 权限在启动时生效）。
3. 把课程窗口放回当前台前调度组，点击"刷新窗口"。
4. 从列表选择课程窗口，确认预览正确。
5. 点击"开始监控"，然后……就可以去做别的事了。

## 自定义提示词

只填按钮上**实际显示**的文字，例如：

- 继续学习
- 继续播放课程
- 我还在学习

不要填"提交 / 交卷 / 支付 / 购买 / 删除"等页面操作词。内置提示词会在设置页直接列出，无需重复添加。

## 平台状态

| 平台 | 状态 |
|---|---|
| **Windows** | ✅ 完整验证（窗口选择 / 预览 / OCR / 自动点击），**主推平台** |
| **macOS** | ⚠️ 源码运行可用；打包版需 Apple 开发者证书才能稳定使用屏幕录制权限 |

> macOS 注意：未签名打包版的屏幕录制权限可能不稳定，推荐源码运行；台前调度收起的窗口可能无法捕获，请把目标窗口放回当前调度组。

## 隐私与安全

- 屏幕内容**默认只在本机处理**，不要求登录、不上传截图、不收集课程账号信息。
- 只允许配置"继续观看"类白名单词。
- 不提供隐藏自动化行为、绕过平台风控或规避反作弊检测的功能。

## 本地测试页

运行 `./run_test_site.command` 会在本机 `127.0.0.1` 启动一个显示"我还在看"的测试页，用于验证窗口预览、OCR 识别和按钮点击。

## 构建 Release

```sh
# Windows（Python 3.12）
./scripts/fetch_tesseract_win.sh   # 获取并裁剪 Tesseract 到 vendor/tesseract/
./build_windows.ps1                # 产出 zip（解压版）+ exe（免解压版）+ sha256

# macOS（Apple Silicon）
./build_macos.command              # 产出 zip + dmg + sha256
```

发布到 GitHub Releases：

```sh
gh release create v0.2.0 \
  dist/CoursePilot-Windows-x64.zip dist/CoursePilot-Windows-x64.zip.sha256 \
  dist/CoursePilot-Windows-x64.exe dist/CoursePilot-Windows-x64.exe.sha256 \
  dist/CoursePilot-macOS-arm64.zip dist/CoursePilot-macOS-arm64.zip.sha256 \
  dist/CoursePilot-macOS-arm64.dmg dist/CoursePilot-macOS-arm64.dmg.sha256 \
  --title "CoursePilot v0.2.0" --notes "..."
```

## 许可证

[MIT License](LICENSE)

---

⭐ 项目对你有用？点个 Star，让更多网课党看到它。
