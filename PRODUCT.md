# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

主要用户是 Windows 桌面端的镀膜工艺工程师。他们在本地选择单个炉次日志文件夹，核验数据质量，查看逐层理论、光学、设备、异常与关联信息，并导出复核清单。

## Product Purpose

Log Analysis 将分散的镀膜日志只读汇总为可筛选、可视化、可导出的工程工作台。成功意味着用户无需手工拼接 CSV 即可定位值得复核的层，同时原始日志保持不变。

## Positioning

分析在用户电脑本地完成，自动关联逐层理论、实测光学与设备数据；统计异常只提供复核线索，不替代工艺规格或成品判定。

## Operating Context

应用运行在 Windows 10/11 x64，使用原生文件夹选择器导入炉次目录。桌面应用以独立窗口运行；公开网站只用于产品介绍、隐私说明和 GitHub 下载，不接收日志。

## Capabilities and Constraints

- 单炉次、离线、只读分析；忽略根目录 `YYYY-MM-DD.csv`。
- 保留总览、理论趋势、光学、设备、异常关联五个模块和 CSV 导出。
- 中文界面为主，核心入口保持 `analyze_folder(path) -> AnalysisResult`。
- 第一版只支持 Windows x64，不提供在线分析、数据库、账号或自动更新。
- 首个二进制版本是未签名测试版 `v0.1.0-beta.1`。

## Brand Commitments

产品名为 **Log Analysis**，副标题为“镀膜日志分析工作台”。应用沿用现有冷静、精密、低干扰的蓝灰工业工作台语言，避免模板化营销外观。

## Evidence on Hand

现有 `index.html` 是产品交互和视觉事实来源。本地黄金样本不得进入公开仓库、网站图片或发布产物；公开演示必须使用脱敏或合成数据。

## Product Principles

- 原始日志只读，数据不离开本机。
- 工程含义优先于装饰效果。
- 错误必须说明问题与恢复方法。
- 公开内容不夸大统计结论。
- 使用最少依赖维持可维护的离线工具。

## Accessibility & Inclusion

支持键盘焦点、清晰状态色、可读中文标签、缩放与窄屏布局；不能只依赖颜色表达异常等级。
