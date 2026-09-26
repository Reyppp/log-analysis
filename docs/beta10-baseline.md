# Mac beta.10 源码基线

2026-09-26：在 `main` 的 `4d6bf12` 之后保存本地源码基线。目标是保留 9 月 20 日已交付版本，不新增业务规则、不重打包、不推送、不创建或移动标签。

## 纳入与排除

保存当前 `analyzer.py`、`desktop.py`、`server.py`、`index.html`、`version.py`、对应测试、Mac spec、构建脚本、前端检查和使用说明。分析器中此前已存在的同层多次运行关联修复也随基线保存：它已在现存 DMG 内，不能退回旧 HEAD 后称为 beta.10。现有许可证、图标、Windows spec、网站合成演示等已跟踪文件继续随提交导出。独立导出发现三个 Windows BAT 在旧 Git 对象中为 LF、工作区为 CRLF；补充 `.gitattributes` 的 `*.bat -text` 并保存现有 CRLF 字节，使归档也保留换行，不修改脚本逻辑。

Windows Inno Setup 的未提交 beta.8 → beta.9 默认版本修改不属于 Mac 基线，留在原工作区。`.DS_Store`、真实炉次日志、数据库、备份、凭据、虚拟环境、缓存、`build/`、`dist/`、`release/` 和本机设置不纳入；不删除这些文件。测试使用源码内生成的合成样本，真实样本不属于提交。

## 现有包与源码证据

项目内 `release/Log-Analysis-v0.1.0-beta.10-macOS-arm64.dmg` 的 SHA-256 为：

`9019820ba0b330aa351382c1611815b915e2e48d55692c3cb8f032cc6369d71c`

本次只读挂载现有 DMG，逐项比较包内 `analyzer`、`server`、`version`、`desktop` 的 Python 代码对象与当前源码在 Python 3.12、optimize=1 下的编译结果（仅标准化构建路径），全部一致；`index.html` 字节一致。该检查覆盖运行入口，不表示每个依赖或整个 DMG 能逐字节重复构建。

9 月 20 日安装与原生交互验收仍保存在本机 `release/MAC_VALIDATION.md`；它不进入源码归档。9 月 26 日已验证源码基线为 `01c72a90b4646b3285912de353864d8bdc703fc7`；独立导出检查见[周回顾执行记录](/Users/rey/GPT/NP/2026-09-15/f/outputs/AI使用周回顾/2026-09-26-Log基线执行.md)。本次仅补注入口文档，文档提交与已验证源码基线区分，不改变上述编号。

## 从明确提交独立导出

下面的 `BASELINE_COMMIT` 已固定为通过独立导出检查的源码基线；`EXPORT_DIR` 必须是新建的空目录，避免混入原工作区代码。

```sh
BASELINE_COMMIT=01c72a90b4646b3285912de353864d8bdc703fc7
EXPORT_DIR=<独立空目录的绝对路径>
mkdir -p "$EXPORT_DIR"
git archive "$BASELINE_COMMIT" | tar -x -C "$EXPORT_DIR"
cd "$EXPORT_DIR"
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-build.txt
.venv/bin/python -m unittest -v
node tools/test_frontend.cjs
.venv/bin/python desktop.py --smoke-test
```

依赖从可信 Python 包索引安装；不复制旧 `.venv`，不复制源码外的私有配置。Node 仅用于无第三方依赖的前端检查，不是应用运行依赖。黄金样本测试默认跳过；只有单独提供获授权的只读样本并设置 `LOG_ANALYSIS_GOLDEN_FOLDER` 才运行，跳过不等于通过。

2026-09-26 检查环境使用 Python 3.12.14、pandas 2.2.3、NumPy 2.3.5、Plotly 6.3.1、pywebview 6.2.1、PyInstaller 6.22.2、Pillow 12.3.0。`requirements*.txt` 并非完整锁文件；默认安装可能解析为更新版本，因此更换依赖后应重新运行相关检查，不能声称复现了原包哈希。若需靠近本次环境，可在安装时明确指定上述已验证版本。

## 安全重建 Mac 应用

在 Apple 芯片 Mac、独立导出目录、干净 Python 3.12 环境中安装构建依赖，然后执行：

```sh
.venv/bin/python tools/build_macos.py
```

构建入口负责先生成 `build/mac/icon.icns`（使用系统 Helvetica 字体），再调用 `Log Analysis macOS.spec`；**不要直接运行 spec**，否则干净导出中没有预生成图标。所需 HTML、Python 模块、许可证均来自提交；Plotly/Cocoa 资源来自安装的依赖。生成的 `.app` 自带 Python，不需要运行时访问原项目或真实样本。

脚本会重建导出目录下的 `build/`、`dist/`、`release/`，并复制同名 DMG/校验文件到 `~/Downloads`；运行前保留 Downloads 中可能存在的同名旧包。不要在原交付目录重建并替换现有验收产物。本轮未运行这个重建步骤，也未替换安装包。新构建需另行记录哈希与验收，当前历史验收不可自动继承。
