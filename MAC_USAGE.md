# Log Analysis macOS 版

版本：0.1.0-beta.10。本包适用于 Apple 芯片 Mac；已在 macOS 27.0 验证的项目见交付验证记录。无需安装 Python 或其他开发工具。

## 安装

1. 打开 `Log-Analysis-v0.1.0-beta.10-macOS-arm64.dmg`。
2. 将 **Log Analysis** 拖到 **Applications（应用程序）**。覆盖旧版前先退出应用。
3. 从“应用程序”打开 Log Analysis，再退出磁盘映像。

这是本地测试版，未经过 Apple Developer ID 签名与公证。系统如阻止打开，请确认来源及 SHA-256 后，在“系统设置 → 隐私与安全性”查看该应用的允许打开选项；组织策略不允许时联系管理员。无需关闭系统安全功能。

同目录的 `.dmg.sha256` 文件记录安装包 SHA-256，可使用 `shasum -a 256` 检查 DMG。

## 使用

点击“选择文件夹”并选择炉次日志目录，再点击“开始分析”。选择器取消后保留原目录。日志只读、分析离线运行。

综合总览和监控 log 总览显示当前筛选的理论总膜厚及 H/L 小计，单位 nm，包含尚未完成的配方层；缺失厚度标注统计不完整。

CSV 使用工具栏导出；图表使用图内的“保存 PNG”按钮。选择原始日志目录之外的位置保存，避免覆盖源数据。图表放大后可用 Esc 退出。

设置及诊断日志位于 `~/Library/Application Support/Log Analysis/`，升级保留设置。新设置不存在时兼容读取旧的 `~/AppData/Local/Log Analysis/settings.json`。

## 开发与构建

在 Apple 芯片 Mac 使用 Python 3.12 创建独立虚拟环境，安装 `requirements-build.txt`，运行 `python -m unittest -v` 和 `python tools/build_macos.py`。

构建生成独立 `.app`、DMG 与 SHA-256，并将后两者复制到“下载”文件夹。Windows 构建继续使用原有 spec 和 Inno Setup。

## 当前产物与源码基线（2026-09-26）

当前有效 DMG 位于项目 `release/`；9 月 20 日回复中的 Downloads 链接已失效。参见 [当前交接入口](MAC_HANDOFF.md) 和 [源码基线与独立重建说明](docs/beta10-baseline.md)。先运行 `tools/build_macos.py` 生成图标和应用，不直接运行依赖预生成图标的 spec。本次仅保存源码基线，不重建或替换历史 DMG。
