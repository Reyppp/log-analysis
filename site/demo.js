(() => {
  "use strict";

  const $ = id => document.getElementById(id);
  const moduleTabs = [...document.querySelectorAll("[data-guide-module]")];
  const modulePanels = [...document.querySelectorAll("[data-guide-panel]")];
  const hotspots = [...document.querySelectorAll("[data-guide-hotspot]")];
  const scopeTabs = [...document.querySelectorAll("[data-site-scope]")];
  const moduleFirstHotspot = {
    combined: { overview: "combined-alignment", device: "combined-device" },
    monitor: { overview: "overview-review", theory: "theory-band", optical: "optical-endpoint", device: "device-metric", anomaly: "anomaly-metric" },
    machine: { overview: "machine-samples", device: "machine-device" }
  };

  const details = {
    "scope-combined": ["综合", "双源关联", "自动匹配工控工作时段与监控镀膜层，并校正时钟偏移。", "需要在同一时间或层号范围内核对两类日志时使用。", "选择综合，再通过总览确认关联状态并进入设备模块。", "关联失败时不会强制合并，两类日志仍可独立分析。"],
    "scope-monitor": ["监控log", "逐层分析", "关联理论、光学、设备记录和统计复核提示。", "需要按镀膜层复核理论设定、光学曲线或设备变化时使用。", "选择监控log，再从左侧进入五个逐层分析模块。", "监控log以层为核心，不包含连续工控时间轴。"],
    "scope-machine": ["工控log", "连续设备记录", "合并连续日期文件并展示设备的实际采样点。", "需要核对功率、真空、温度、气体或转速的连续变化时使用。", "选择工控log，再按材料、区段和设备指标筛选。", "仅有工控log时不推测镀膜层；双源关联后可显示对应层。"],
    "combined-alignment": ["综合总览", "双源关联", "汇总两类日志的完整性、镀膜层匹配和时钟偏移。", "开始跨源设备对照前确认关联结果时使用。", "查看关联状态、匹配层数和时钟偏移，再进入设备模块。", "关联状态描述数据匹配结果，不代表工艺质量。"],
    "combined-motor": ["综合总览", "转速来源", "综合模式以工控log的 Motor Speed 作为逐层转速。", "核对监控log与工控log转速差异时使用。", "查看工控log权威值，并保留监控log参考值用于审计。", "其他设备字段不互相覆盖，仍按数据源分别展示。"],
    "combined-device": ["综合设备", "双源设备对照", "按镀膜层或时间对照工控log与监控log设备数据。", "排查同一层或同一时刻的跨源差异时使用。", "选择横坐标与设备指标，再使用层范围、材料和监控方式筛选。", "时间图展示日志中的实际采样点，不计算插值。"],
    "machine-samples": ["工控log总览", "实际采样点", "统计当前筛选范围内的连续设备记录。", "确认日期文件覆盖范围和可用数据量时使用。", "选择材料或镀膜区段后查看采样点与工作时间变化。", "采样点来自原始日志；趋势展示会优先保留真实边界与极值。"],
    "machine-quality": ["工控log总览", "数据质量", "检查日期连续性、重复时间、时间缺口和设备逻辑。", "解释连续趋势前确认工控数据是否完整时使用。", "在总览中展开整炉工控log结构与时间质量。", "质量提示用于数据核验，不输出产品合格结论。"],
    "machine-device": ["工控log设备", "连续设备趋势", "按时间显示功率、电流、电压、真空、温度、气体和转速。", "需要查看设备在镀膜区段内的连续变化时使用。", "选择材料、区段和设备指标，查看对应实际采样点。", "单选 H 或 L 时只显示该材料参与工作的时间。"],
    "overview-review": ["总览", "重点复核层", "汇总达到重点复核阈值的层。", "完成分析后确定优先检查顺序。", "进入总览，选择重点复核层查看对应记录。", "统计偏离仅提供复核线索，不代表质量结论。"],
    "overview-quality": ["总览", "数据质量", "汇总缺失文件、字段异常和时间逻辑问题。", "解读趋势和复核提示前确认数据可用性。", "展开数据质量记录，按错误、警告和提示逐项核验。", "数据质量问题独立于统计复核提示。"],
    "theory-band": ["理论趋势", "材料与监控方式", "按层显示 H/L 材料及 OMS/Timer 监控方式。", "核对材料切换和监控方式分布时使用。", "选择该区域，再结合层号检查连续性和切换位置。", "材料与监控方式用于分组解释，不直接表示异常。"],
    "theory-rate": ["理论趋势", "理论与实际速率", "对比逐层理论速率和实际速率。", "检查速率偏差或材料分组差异时使用。", "查看同材料曲线及悬停数值，定位偏差层。", "不同材料的设定不同，应在同材料范围内比较。"],
    "optical-endpoint": ["光学", "终点透过率趋势", "对比 Meas、动态 Calc 和理论 End T。", "判断全炉光学终点偏移及拟合变化时使用。", "先查看整体趋势，再进入偏移明显的单层详情。", "曲线用于确定复核范围，不替代成品光谱判定。"],
    "optical-detail": ["光学", "单层详情", "关联单层 Meas/Calc 曲线、理论曲线和原始截图。", "复核特定层的终点偏差或曲线形态时使用。", "使用前一层和后一层切换，并核对同层截图。", "截图仅辅助核验，不参与统计计算。"],
    "device-metric": ["设备", "设备指标", "按层显示功率、温度或真空的均值与波动。", "排查光学偏差对应的设备状态变化时使用。", "选择指标后，比较 H/L 材料曲线及变化范围。", "真空等未声明单位的字段按日志原始值显示。"],
    "device-groups": ["设备", "H/L 分组统计", "分别汇总 H/L 材料的样本数、均值和范围。", "避免材料设定差异造成误判时使用。", "先选择设备指标，再对比分组统计和逐层趋势。", "分组统计描述当前炉次，不构成设备规格限值。"],
    "anomaly-metric": ["异常复核", "复核指标", "显示稳健 Z 分数识别的相对偏离层。", "需要形成统计复核清单时使用。", "切换指标，查看红圈层并对照异常排名。", "样本不足、MAD 为零或字段恒定时不会检测。"],
    "anomaly-ranking": ["异常复核", "异常排名", "按等级和偏离程度排列需复核层。", "需要确定单层核验顺序时使用。", "选择排名记录，再进入对应层的光学或设备详情。", "排名只反映统计偏离程度，不代表质量判定。"]
  };

  const scopeConfig = {
    combined: { note: "已关联 180 个镀膜层", filters: ["起始层 1", "结束层 180", "材料 H / L", "监控方式 OMS / Timer", "镀膜区段 1"] },
    monitor: { note: "当前包含 180 个监控层", filters: ["起始层 1", "结束层 180", "材料 H / L", "监控方式 OMS / Timer", "异常阈值 3.5"] },
    machine: { note: "当前包含 2 个日期文件", filters: ["起始层 1", "结束层 180", "材料 H / L", "监控方式 OMS / Timer", "镀膜区段 1"] }
  };

  let activeScope = "combined";
  let activeModule = "overview";
  let activeHotspot = "combined-alignment";
  let selectedLayer = 96;
  let deviceMetric = "power";
  let anomalyMetric = "residual";

  function setScope(name, focusTab = false) {
    const config = scopeConfig[name];
    if (!config) return;
    activeScope = name;
    scopeTabs.forEach(tab => {
      const active = tab.dataset.siteScope === name;
      tab.classList.toggle("active", active);
      tab.setAttribute("aria-selected", String(active));
      tab.tabIndex = active ? 0 : -1;
      if (active && focusTab) tab.focus();
    });
    moduleTabs.forEach(tab => { tab.hidden = !tab.dataset.guideScopes.split(" ").includes(name); });
    document.querySelectorAll("[data-guide-scope-panel]").forEach(panel => { panel.hidden = panel.dataset.guideScopePanel !== name; });
    $("guideFilterbar").innerHTML = config.filters.map(item => `<span>${item}</span>`).join("");
    $("guideSourceNote").textContent = config.note;
    const currentTab = moduleTabs.find(tab => tab.dataset.guideModule === activeModule && !tab.hidden);
    setModule(currentTab ? activeModule : "overview");
    showDetail(`scope-${name}`);
    requestAnimationFrame(drawAll);
  }

  scopeTabs.forEach((tab, index) => {
    tab.addEventListener("click", () => setScope(tab.dataset.siteScope));
    tab.addEventListener("keydown", event => {
      if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const previous = event.key === "ArrowLeft" || event.key === "ArrowUp";
      const nextIndex = event.key === "Home" ? 0 : event.key === "End" ? scopeTabs.length - 1 : (index + (previous ? scopeTabs.length - 1 : 1)) % scopeTabs.length;
      setScope(scopeTabs[nextIndex].dataset.siteScope, true);
    });
  });

  function showDetail(key, reveal = false) {
    const detail = details[key];
    if (!detail) return;
    activeHotspot = key;
    hotspots.forEach(node => node.classList.toggle("active-hotspot", node.dataset.guideHotspot === key));
    $("guideDetailModule").textContent = detail[0];
    $("guideDetailTitle").textContent = detail[1];
    $("guideDetailFunction").textContent = detail[2];
    $("guideDetailWhen").textContent = detail[3];
    $("guideDetailHow").textContent = detail[4];
    $("guideDetailNote").textContent = detail[5];
    if (reveal && window.matchMedia("(max-width: 1050px)").matches) requestAnimationFrame(() => {
      const explanation = $("guideExplanation");
      explanation.focus({ preventScroll: true });
      explanation.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
    });
  }

  function setModule(name, focusTab = false) {
    activeModule = name;
    moduleTabs.forEach(tab => {
      const active = tab.dataset.guideModule === name;
      tab.classList.toggle("active", active);
      tab.setAttribute("aria-selected", String(active));
      tab.tabIndex = active ? 0 : -1;
      if (active && focusTab) tab.focus();
    });
    modulePanels.forEach(panel => {
      const active = panel.dataset.guidePanel === name;
      panel.classList.toggle("active", active);
      panel.hidden = !active;
    });
    showDetail(moduleFirstHotspot[activeScope][name] || `scope-${activeScope}`);
    requestAnimationFrame(drawAll);
  }

  moduleTabs.forEach(tab => {
    tab.addEventListener("click", () => setModule(tab.dataset.guideModule));
    tab.addEventListener("keydown", event => {
      if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const availableTabs = moduleTabs.filter(item => !item.hidden);
      const index = availableTabs.indexOf(tab);
      const previous = event.key === "ArrowLeft" || event.key === "ArrowUp";
      const nextIndex = event.key === "Home" ? 0 : event.key === "End" ? availableTabs.length - 1 : (index + (previous ? availableTabs.length - 1 : 1)) % availableTabs.length;
      setModule(availableTabs[nextIndex].dataset.guideModule, true);
    });
  });

  hotspots.forEach(node => {
    node.addEventListener("click", event => {
      if (event.target.closest("#guideLayerPrev, #guideLayerNext")) return;
      showDetail(node.dataset.guideHotspot, true);
    });
    node.addEventListener("keydown", event => {
      if (event.key !== "Enter" && event.key !== " ") return;
      if (event.currentTarget !== event.target && event.target.closest("button")) return;
      event.preventDefault();
      showDetail(node.dataset.guideHotspot, true);
    });
  });

  function frame(canvas) {
    const rect = canvas.getBoundingClientRect();
    if (!rect.width || !rect.height) return null;
    const ratio = window.devicePixelRatio || 1;
    canvas.width = Math.round(rect.width * ratio);
    canvas.height = Math.round(rect.height * ratio);
    const context = canvas.getContext("2d");
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    return { context, width: rect.width, height: rect.height };
  }

  function lineChart(id, series, options = {}) {
    const canvas = $(id);
    const target = canvas && frame(canvas);
    if (!target) return;
    const { context, width, height } = target;
    const pad = { left: 34, right: 10, top: 24, bottom: 18 };
    const values = series.flatMap(item => item.values);
    const min = options.min ?? Math.min(...values);
    const max = options.max ?? Math.max(...values);
    const span = max - min || 1;
    context.clearRect(0, 0, width, height);
    context.font = '9px "Segoe UI", sans-serif';
    context.fillStyle = "#718290";
    context.strokeStyle = "#e1e8ed";
    context.lineWidth = 1;
    for (let i = 0; i < 4; i += 1) {
      const y = pad.top + (height - pad.top - pad.bottom) * i / 3;
      context.beginPath(); context.moveTo(pad.left, y); context.lineTo(width - pad.right, y); context.stroke();
      const value = max - span * i / 3;
      context.fillText(options.format ? options.format(value) : value.toFixed(2), 2, y + 3);
    }
    const point = (value, index, count) => ({
      x: pad.left + (width - pad.left - pad.right) * index / Math.max(1, count - 1),
      y: pad.top + (height - pad.top - pad.bottom) * (max - value) / span
    });
    series.forEach((item, seriesIndex) => {
      const points = item.values.map((value, index) => point(value, index, item.values.length));
      context.strokeStyle = item.color;
      context.lineWidth = item.width || 2;
      context.setLineDash(item.dash || []);
      if (options.lines !== false) {
        context.beginPath();
        points.forEach((current, index) => {
          if (!index) context.moveTo(current.x, current.y);
          else if (options.smooth) {
            const previous = points[index - 1];
            context.quadraticCurveTo(previous.x, previous.y, (previous.x + current.x) / 2, (previous.y + current.y) / 2);
            if (index === points.length - 1) context.lineTo(current.x, current.y);
          } else context.lineTo(current.x, current.y);
        });
        context.stroke();
      }
      context.setLineDash([]);
      if (item.points) {
        context.fillStyle = item.color;
        points.forEach(current => { context.beginPath(); context.arc(current.x, current.y, 2.4, 0, Math.PI * 2); context.fill(); });
      }
      context.fillStyle = item.color;
      context.fillRect(pad.left + seriesIndex * 78, 7, 13, 2);
      context.fillStyle = "#586b79";
      context.fillText(item.name, pad.left + 18 + seriesIndex * 78, 10);
    });
    (options.alerts || []).forEach(index => {
      const value = series[0].values[index];
      const current = point(value, index, series[0].values.length);
      context.strokeStyle = "#b42318";
      context.lineWidth = 2;
      context.beginPath(); context.arc(current.x, current.y, 6, 0, Math.PI * 2); context.stroke();
    });
  }

  const overviewH = [0.22, 0.35, 0.18, 0.49, 0.31, 0.58, 0.26, 0.43, 0.19, 0.36, 0.28, 0.51];
  const overviewL = [-0.18, -0.31, -0.24, -0.42, -0.21, -0.35, -0.15, -0.29, -0.45, -0.22, -0.34, -0.18];
  const thickness = [121, 78, 118, 82, 124, 76, 119, 84, 122, 79, 117, 81];
  const rateTheory = [0.62, 0.48, 0.61, 0.47, 0.63, 0.49, 0.61, 0.48, 0.62, 0.47, 0.63, 0.48];
  const rateActual = [0.60, 0.50, 0.59, 0.46, 0.64, 0.47, 0.62, 0.49, 0.60, 0.45, 0.65, 0.47];
  const opticalMeas = [0.43, 0.46, 0.44, 0.49, 0.47, 0.52, 0.48, 0.54, 0.50, 0.53, 0.49, 0.55];
  const opticalCalc = [0.42, 0.45, 0.45, 0.48, 0.48, 0.50, 0.49, 0.52, 0.51, 0.52, 0.50, 0.53];
  const opticalTheory = [0.44, 0.44, 0.46, 0.46, 0.48, 0.48, 0.50, 0.50, 0.51, 0.51, 0.52, 0.52];
  const combinedActualTime = [398, 286, 421, 274, 405, 291, 418, 281, 399, 296, 426, 278];
  const combinedTargetTime = [392, 281, 415, 270, 401, 286, 411, 276, 395, 291, 419, 274];
  const machinePowerH = [5.92, 6.08, 5.87, 6.21, 6.03, 6.17, 5.95, 6.26, 6.11, 5.99, 6.22, 6.06, 6.18, 5.91, 6.24, 6.09, 6.15, 6.01];
  const machinePowerL = [4.08, 4.22, 4.15, 4.31, 4.18, 4.27, 4.12, 4.36, 4.21, 4.16, 4.33, 4.19, 4.29, 4.11, 4.35, 4.23, 4.26, 4.17];

  const deviceData = {
    power: { title: "功率均值逐层趋势", unit: "日志原始值", h: [5.8, 6.0, 5.9, 6.2, 6.1, 6.3, 6.0, 6.2, 6.1, 6.4, 6.2, 6.3], l: [4.1, 4.2, 4.0, 4.3, 4.2, 4.4, 4.1, 4.3, 4.2, 4.5, 4.3, 4.4] },
    temperature: { title: "腔体温度均值逐层趋势", unit: "°C", h: [214, 216, 218, 217, 219, 221, 220, 222, 221, 223, 224, 223], l: [213, 214, 216, 215, 217, 219, 218, 220, 219, 221, 222, 221] },
    vacuum: { title: "真空均值逐层趋势", unit: "日志原始值", h: [2.2, 2.3, 2.1, 2.4, 2.2, 2.5, 2.3, 2.4, 2.2, 2.5, 2.4, 2.3], l: [2.0, 2.1, 1.9, 2.2, 2.0, 2.3, 2.1, 2.2, 2.0, 2.3, 2.2, 2.1] }
  };
  const anomalyData = {
    residual: { title: "终点拟合残差", values: [0.11, 0.14, 0.09, 0.18, 0.12, 0.61, 0.16, 0.13, 0.10, 0.17, 0.48, 0.12], alerts: [5, 10] },
    rate: { title: "实际速率偏差", values: [0.01, -0.02, 0.02, -0.01, 0.03, 0.09, -0.02, 0.01, -0.03, 0.02, -0.08, 0.01], alerts: [5, 10] }
  };

  function drawLayer() {
    const shift = (selectedLayer - 96) * 0.008;
    const meas = [0.18, 0.21, 0.29, 0.42, 0.58, 0.69, 0.63, 0.51, 0.44, 0.47, 0.55, 0.61].map(value => value + shift);
    const calc = [0.17, 0.22, 0.31, 0.43, 0.56, 0.66, 0.62, 0.52, 0.45, 0.48, 0.54, 0.59].map(value => value + shift / 2);
    lineChart("guideLayerCanvas", [{ name: "Meas", values: meas, color: "#075e91" }, { name: "动态 Calc", values: calc, color: "#c5691a" }], { min: 0.1, max: 0.75, smooth: true });
  }

  function drawDevice() {
    const item = deviceData[deviceMetric];
    $("guideDeviceTitle").textContent = item.title;
    $("guideDeviceUnit").textContent = item.unit;
    lineChart("guideDeviceCanvas", [{ name: "H 材料", values: item.h, color: "#075e91", points: true }, { name: "L 材料", values: item.l, color: "#c5691a", points: true }], { smooth: true });
    const row = (name, values) => {
      const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
      return `<tr><td>${name}</td><td>${values.length}</td><td>${mean.toFixed(2)}</td><td>${Math.min(...values).toFixed(2)}-${Math.max(...values).toFixed(2)}</td></tr>`;
    };
    $("guideDeviceStats").innerHTML = row("H 材料", item.h) + row("L 材料", item.l);
  }

  function drawCombinedOverview() {
    lineChart("guideCombinedOverviewCanvas", [
      { name: "监控实际", values: combinedActualTime, color: "#075e91", points: true },
      { name: "工控工作", values: combinedTargetTime, color: "#c5691a", points: true }
    ], { min: 250, max: 450, smooth: true });
  }

  function drawMachineOverview() {
    lineChart("guideMachineOverviewCanvas", [
      { name: "H 材料", values: machinePowerH, color: "#075e91", points: true },
      { name: "L 材料", values: machinePowerL, color: "#c5691a", points: true }
    ], { min: 3.8, max: 6.5, lines: false });
  }

  function drawCombinedDevice() {
    const monitorH = deviceData.power.h;
    const monitorL = deviceData.power.l;
    lineChart("guideCombinedDeviceCanvas", [
      { name: "H 工控", values: machinePowerH.slice(0, 12), color: "#075e91", points: true },
      { name: "L 工控", values: machinePowerL.slice(0, 12), color: "#c5691a", points: true },
      { name: "H 监控", values: monitorH, color: "#075e91", points: true, dash: [3, 3] },
      { name: "L 监控", values: monitorL, color: "#c5691a", points: true, dash: [3, 3] }
    ], { min: 3.8, max: 6.6, smooth: true });
  }

  function drawMachineDevice() {
    lineChart("guideMachineDeviceCanvas", [
      { name: "H 材料", values: machinePowerH, color: "#075e91", points: true },
      { name: "L 材料", values: machinePowerL, color: "#c5691a", points: true }
    ], { min: 3.8, max: 6.5, lines: false });
  }

  function drawAnomaly() {
    const item = anomalyData[anomalyMetric];
    $("guideAnomalyTitle").textContent = item.title;
    lineChart("guideAnomalyCanvas", [{ name: item.title, values: item.values, color: "#075e91", points: true }], { alerts: item.alerts, smooth: true });
  }

  function drawAll() {
    drawCombinedOverview();
    drawMachineOverview();
    lineChart("guideOverviewCanvas", [{ name: "H 材料", values: overviewH, color: "#075e91" }, { name: "L 材料", values: overviewL, color: "#c5691a" }], { min: -0.6, max: 0.7, alerts: [5, 10] });
    lineChart("guideThicknessCanvas", [{ name: "物理厚度", values: thickness, color: "#075e91", points: true }], { min: 60, max: 135, smooth: true });
    lineChart("guideRateCanvas", [{ name: "理论速率", values: rateTheory, color: "#075e91", points: true }, { name: "实际速率", values: rateActual, color: "#c5691a", points: true }], { min: 0.4, max: 0.7, smooth: true });
    lineChart("guideOpticalCanvas", [{ name: "Meas", values: opticalMeas, color: "#075e91" }, { name: "动态 Calc", values: opticalCalc, color: "#c5691a" }, { name: "理论 End T", values: opticalTheory, color: "#6d68a8" }], { min: 0.38, max: 0.58, smooth: true });
    drawLayer();
    drawCombinedDevice();
    drawDevice();
    drawMachineDevice();
    drawAnomaly();
  }

  function moveLayer(delta) {
    selectedLayer = Math.max(95, Math.min(99, selectedLayer + delta));
    $("guideLayerLabel").textContent = `${selectedLayer}层`;
    $("guideImageLayer").textContent = `Layer ${selectedLayer}`;
    showDetail("optical-detail");
    drawLayer();
  }

  $("guideLayerPrev").addEventListener("click", event => { event.stopPropagation(); moveLayer(-1); });
  $("guideLayerNext").addEventListener("click", event => { event.stopPropagation(); moveLayer(1); });

  document.querySelectorAll("[data-device-metric]").forEach(button => button.addEventListener("click", () => {
    deviceMetric = button.dataset.deviceMetric;
    document.querySelectorAll("[data-device-metric]").forEach(item => {
      const active = item === button;
      item.classList.toggle("active", active);
      item.setAttribute("aria-pressed", String(active));
    });
    showDetail("device-metric");
    drawDevice();
  }));

  document.querySelectorAll("[data-anomaly-metric]").forEach(button => button.addEventListener("click", () => {
    anomalyMetric = button.dataset.anomalyMetric;
    document.querySelectorAll("[data-anomaly-metric]").forEach(item => {
      const active = item === button;
      item.classList.toggle("active", active);
      item.setAttribute("aria-pressed", String(active));
    });
    showDetail("anomaly-metric");
    drawAnomaly();
  }));

  new ResizeObserver(drawAll).observe(document.querySelector(".guide-client"));
  setScope("combined");
})();
