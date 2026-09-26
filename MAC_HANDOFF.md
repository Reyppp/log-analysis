## 当前入口（2026-09-26 复核）

- 当前 Mac 项目：`/Users/rey/GPT/projects/L.Log-Analysis`，本地测试版 `0.1.0-beta.10`。
- 运行、安装与构建：[MAC_USAGE.md](MAC_USAGE.md)；源码基线与独立导出方法：[docs/beta10-baseline.md](docs/beta10-baseline.md)。本次将已交付的 beta.10 源码、必要测试和构建入口保存为本地 Git 基线，不推送或发布；已验证源码基线为 `01c72a90b4646b3285912de353864d8bdc703fc7`，导出验证见[周回顾执行记录](/Users/rey/GPT/NP/2026-09-15/f/outputs/AI使用周回顾/2026-09-26-Log基线执行.md)。本次入口文档补注独立提交，不改变该源码基线编号。
- 现存安装包：[release/Log-Analysis-v0.1.0-beta.10-macOS-arm64.dmg](release/Log-Analysis-v0.1.0-beta.10-macOS-arm64.dmg)。SHA-256：`9019820ba0b330aa351382c1611815b915e2e48d55692c3cb8f032cc6369d71c`，本日重新核对一致。
- 当次实际验收：[release/MAC_VALIDATION.md](release/MAC_VALIDATION.md)，记录的是 9 月 20 日交付，不代表本次重新运行完整视觉、安装或真实样本验收。`release/` 为保留在本机的忽略目录，不随源码提交导出。
- **9 月 20 日回复中的 `/Users/rey/Downloads/Log-Analysis-v0.1.0-beta.10-macOS-arm64.dmg` 历史下载链接现已失效**；文件不存在的原因未核实，当前使用上方项目内链接。
- 以下 9 月 11 日迁移目录、beta.9、环境与验证内容原样保留，属于历史记录。接续时以当前入口开始，并重新核对本地状态。

---

# Log Analysis（镀膜日志分析）：Mac 接续交接

更新日期：2026-09-11

## 当前状态

Log Analysis 是本地只读的镀膜日志分析工作台，核心入口为 `analyze_folder(path)`；它识别工控日志与逐层监控日志，提供监控、工控和综合分析以及 CSV/PNG 导出。产品定义仍以 Windows x64 为第一发布平台，Mac 适配用于开发和本地接续，不能据此宣称已有 macOS 安装包或公证发布流程。

Windows 项目目录为：

```text
D:\CDriveData\Projects\coating_analyzer
```

当前版本由 `version.py` 给出：`0.1.0-beta.9`。Windows 当前 HEAD：

```text
df50f07e4f5b22f258d81a783b7651e492d3f20b
Isolate Cocoa alert in platform test
```

Windows 工作树保留 5 个原有业务脏文件，未被迁移适配覆盖：

```text
analyzer.py
index.html
installer/LogAnalysis.iss
test_analyzer.py
version.py
```

Mac 项目目录为：

```text
/Users/rey/Developer/Mac-Migration-20260910/workspace/projects/Log-Analysis
```

写入本交接前，Mac HEAD 与 Windows 一致，也保留这 5 个工作树修改，并另外出现 Finder 产生的未跟踪 `.DS_Store`。`.DS_Store` 不属于业务变更，不要与上述 5 个文件一并提交。本次后续文档提交只新增 `MAC_HANDOFF.md`，提交号见总览配套的 `项目交接验收.json`。

## Mac 启动方式和平台边界

已验证环境为 Apple Silicon、macOS 26.6、Python 3.12.14、pywebview 6.2、PyObjC/Cocoa。Mac 使用迁移目录内独立 Python 环境：

```text
/Users/rey/Developer/Mac-Migration-20260910/tools/venvs/dlog/bin/python
```

Finder 入口：

```text
/Users/rey/Developer/Mac-Migration-20260910/开始使用/镀膜日志分析.command
```

等价的终端启动步骤：

```sh
source "$HOME/Developer/Mac-Migration-20260910/tools/activate.sh"
cd "$HOME/Developer/Mac-Migration-20260910/workspace/projects/Log-Analysis"
"$HOME/Developer/Mac-Migration-20260910/tools/venvs/dlog/bin/python" desktop.py
```

`desktop.py` 在 Mac 选择 Cocoa，提示框使用 Cocoa 依赖；Mac 不增加跨进程单实例锁。Windows 的互斥锁、EdgeChromium 后端和启动行为继续保持原路径。Mac 适配没有改写业务算法、日志格式或 Windows 发布配置。

## 正式源码和数据合同

- `desktop.py` 是桌面启动、Cocoa/Windows 平台分支、原生文件对话框和 CSV 保存入口。
- `server.py` 提供本地服务，`analyzer.py` 负责日志识别、解析、关联和汇总，`index.html` 是前端工作台。
- 产品入口应使用 `analyze_folder(path)`；根目录文档和测试中提到的真实日志均必须保持只读。
- 文件识别、双源关联、质量状态和异常复核必须保留来源与原始值；统计异常只是复核线索，不直接代表工艺或产品判定。
- 工控与监控来源应分别保留，局部覆盖、缺失、断档、未完成层和未关联区间不能被静默填补或合并。
- CSV 使用完整有效数据；图表在高采样量下可以显示精简数据，但不得以精简结果替代统计或导出数据。

## 当前实际原始数据路径

Windows 上与本项目相关的原始样本仍位于：

```text
D:\Work\Y2号机\Y2炉次\Y2-26080\Y226080log
```

该目录当前仍存在，检查到 977 个文件。补充资料还包括：

```text
D:\Work\Q号机\Log\Q26085
D:\Work\Q号机\Q炉次\Q26085
D:\Work\Y2号机\Y2炉次\Y2-26089\Y226089
```

Mac 当前只读检查显示：

```text
/Users/rey/Developer/Mac-Migration-20260910/workspace/data/extra-originals
```

这一目录当前不存在。因此，不能把旧验证记录中的 `/Users/rey/Developer/Mac-Migration-20260910/workspace/data/extra-originals/Y226080log` 当作 Mac 现在已有的可用原始目录。Y226080log 目前应标记为“Windows 原路径仍有，迁移加密归档/清单中有记录”；如果要在 Mac 再做真实导入，先从归档或 Windows 复制到明确的新路径，完成文件数量和 SHA-256 核对，再把该路径交给程序。不要凭旧验证报告重建或编造数据。

## 已完成的历史 Mac 验证与边界

历史迁移验证记录如下：原有 46 项测试中 45 项通过，黄金样本单独提供后通过；新增 2 项平台测试通过。Cocoa 窗口曾读取 Y226080log，得到 243 层、实际时长 97,612 秒，并导出 243 行 CSV。对应记录文件为迁移交付目录中的 `coating-native-result.json`；它证明当时测试程序读到了该路径，不能证明今天 Mac 的 `extra-originals` 目录仍在。

当时的原生导出测试由程序指定输出路径，未实际操作用户的保存对话框。以下项目仍需用户在 Mac 手动确认：

- 通过 Cocoa 文件夹选择器选择当前真实存在的炉次目录，再执行导入、分析和取消。
- 核对监控独立、工控独立、综合模式，以及层/材料/区段筛选和断档显示。
- 用原生保存对话框导出 CSV/PNG，确认没有覆盖原始日志；核对中文、日期、完整有效数据和导出行数。
- 在 Mac 上对实际样本重新确认窗口关闭、日志位置和长曲线操作。自动化测试通过不等于 Office、安装包、签名或用户交互验收通过。

## 下一次接续提示

开始新任务时，先核对 `git status --short --branch`，保留上述 5 个业务脏文件；阅读本交接、仓库 `README.md`、`PRODUCT.md`、`MAC_USAGE.md` 和 `/Users/rey/Developer/Mac-Migration-20260910/workspace/PROJECT_HANDOFF.md`。不要用 Mac 的 `.DS_Store` 或构建缓存覆盖 Windows 工作树。

如果要继续验证 Y226080log，先确认 Windows 源目录或加密归档可读，再把资料复制到 Mac 的新目录并生成独立校验记录；在资料尚未出现前，启动程序只能验证窗口和平台分支，不能称为真实 Y226080log 分析通过。

代码换机前，先提交明确要接续的改动并记录 HEAD；不要把 `node_modules`、Windows 虚拟环境、构建缓存、真实日志或凭据放进 Git。Windows 仍是当前发布和 Inno Setup（.iss）打包端，Mac 侧的 Cocoa 启动验证不改变这一边界。
