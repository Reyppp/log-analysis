from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from analyzer import (
    AnalysisError,
    analyze_folder,
    compute_correlations,
    csv_bytes,
    detect_anomalies,
    load_layer_detail,
    source_fingerprint,
)


METRIC_LABELS = {
    "phy_thick": "物理厚度",
    "recipe_rate": "配方速率",
    "actual_rate": "实际速率",
    "rate_delta": "速率偏差",
    "planned_time": "计划时间 (s)",
    "actual_time": "实际时间 (s)",
    "time_delta": "时间偏差 (s)",
    "final_meas": "终点 Meas",
    "final_calc": "终点动态 Calc",
    "end_t": "配方 End T",
    "fit_end_residual": "终点 Meas−Calc",
    "recipe_end_offset": "终点 Meas−End T",
    "fit_mae": "拟合 MAE",
    "fit_rmse": "拟合 RMSE",
    "fit_p95_abs": "拟合 P95 绝对残差",
    "fit_max_abs": "拟合最大绝对残差",
    "signal_median": "信号中位数",
    "signal_std": "信号标准差",
    "signal_cv": "信号变异系数",
    "power_mean": "有效功率均值",
    "power_std": "有效功率标准差",
    "power_range": "有效功率范围",
    "current_mean": "有效电流均值",
    "current_std": "有效电流标准差",
    "current_range": "有效电流范围",
    "voltage_mean": "有效电压均值",
    "voltage_std": "有效电压标准差",
    "voltage_range": "有效电压范围",
    "vacuum_mean": "腔体真空均值",
    "vacuum_std": "腔体真空标准差",
    "chamber_temp_mean": "腔体温度均值",
    "chamber_temp_std": "腔体温度标准差",
    "water_in_mean": "进水温度均值",
    "water_out_mean": "出水温度均值",
    "motor_mean": "转速均值",
    "motor_std": "转速标准差",
    "o2_mean": "O₂ 均值",
    "ar_mean": "Ar 均值",
}

DEVICE_CHOICES = [
    ("power_mean", "power_std"),
    ("current_mean", "current_std"),
    ("voltage_mean", "voltage_std"),
    ("vacuum_mean", "vacuum_std"),
    ("chamber_temp_mean", "chamber_temp_std"),
    ("water_in_mean", None),
    ("water_out_mean", None),
    ("motor_mean", "motor_std"),
    ("o2_mean", None),
    ("ar_mean", None),
]


@st.cache_data(show_spinner=False)
def cached_analyze(path: str, fingerprint: tuple) -> object:
    del fingerprint
    return analyze_folder(path)


@st.cache_data(show_spinner=False)
def cached_layer(path: str, layer: int, fingerprint: tuple) -> dict:
    del fingerprint
    return load_layer_detail(path, layer)


def format_duration(seconds: float) -> str:
    if pd.isna(seconds):
        return "—"
    seconds = int(round(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def empty_state() -> None:
    st.info("输入炉次日志文件夹路径并点击“分析”。程序只读原始文件，并忽略根目录所有 YYYY-MM-DD.csv。")


def main() -> None:
    st.set_page_config(page_title="镀膜日志自动分析", page_icon="📈", layout="wide")
    st.title("镀膜日志自动分析")
    st.caption("单炉次 · 本地只读 · 统计异常只用于提示复核，不代表合格判定")

    with st.sidebar:
        st.header("导入")
        input_path = st.text_input("炉次文件夹", value=st.session_state.get("path_input", ""), placeholder=r"C:\Logs\Batch-001")
        if st.button("分析", type="primary", width="stretch"):
            st.session_state["path_input"] = input_path.strip().strip('"')
            st.session_state["analysis_path"] = st.session_state["path_input"]

    path = st.session_state.get("analysis_path", "")
    if not path:
        empty_state()
        return

    try:
        fingerprint = source_fingerprint(path)
        if not fingerprint:
            raise AnalysisError(f"文件夹不存在或没有可分析文件：{path}")
        with st.spinner("正在解析并汇总逐层数据…"):
            result = cached_analyze(path, fingerprint)
    except AnalysisError as exc:
        st.error(str(exc))
        return
    except Exception as exc:
        st.error(f"分析失败：{exc}")
        return

    summary = result.layer_summary
    threshold = st.sidebar.slider("统计异常阈值 |robust z|", 2.5, 5.0, 3.5, 0.1)
    anomalies = detect_anomalies(summary, threshold)
    layers = summary["layer"].astype(int)
    layer_range = st.sidebar.slider("层范围", int(layers.min()), int(layers.max()), (int(layers.min()), int(layers.max())))
    materials = st.sidebar.multiselect("材料", sorted(summary["material"].dropna().unique()), default=sorted(summary["material"].dropna().unique()))
    methods = st.sidebar.multiselect("终止方式", sorted(summary["method"].dropna().unique()), default=sorted(summary["method"].dropna().unique()))
    mask = summary["layer"].between(*layer_range) & summary["material"].isin(materials) & summary["method"].isin(methods)
    filtered = summary.loc[mask].copy()
    filtered_anomalies = anomalies[anomalies["layer"].isin(filtered["layer"])] if not anomalies.empty else anomalies

    st.sidebar.divider()
    st.sidebar.download_button(
        "下载 layer_summary.csv",
        csv_bytes(summary),
        "layer_summary.csv",
        "text/csv",
        width="stretch",
    )
    st.sidebar.download_button(
        "下载 anomalies.csv",
        csv_bytes(anomalies),
        "anomalies.csv",
        "text/csv",
        width="stretch",
    )

    overview_tab, recipe_tab, optical_tab, device_tab, anomaly_tab = st.tabs(
        ["总览", "配方与层趋势", "光学分析", "设备分析", "异常与关联"]
    )

    with overview_tab:
        batch = result.batch_summary
        cols = st.columns(6)
        cols[0].metric("炉号", batch["lot_id"])
        cols[1].metric("层数", batch["layer_count"], f"H {batch['h_layers']} / L {batch['l_layers']}")
        cols[2].metric("完成状态", "已完成" if batch["finished"] else "需核验")
        cols[3].metric("累计镀膜", format_duration(batch["actual_seconds"]), f"计划 {format_duration(batch['planned_seconds'])}")
        priority_layers = anomalies.loc[anomalies["level"] == "重点复核", "layer"].nunique() if not anomalies.empty else 0
        cols[4].metric("重点复核层", int(priority_layers))
        cols[5].metric("数据质量", f"{batch['quality_errors']} 错误", f"{batch['quality_warnings']} 警告")

        if filtered.empty or not filtered["recipe_end_offset"].notna().any():
            st.warning("当前筛选条件下没有可用的终点光学数据。")
        else:
            chart = px.scatter(
                filtered,
                x="layer",
                y="recipe_end_offset",
                color="material",
                symbol="method",
                labels={"layer": "层号", "recipe_end_offset": "Meas−End T", "material": "材料", "method": "终止方式"},
                title="原始配方终点偏移概览",
            )
            chart.update_yaxes(tickformat=".2%")
            st.plotly_chart(chart, width="stretch")

        st.subheader("优先复核")
        if filtered_anomalies.empty:
            st.success("当前阈值和筛选条件下未发现统计异常。")
        else:
            attention = filtered_anomalies.assign(
                指标=filtered_anomalies["metric"].map(METRIC_LABELS).fillna(filtered_anomalies["metric"]),
                绝对Z=filtered_anomalies["robust_z"].abs(),
            )
            st.dataframe(
                attention[["layer", "material", "method", "指标", "value", "level", "绝对Z", "reason"]].head(30),
                width="stretch",
                hide_index=True,
            )

        with st.expander("数据质量与忽略字段", expanded=batch["quality_errors"] > 0):
            if batch["ignored_date_csvs"]:
                st.write("已忽略日期主 CSV：", "、".join(batch["ignored_date_csvs"]))
            else:
                st.write("当前目录未发现 YYYY-MM-DD.csv；发现时会自动忽略。")
            st.write(
                f"日志消息 {result.events['message_count']:,} 条；执行层 {result.events['coating_sequence_count']}；"
                f"完成标志 {result.events['finished_count']}；错误关键词 {result.events['error_like_count']}。"
            )
            if result.data_quality.empty:
                st.success("未发现结构或关联错误。")
            else:
                st.dataframe(result.data_quality, width="stretch", hide_index=True)
            if not result.constant_fields.empty:
                st.markdown("**全炉恒定、默认不绘图的字段**")
                st.dataframe(result.constant_fields, width="stretch", hide_index=True)

    with recipe_tab:
        if filtered.empty:
            st.warning("当前筛选条件下没有层数据。")
        else:
            strip = px.scatter(
                filtered,
                x="layer",
                y="material",
                color="material",
                symbol="method",
                labels={"layer": "层号", "material": "材料", "method": "终止方式"},
                title="材料与终止方式",
            )
            strip.update_traces(marker={"size": 8})
            st.plotly_chart(strip, width="stretch")
            left, right = st.columns(2)
            with left:
                fig = px.line(filtered, x="layer", y="phy_thick", color="material", markers=True, labels={"layer": "层号", "phy_thick": "物理厚度", "material": "材料"})
                st.plotly_chart(fig, width="stretch")
                fig = px.line(filtered, x="layer", y=["recipe_rate", "actual_rate"], labels={"layer": "层号", "value": "速率", "variable": "系列"})
                fig.for_each_trace(lambda trace: trace.update(name=METRIC_LABELS.get(trace.name, trace.name)))
                st.plotly_chart(fig, width="stretch")
            with right:
                fig = px.line(filtered, x="layer", y=["planned_time", "actual_time"], labels={"layer": "层号", "value": "时间 (s)", "variable": "系列"})
                fig.for_each_trace(lambda trace: trace.update(name=METRIC_LABELS.get(trace.name, trace.name)))
                st.plotly_chart(fig, width="stretch")
                fig = px.scatter(filtered, x="layer", y="time_delta", color="material", symbol="method", labels={"layer": "层号", "time_delta": "实际−计划时间 (s)", "material": "材料", "method": "终止方式"})
                st.plotly_chart(fig, width="stretch")

    with optical_tab:
        if filtered.empty or not filtered["final_meas"].notna().any():
            st.warning("当前筛选条件下没有可用的光学数据，请查看数据质量信息。")
        else:
            endpoint = filtered.melt(
                id_vars=["layer", "material", "method"],
                value_vars=["final_meas", "final_calc", "end_t"],
                var_name="series",
                value_name="transmittance",
            )
            endpoint["series"] = endpoint["series"].map(METRIC_LABELS)
            fig = px.line(endpoint, x="layer", y="transmittance", color="series", hover_data=["material", "method"], labels={"layer": "层号", "transmittance": "透过率", "series": "系列"}, title="终点透过率：实测、动态计算与原始配方")
            fig.update_yaxes(tickformat=".1%")
            st.plotly_chart(fig, width="stretch")

            left, right = st.columns(2)
            with left:
                hidden_metrics = set(result.batch_summary["hidden_summary_metrics"])
                residual_choices = [metric for metric in ["fit_end_residual", "recipe_end_offset", "fit_mae", "fit_p95_abs", "fit_max_abs"] if metric not in hidden_metrics]
                if residual_choices:
                    residual_metric = st.selectbox("残差指标", residual_choices, format_func=lambda value: METRIC_LABELS[value])
                    fig = px.scatter(filtered, x="layer", y=residual_metric, color="material", symbol="method", labels={"layer": "层号", residual_metric: METRIC_LABELS[residual_metric], "material": "材料", "method": "终止方式"})
                    fig.update_yaxes(tickformat=".2%")
                    st.plotly_chart(fig, width="stretch")
                else:
                    st.info("当前筛选下残差指标无变化。")
            with right:
                signal_choices = [metric for metric in ["signal_median", "signal_std", "signal_cv"] if metric not in hidden_metrics]
                if signal_choices:
                    signal_metric = st.selectbox("信号指标", signal_choices, format_func=lambda value: METRIC_LABELS[value])
                    fig = px.scatter(filtered, x="layer", y=signal_metric, color="material", symbol="method", labels={"layer": "层号", signal_metric: METRIC_LABELS[signal_metric], "material": "材料", "method": "终止方式"})
                    st.plotly_chart(fig, width="stretch")
                else:
                    st.info("当前筛选下信号指标无变化。")

            st.subheader("单层详情")
            selected_layer = st.selectbox("层号", filtered["layer"].astype(int).tolist())
            detail = cached_layer(path, int(selected_layer), fingerprint)
            meas = detail["meas"]
            curve = go.Figure()
            curve.add_trace(go.Scatter(x=meas["SamTime"], y=meas["MeasVal(1)"], name="Meas", mode="lines"))
            curve.add_trace(go.Scatter(x=meas["SamTime"], y=meas["CalcVal(1)"], name="动态 Calc", mode="lines"))
            curve.update_layout(title=f"第 {selected_layer} 层实测与动态计算", xaxis_title="采样时间 (s)", yaxis_title="透过率")
            curve.update_yaxes(tickformat=".2%")
            st.plotly_chart(curve, width="stretch")
            detail_left, detail_right = st.columns(2)
            with detail_left:
                calc = detail["calc"]
                if not calc.empty:
                    fig = px.line(calc, x="thickness", y="calculated_t", labels={"thickness": "厚度", "calculated_t": "理论透过率"}, title="理论厚度—透过率曲线")
                    fig.update_yaxes(tickformat=".2%")
                    st.plotly_chart(fig, width="stretch")
            with detail_right:
                if detail["image_path"] and Path(detail["image_path"]).is_file():
                    st.image(detail["image_path"], caption=f"第 {selected_layer} 层原始截图", width="stretch")
                else:
                    st.info("该层没有截图。")

    with device_tab:
        hidden_metrics = set(result.batch_summary["hidden_summary_metrics"])
        available = [(mean, std) for mean, std in DEVICE_CHOICES if mean not in hidden_metrics and mean in filtered and filtered[mean].notna().any()]
        if not available or filtered.empty:
            st.warning("当前筛选条件下没有设备数据。")
        else:
            selected_metric = st.selectbox("设备指标", [item[0] for item in available], format_func=lambda value: METRIC_LABELS[value])
            std_metric = next(std for mean, std in available if mean == selected_metric)
            error_column = std_metric if std_metric and std_metric in filtered and filtered[std_metric].notna().any() else None
            fig = px.scatter(
                filtered,
                x="layer",
                y=selected_metric,
                color="material",
                symbol="method",
                error_y=error_column,
                labels={"layer": "层号", selected_metric: METRIC_LABELS[selected_metric], "material": "材料", "method": "终止方式"},
                title=f"{METRIC_LABELS[selected_metric]}逐层趋势",
            )
            fig.update_traces(mode="lines+markers")
            st.plotly_chart(fig, width="stretch")
            material_stats = filtered.groupby("material")[selected_metric].agg(["count", "mean", "std", "min", "max"]).reset_index()
            st.dataframe(material_stats, width="stretch", hide_index=True)

    with anomaly_tab:
        st.caption("统计异常只表示相对同类层偏离；相关关系用于寻找线索，不代表因果。")
        if filtered_anomalies.empty:
            st.success("当前阈值和筛选条件下未发现统计异常。")
        else:
            table = filtered_anomalies.copy()
            table.insert(4, "metric_label", table["metric"].map(METRIC_LABELS).fillna(table["metric"]))
            st.dataframe(table, width="stretch", hide_index=True)
            metric = st.selectbox("查看异常指标", sorted(table["metric"].unique()), format_func=lambda value: METRIC_LABELS.get(value, value))
            metric_anomalies = table[table["metric"] == metric]
            fig = px.scatter(filtered, x="layer", y=metric, color="material", symbol="method", labels={"layer": "层号", metric: METRIC_LABELS.get(metric, metric), "material": "材料", "method": "终止方式"})
            fig.add_trace(
                go.Scatter(
                    x=metric_anomalies["layer"],
                    y=metric_anomalies["value"],
                    mode="markers",
                    name="异常",
                    marker={"color": "red", "size": 13, "symbol": "circle-open", "line": {"width": 2}},
                )
            )
            st.plotly_chart(fig, width="stretch")

        correlations = compute_correlations(filtered)
        st.subheader("光学指标与工艺参数的 Spearman 相关")
        if correlations.empty:
            st.info("有效样本不足或当前筛选指标恒定，无法计算相关关系。")
        else:
            correlations = correlations.assign(
                关系=correlations["target"].map(METRIC_LABELS) + " ← " + correlations["driver"].map(METRIC_LABELS)
            )
            fig = px.bar(correlations.sort_values("abs_spearman"), x="abs_spearman", y="关系", color="material", orientation="h", hover_data=["spearman", "samples"], labels={"abs_spearman": "|Spearman ρ|", "material": "材料"})
            st.plotly_chart(fig, width="stretch")
            st.dataframe(correlations, width="stretch", hide_index=True)


if __name__ == "__main__":
    main()
