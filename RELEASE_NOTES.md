# Log Analysis v0.1.0-beta.1

首个公开测试版，将镀膜日志分析工作台封装为 Windows x64 独立应用。

## 主要功能

- 本地只读导入单炉次日志文件夹。
- 总览、理论趋势、光学、设备、异常关联五个分析模块。
- 单层曲线、理论曲线、原始截图和前后切层。
- UTF-8 BOM 逐层汇总与异常清单导出。

## 系统要求

- Windows 10/11 x64
- Microsoft Edge WebView2 Runtime

## 安装与校验

下载 `Log-Analysis-Setup-*.exe` 和 `SHA256SUMS.txt`，使用 PowerShell 的
`Get-FileHash` 核对 SHA-256 后运行安装程序。

## 已知限制

这是未签名测试版，Windows SmartScreen 或组织安全策略可能发出警告或阻止运行。
统计异常只用于提示复核，不代表工艺或产品合格判定。
