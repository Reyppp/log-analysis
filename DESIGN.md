# Log Analysis Design System

Log Analysis 使用冷静、精密、低干扰的蓝灰工业工作台语言。界面首先服务于工程判断：层级清楚、单位完整、状态明确，装饰不能压过数据。

## Visual direction

- 以浅灰蓝背景和白色工作面区分层级，深蓝只用于主操作、当前导航和关键曲线。
- 正常、关注、错误分别使用绿、橙、红语义色；状态必须同时有文字，不能只靠颜色表达。
- 主要容器使用 1px 边框和 8–14px 圆角。阴影仅用于需要浮出页面的窗口、视口聚焦和网站产品演示。
- 不使用渐变、在线字体、装饰性玻璃效果或多层卡片嵌套。

## Tokens

| Role | Value |
| --- | --- |
| Page background | `#f1f4f7` |
| Surface | `#ffffff` |
| Soft surface | `#e8eef2` |
| Border | `#ccd7df` |
| Primary text | `#17242e` |
| Secondary text | `#586b79` |
| Primary blue | `#075e91` |
| Deep blue | `#063b5a` |
| Highlight cyan | `#9fd7ef` |
| Success | `#267451` |
| Danger | `#b42318` |
| Radius | `8px` controls, `14px` major surfaces |

Use `Segoe UI`, `Microsoft YaHei`, then system sans-serif. Numeric log paths and checksums use Consolas or the system monospace stack.

## Layout

- Desktop application: fixed top operation bar, source-context switch, contextual left navigation, sticky filter row, and one active analysis module in the main work area. The source switch offers only the detected modes in the order 综合, 监控log, 工控log. Combined and work-control contexts each expose two modules; segmentation remains an internal calculation rather than a navigation destination.
- The primary desktop viewport is 1440×900 with a 960×640 minimum. Below 900px, module navigation becomes horizontal.
- Public site: generous editorial sections with a split hero, an interactive three-scope explanation, and a full-width five-module monitor-log guide. On desktop the guide uses a client view beside its explanation panel; at ≤1050px the explanation moves below and focuses/reveals after a hotspot is selected. Privacy and installation sections follow.
- Use spacing in a 4px-derived rhythm. Dense controls may use 8–12px gaps; sections use 24–40px; public-site sections use 64px or more.

## Components

### Buttons

Primary actions use the primary blue fill, white text, a minimum 44px hit target and a visible disabled state. Secondary actions use a neutral surface and border. Text links are reserved for navigation or documentation.

### Navigation and filters

The active source context and module are unmistakable through label, foreground and surface treatment. Material and monitoring-method filters behave as segmented switches. Switching contexts preserves each context's filters, selected layer, activity session and chosen metrics.

### Charts

Every chart has a complete Chinese title, X/Y axis names, reliable units, legend and formatted hover content. Regular chart panels use one shared title position, legend row and plot margins. Device pages align the metric rail and chart to one enlarged, equal-height row; any H/L comparison table sits below them and spans their combined width. H/L series are always ordered as “H 材料” then “L 材料”. Device layer trends use restrained spline lines with visible data points. Combined device comparison supports layer and time axes. Work-control trends and combined time trends use an internal 8,000-point budget, preserving real boundaries and extrema without presenting sampling diagnostics in the chart. Viewport gestures never reload data. A single-material filter hides every interval in which that material is inactive. Do not connect lines across coating layers, filtered intervals or axis breaks.

Work-control and monitor device charts share one ordered blue-orange-purple-green palette. Material colors remain stable after filtering, gas channels use the same palette order, and unified hover details place each trace marker and name before its values. Work-control gas metrics use separate O₂ and Ar entries in the same metric rail pattern as monitor logs.

Time charts use a Plotly top secondary x-axis for coating layers. It overlays and matches the bottom time axis, sits below the first-row legend and above the plotting area, has no axis title, and uses the compact `X层` form while table cells remain numeric. Tick density recalculates after zoom, resize and viewport focus without requesting or redrawing data. The two horizontal axes pan and zoom together; vertical boundary lines may remain inside the plot, but layer text must not overlap curves, titles, legends or the mode bar. Each chart offers viewport focus; `Esc` exits and focus returns to the triggering control.

### Tables and status

Visible columns use Chinese field names from shared metadata. Unknown fields must be shown as `未命名字段（内部名）` instead of disappearing. Empty, loading, disconnected and failed states explain both the condition and the next recovery action.

## Accessibility and motion

- Preserve visible keyboard focus and logical focus order.
- Provide semantic dialog roles for chart focus and lock background scrolling while open.
- Respect `prefers-reduced-motion`; motion is short and communicates state rather than decoration.
- Maintain readable contrast and never communicate anomaly severity with color alone.
- The public guide renders synthetic chart data on `Canvas`; module navigation uses `tablist`/`tab` semantics with roving keyboard focus, arrow keys and Home/End, while metric switches expose `aria-pressed`. Hotspots are keyboard-focusable; on narrow layouts, selecting one focuses and reveals the explanation panel.

## Content rules

Use “理论” for planned values and “监控方式” for OMS/Timer. Statistical anomalies are always described as review prompts, never pass/fail conclusions. The public site states that all log analysis remains local and uses only synthetic or anonymized imagery.
