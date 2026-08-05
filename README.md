# CoursePilot

## AI 网课播放辅助｜续课助手

![CoursePilot 图标](assets/coursepilot-icon.png)

CoursePilot 是一个面向 macOS 和 Windows 的本地 AI 屏幕识别工具，用来识别课程播放过程中出现的“我还在看”“继续观看”等确认提示，并在用户授权后点击对应按钮。

它不依赖油猴脚本、浏览器插件或特定网站适配器，屏幕内容只在本机处理，适合重复出现观看确认弹窗的课程播放场景。

> 当前状态：macOS Apple Silicon 版本已完成本机验证；Windows 适配器尚未实现，暂不能发布可用的 Windows 版本。

## 功能特点

- 本地 AI/OCR 识别屏幕中的继续观看提示。
- 支持 Chrome、哔哩哔哩及其他可捕获的普通窗口。
- 只识别白名单提示词，不处理提交、交卷、支付、购买、删除等操作。
- 支持用户添加自定义按钮文字，并在设置页面显示内置提示词。
- 不上传屏幕内容，不注入网页，不修改网页代码。
- macOS 使用 Apple Vision 和 ScreenCaptureKit 本地处理。
- 后续计划支持 Windows 原生窗口捕获和输入控制。

## 搜索关键词

网课辅助、刷课辅助、课程播放自动化、自动处理继续观看、AI 屏幕识别、本地 OCR、自动点击提示、视频播放助手、macOS、Windows、CoursePilot。

## macOS 使用教程

### 1. 下载并启动（普通用户）

在 GitHub Releases 下载 `CoursePilot-macOS-arm64.zip`，解压后将 `CoursePilot.app` 拖到“应用程序”文件夹，再双击启动。

这是 Apple Silicon 版本。如果 macOS 提示无法验证开发者，请在 Finder 中右键点击 `CoursePilot.app`，选择“打开”，再确认打开。首次启动仍然需要授予屏幕录制和辅助功能权限。

### 2. 从源码运行（开发者）

```sh
git clone https://github.com/fsh114514/CoursePilot.git
cd CoursePilot
python3 -m venv .venv
.venv/bin/pip install -e '.[macos]'
./run_macos.command
```

也可以直接双击 `run_macos.command` 启动。

### 3. 第一次使用

1. 打开“系统设置 → 隐私与安全性”。
2. 在“屏幕录制”中允许 Python 或 CoursePilot。
3. 在“辅助功能”中允许 Python 或 CoursePilot。
4. 重启程序。
5. 把课程窗口放到当前台前调度组，并点击“刷新窗口”。
6. 从列表选择课程窗口，确认预览正确。
7. 点击“开始监控”。

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

Windows 原生窗口捕获、OCR 和输入控制适配器正在开发中。

当前仓库中的 Windows 入口会明确提示尚未实现，因此暂不建议在 Windows 上安装或发布安装包。Windows 版本完成后，会补充：

1. Windows 安装包下载地址。
2. 屏幕捕获权限说明。
3. 窗口选择和预览步骤。
4. Windows Defender 和输入控制注意事项。

## 本地测试页

运行下面的命令会启动本地测试页：

```sh
./run_test_site.command
```

页面会在几秒后显示“我还在看”，用于验证窗口预览、OCR 识别和按钮点击。测试页只在 `127.0.0.1` 本机运行。

## 当前 Release

`v0.1.0` 目前只提供 macOS Apple Silicon 包：

- `CoursePilot-macOS-arm64.zip`
- `CoursePilot-macOS-arm64.zip.sha256`

Windows 安装包会在 Windows 原生适配器完成并经过另一台 Windows 电脑实测后再发布。

## 隐私与安全

- 屏幕内容默认只在本机处理。
- 不要求登录、不上传截图、不收集课程账号信息。
- 只允许用户配置继续观看类白名单词。
- 不提供隐藏自动化行为、绕过平台风控或规避反作弊检测的功能。

## 开发状态

```text
macOS：可用原型，已完成本地测试
Windows：待实现
Linux：暂不计划
```

## 许可证

本项目使用 [MIT License](LICENSE)。
