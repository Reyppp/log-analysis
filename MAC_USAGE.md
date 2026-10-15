# Log Analysis macOS 版

版本：0.1.0-beta.10，Mac 构建号 10.2。本包适用于 Apple 芯片 Mac；实际验证项目见交付验证记录。无需安装 Python 或其他开发工具。

## 安装

1. 打开下载文件夹中的 `Log-Analysis-v0.1.0-beta.10-macOS-arm64-20261015.dmg`。
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

## 界面更新（2026-10-15）

保留蓝灰配色，调整总览、筛选、异常分页、导出范围说明及顶部工具栏对齐；不改变计算代码和原始日志。功能版本仍为 `0.1.0-beta.10`，Mac 构建号更新为 `10.2`。

日期版 DMG 与 `.dmg.sha256` 保存在“下载”文件夹和项目 `release/`。本机更新、备份与验证记录见 [本轮记录](release/upgrade-20261015-112238/UPGRADE_REPORT.md)。

## 历史产物与源码基线（2026-09-27）

当日 DMG 与 `.dmg.sha256` 已保存到 `/Users/rey/Downloads/`，项目 `release/` 也保留副本。历史包 SHA-256：`1f2e09f68c127f446cfa3f622bf95a9cd1c8e03ddf47276cfe4391b494db8dc7`。

完整功能验收见 [原交付记录](release/MAC_VALIDATION.md)；日期版构建、独立安装、真实分析、CSV 导出和重开验证见 [本轮记录](release/upgrade-20260927/mac-summary.md)。本轮未重复全部视觉验收。源码基线说明见 [独立重建说明](docs/beta10-baseline.md)。先运行 `tools/build_macos.py` 生成图标和应用，不直接运行依赖预生成图标的 spec。

## 2026-09-27 包版本标识补正

功能版本保持 `0.1.0-beta.10`；已装 Mac 代码已与该基线一致，此次不改变计算。包元数据新增 `CFBundleVersion=10.1`（beta.10 的首次包标识补正）及完整 `LogAnalysisVersion=0.1.0-beta.10`；关于面板继续显示完整功能版本。标准短版本按 Apple 三段数字格式保留 `0.1.0`，不能仅凭该字段判断 beta 版本。

构建生成的 DMG 名称现在附加当天日期（例如 `-20260927.dmg`），同名产物已存在时停止，避免覆盖历史包。安装前保留旧应用及 Application Support 设置；本轮证据在 `release/upgrade-20260927/`。
