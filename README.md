# Log Analysis

面向镀膜工艺工程师的 Windows 本地日志分析工作台。选择一个炉次文件夹后，应用会只读校验日志、生成逐层汇总，并提供理论、光学、设备、异常与关联图表。

> English: Log Analysis is a local, read-only Windows workbench for single-run coating log validation, layer summaries, optical/device trends, anomaly hints, and CSV exports.

## 数据边界

- 原始日志只读，不修改内容或时间戳。
- 分析只在当前电脑完成，不提供上传接口、账号或云端数据库。
- 根目录名称符合 `YYYY-MM-DD.csv` 的文件自动排除。
- 异常与相关性是统计复核线索，不代表工艺或产品合格判定。

真实炉次日志不属于本仓库。测试和公开页面只能使用合成或脱敏数据。

## 安装

### 系统要求

- Windows 10/11 x64。
- Microsoft Edge WebView2 Runtime；Windows 10/11 通常已经安装，缺失时安装程序会显示下载指引。

### 下载与校验

1. 升级前先关闭所有正在运行的 Log Analysis 窗口。
2. 下载 [Log Analysis v0.1.0-beta.4 安装程序](https://github.com/Reyppp/log-analysis/releases/download/v0.1.0-beta.4/Log-Analysis-Setup-v0.1.0-beta.4-x64.exe) 和同一版本的 [SHA256SUMS.txt](https://github.com/Reyppp/log-analysis/releases/download/v0.1.0-beta.4/SHA256SUMS.txt)。也可以先查看[完整版本说明](https://github.com/Reyppp/log-analysis/releases/tag/v0.1.0-beta.4)。
3. 在下载目录打开 PowerShell，运行：

```powershell
Get-FileHash -Algorithm SHA256 .\Log-Analysis-Setup-v0.1.0-beta.4-x64.exe
Get-Content .\SHA256SUMS.txt
```

4. 确认两处显示的 64 位 SHA-256 完全一致；不一致时不要运行安装程序，请重新下载。

### 安装与首次使用

1. 双击 `Log-Analysis-Setup-v0.1.0-beta.4-x64.exe`。
2. 按安装向导继续；程序默认安装到当前用户目录，不需要管理员权限，桌面快捷方式可选。
3. 当前版本是未签名测试版。若 SmartScreen 显示“Windows 已保护你的电脑”，请先确认 SHA-256 已匹配，再选择“更多信息”，核对文件名后选择“仍要运行”。如果组织安全策略禁止运行，请联系管理员，不要关闭系统安全功能。
4. 安装完成后，从开始菜单打开 **Log Analysis**。
5. 点击“选择文件夹”，选择炉次日志目录，再点击“开始分析”。所有数据只在本机处理。

覆盖安装会保留上次选择的炉次路径。卸载默认保留设置，也可以在卸载时选择同时删除。

### 已知限制

- 这是未签名测试版，SmartScreen 或组织安全策略可能发出警告。
- 部分安装环境中，单层详情图表或原始截图可能不显示；该问题仍在修复，不影响逐层汇总和其他全炉分析页面。

## 开发运行

推荐 Python 3.11：

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe desktop.py
```

浏览器开发入口继续保留：

```powershell
.venv\Scripts\python.exe server.py
```

或者双击 `启动镀膜分析.bat`。不要直接双击 `index.html`。

## 测试

```powershell
.venv\Scripts\python.exe -m unittest -v
```

如需运行本地黄金样本验收，请先设置 `LOG_ANALYSIS_GOLDEN_FOLDER` 为样本目录；未设置时自动跳过该项。样本不会进入 Git。

## Windows 构建

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.venv\Scripts\python.exe tools\create_icon.py
.venv\Scripts\pyinstaller.exe --noconfirm --clean "Log Analysis.spec"
```

安装 [Inno Setup 7.1.0](https://jrsoftware.org/isdl.php) 后：

运行 `构建安装包.bat`，脚本会从当前用户或系统安装目录寻找 Inno Setup 编译器，并在 `release/` 中生成安装程序。

生成文件位于 `release/`。GitHub 的 Release 工作流会自动测试、构建、生成 SHA-256 并创建未公开的 Pre-release 草稿。

## 公开网站

`site/` 是独立的静态介绍与下载页面，通过 GitHub Pages 部署。它不是在线分析服务，也不会读取炉次文件。

## License

[MIT](LICENSE)
