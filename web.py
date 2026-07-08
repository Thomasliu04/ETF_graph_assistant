import json
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from scripts.ai_analyst import ETFAIAnalyst
from scripts.config import AppConfig
from scripts.data_calc import ETFDataCalculator
from scripts.review_ai import AIReviewer
from scripts.run_context import RunContext
from scripts.visual_plot import ETFVisualizer


CONFIG = AppConfig()
PROJECT_ROOT = CONFIG.project_root
RESULT_DIR = CONFIG.result_dir
UPLOAD_DIR = CONFIG.data_dir / "uploads"
AGG_FILE = RESULT_DIR / "ETF聚合汇总表.xlsx"
REPORT_FILE = RESULT_DIR / "AI数据分析报告第一版测试.md"
REVIEW_FILE = RESULT_DIR / "AI审核报告.md"
AGG_NAMES = ["area", "track", "manager", "national_team"]

os.makedirs(RESULT_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)


st.set_page_config(
    page_title="ETF Graph Assistant",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    :root {
        --border: #d8dee9;
        --text-muted: #667085;
        --danger: #b42318;
        --ok: #067647;
    }
    .block-container {
        padding-top: 1.2rem;
        padding-bottom: 2rem;
        max-width: 1500px;
    }
    h1, h2, h3 { letter-spacing: 0; }
    div[data-testid="stMetric"] {
        background: #fff;
        border: 1px solid var(--border);
        border-radius: 8px;
        padding: 12px 14px;
        min-height: 94px;
    }
    div[data-testid="stMetricLabel"] p {
        color: var(--text-muted);
        font-size: 0.82rem;
    }
    div[data-testid="stMetricValue"] { font-size: 1.35rem; }
    section[data-testid="stSidebar"] { border-right: 1px solid var(--border); }
    .app-header {
        border-bottom: 1px solid var(--border);
        padding-bottom: 0.8rem;
        margin-bottom: 1rem;
    }
    .app-title {
        font-size: 1.75rem;
        font-weight: 700;
        margin: 0;
    }
    .app-subtitle {
        color: var(--text-muted);
        margin-top: 0.25rem;
        font-size: 0.92rem;
    }
    .status-line {
        display: flex;
        gap: 10px;
        flex-wrap: wrap;
        margin-top: 0.7rem;
    }
    .status-pill {
        border: 1px solid var(--border);
        border-radius: 999px;
        padding: 4px 10px;
        background: #fff;
        color: #344054;
        font-size: 0.8rem;
        white-space: nowrap;
    }
    .status-ok {
        border-color: #a6d8bd;
        color: var(--ok);
        background: #f0f9f4;
    }
    .status-warn {
        border-color: #f3c7c2;
        color: var(--danger);
        background: #fff4f2;
    }
    .section-label {
        color: var(--text-muted);
        text-transform: uppercase;
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.06em;
        margin: 0 0 0.35rem 0;
    }
    .stButton > button, .stDownloadButton > button {
        border-radius: 6px;
        min-height: 38px;
        font-weight: 600;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def init_state():
    st.session_state.setdefault("source_xlsx_path", str(CONFIG.xlsx_path))
    st.session_state.setdefault("csv_path", str(CONFIG.csv_path))
    st.session_state.setdefault("agg_tables", None)
    st.session_state.setdefault("report_text", None)
    st.session_state.setdefault("review_text", None)
    st.session_state.setdefault("active_run_id", None)
    st.session_state.setdefault("active_run_dir", None)


def safe_name(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in name)


def file_status(path: Path) -> str:
    return "就绪" if path.exists() else "缺失"


def file_badge(path: Path, label: str) -> str:
    status_class = "status-ok" if path.exists() else "status-warn"
    return f'<span class="status-pill {status_class}">{label}: {file_status(path)}</span>'


def active_xlsx_path() -> Path:
    return Path(st.session_state["source_xlsx_path"])


def active_csv_path() -> Path:
    return Path(st.session_state["csv_path"])


def create_run_context() -> RunContext:
    run_context = RunContext(CONFIG.run_dir)
    st.session_state["active_run_id"] = run_context.run_id
    st.session_state["active_run_dir"] = str(run_context.run_dir)
    run_context.record_value(
        "config",
        {
            "source_xlsx_path": str(active_xlsx_path()),
            "sheet_name": CONFIG.sheet_name,
            "period_start": CONFIG.period_start,
            "period_end": CONFIG.period_end,
            "target_company": CONFIG.target_company,
            "model_name": CONFIG.model_name,
            "base_url": CONFIG.base_url,
            "request_timeout": CONFIG.request_timeout,
            "request_retries": CONFIG.request_retries,
        },
    )
    return run_context


def current_run_context() -> RunContext:
    run_dir = st.session_state.get("active_run_dir")
    if not run_dir:
        return create_run_context()
    run_path = Path(run_dir)
    if not run_path.exists():
        return create_run_context()
    return RunContext(CONFIG.run_dir, run_id=run_path.name)


def save_uploaded_file(uploaded_file) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = UPLOAD_DIR / f"{timestamp}_{safe_name(uploaded_file.name)}"
    target.write_bytes(uploaded_file.getbuffer())
    st.session_state["source_xlsx_path"] = str(target)
    st.session_state["csv_path"] = str(target.with_suffix(".csv"))
    st.session_state["agg_tables"] = None
    st.session_state["report_text"] = None
    st.session_state["review_text"] = None
    st.session_state["active_run_id"] = None
    st.session_state["active_run_dir"] = None
    return target


def convert_active_source(run_context: RunContext | None = None) -> Path:
    xlsx_path = active_xlsx_path()
    csv_path = active_csv_path()
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    ETFDataCalculator.xlsx_to_csv(xlsx_path, csv_path, sheet_name=CONFIG.sheet_name)
    if run_context:
        run_context.copy_input(xlsx_path)
        run_context.copy_input(csv_path)
    return csv_path


def build_agg_tables(run_context: RunContext | None = None) -> dict[str, pd.DataFrame]:
    if not active_csv_path().exists():
        convert_active_source(run_context)
    calc = ETFDataCalculator(base_csv_path=str(active_csv_path()), run_context=run_context)
    tables = calc.calc_registered_aggs(AGG_NAMES)
    calc.export_agg_tables(tables)
    return tables


def get_agg_tables_from_state() -> dict[str, pd.DataFrame] | None:
    return st.session_state.get("agg_tables")


def load_preview(path: Path, rows: int = 20) -> pd.DataFrame | None:
    if not path.exists():
        return None
    return pd.read_csv(path, encoding="utf-8-sig").head(rows)


def list_runs() -> list[Path]:
    if not CONFIG.run_dir.exists():
        return []
    runs = [p for p in CONFIG.run_dir.iterdir() if p.is_dir()]
    return sorted(runs, key=lambda p: p.stat().st_mtime, reverse=True)


def load_manifest(run_dir: Path) -> dict:
    path = run_dir / "run_manifest.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def render_top_metrics(tables: dict[str, pd.DataFrame] | None):
    if not tables:
        cols = st.columns(4)
        for col, label in zip(cols, ["区域", "赛道", "管理人", "国家队"]):
            col.metric(label, "未计算")
        return

    area = tables["area"]
    track = tables["track"]
    manager = tables["manager"]
    national_team = tables["national_team"]

    cols = st.columns(4)
    cols[0].metric("区域数量", f"{len(area)}")
    cols[1].metric("赛道数量", f"{len(track)}")
    cols[2].metric("管理人数量", f"{len(manager)}")
    cols[3].metric("国家队分类", f"{len(national_team)}")

    cols = st.columns(4)
    top_area = area.iloc[0]
    top_track = track.iloc[0]
    top_manager = manager.iloc[0]
    total_end_size = area["期末规模"].sum()
    cols[0].metric("最大区域增量", f"{top_area['规模增量']:.2f} 亿", top_area["区域类型"])
    cols[1].metric("最大赛道增量", f"{top_track['规模增量']:.2f} 亿", top_track["赛道类型"])
    cols[2].metric("最大管理人增量", f"{top_manager['规模增量']:.2f} 亿", top_manager["管理人"])
    cols[3].metric("期末总规模", f"{total_end_size:.2f} 亿")


def render_table_tabs(tables: dict[str, pd.DataFrame] | None):
    if not tables:
        st.info("尚未生成聚合表。")
        return

    tab_area, tab_track, tab_manager, tab_national = st.tabs(["区域", "赛道", "管理人", "国家队"])
    with tab_area:
        st.dataframe(tables["area"], use_container_width=True, hide_index=True)
    with tab_track:
        st.dataframe(tables["track"], use_container_width=True, hide_index=True)
    with tab_manager:
        st.dataframe(tables["manager"], use_container_width=True, hide_index=True)
    with tab_national:
        st.dataframe(tables["national_team"], use_container_width=True, hide_index=True)


def render_charts(tables: dict[str, pd.DataFrame] | None):
    if not tables:
        st.info("尚未生成聚合表。")
        return

    plotter = ETFVisualizer(save_dir=CONFIG.output_dir)
    fig_area = plotter.plot_area_increment(tables["area"])
    fig_track = plotter.plot_track_top10(tables["track"])
    fig_manager = plotter.plot_manager_top20(tables["manager"])

    top, bottom = st.columns([1, 1])
    with top:
        st.pyplot(fig_area, use_container_width=True)
    with bottom:
        st.pyplot(fig_track, use_container_width=True)
    st.pyplot(fig_manager, use_container_width=True)


def render_report(report_text: str | None):
    if report_text:
        st.markdown(report_text)
    elif REPORT_FILE.exists():
        st.markdown(REPORT_FILE.read_text(encoding="utf-8"))
    else:
        st.info("尚未生成 AI 分析报告。")


def render_history():
    runs = list_runs()
    if not runs:
        st.info("尚无历史运行。")
        return

    labels = []
    for run in runs:
        manifest = load_manifest(run)
        created_at = manifest.get("created_at", run.name)
        labels.append(f"{run.name}  |  {created_at}")

    selected_label = st.selectbox("历史运行", labels)
    selected_run = runs[labels.index(selected_label)]
    manifest = load_manifest(selected_run)

    st.markdown('<p class="section-label">运行信息</p>', unsafe_allow_html=True)
    info = pd.DataFrame(
        [
            {"项目": "run_id", "值": selected_run.name},
            {"项目": "created_at", "值": manifest.get("created_at", "")},
            {"项目": "git_commit", "值": manifest.get("git_commit", "")},
            {"项目": "final_review_score", "值": manifest.get("final_review_score", "")},
        ]
    )
    st.dataframe(info, use_container_width=True, hide_index=True)

    report_path = selected_run / "ai" / "report.md"
    review_path = selected_run / "ai" / "review.md"
    table_dir = selected_run / "tables"

    report_tab, table_tab, review_tab, file_tab = st.tabs(["报告", "聚合表", "审核", "文件"])
    with report_tab:
        if report_path.exists():
            st.markdown(report_path.read_text(encoding="utf-8"))
            st.download_button("下载本次报告", report_path.read_bytes(), file_name=f"{selected_run.name}_report.md")
        else:
            st.info("该运行没有 AI 报告。")

    with table_tab:
        table_files = sorted(table_dir.glob("*.csv")) if table_dir.exists() else []
        if not table_files:
            st.info("该运行没有聚合表。")
        else:
            selected_table = st.selectbox("聚合表文件", [p.name for p in table_files])
            table_path = table_dir / selected_table
            st.dataframe(pd.read_csv(table_path, encoding="utf-8-sig"), use_container_width=True, hide_index=True)
            st.download_button("下载当前聚合表", table_path.read_bytes(), file_name=selected_table)

    with review_tab:
        if review_path.exists():
            st.markdown(review_path.read_text(encoding="utf-8"))
            st.download_button("下载本次审核", review_path.read_bytes(), file_name=f"{selected_run.name}_review.md")
        else:
            st.info("该运行没有审核报告。")

    with file_tab:
        files = [p for p in selected_run.rglob("*") if p.is_file()]
        file_rows = [{"文件": str(p.relative_to(selected_run)), "大小": p.stat().st_size} for p in files]
        st.dataframe(pd.DataFrame(file_rows), use_container_width=True, hide_index=True)


init_state()

st.markdown(
    f"""
    <div class="app-header">
        <p class="app-title">ETF Graph Assistant</p>
        <p class="app-subtitle">ETF 底表计算、聚合可视化与 AI 研报生成</p>
        <div class="status-line">
            {file_badge(active_xlsx_path(), "Excel 底表")}
            {file_badge(active_csv_path(), "CSV 底表")}
            {file_badge(AGG_FILE, "聚合表")}
            {file_badge(REPORT_FILE, "AI 报告")}
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown('<p class="section-label">数据源</p>', unsafe_allow_html=True)
    uploaded_file = st.file_uploader("上传底表", type=["xlsx"])
    if uploaded_file is not None:
        upload_key = f"{uploaded_file.name}:{uploaded_file.size}"
        if st.session_state.get("upload_key") != upload_key:
            saved_path = save_uploaded_file(uploaded_file)
            st.session_state["upload_key"] = upload_key
            st.success(f"已上传：{saved_path.name}")

    st.text_input("当前 Excel", str(active_xlsx_path()), disabled=True)
    st.text_input("当前 CSV", str(active_csv_path()), disabled=True)

    convert_clicked = st.button("转换底表", use_container_width=True)
    calc_clicked = st.button("计算聚合表", type="primary", use_container_width=True)

    st.divider()
    st.markdown('<p class="section-label">AI 设置</p>', unsafe_allow_html=True)
    env_key = CONFIG.api_key or ""
    api_key = st.text_input("API Key", value=env_key, type="password", placeholder="读取 .env 或手动输入")
    st.text_input("模型", CONFIG.model_name, disabled=True)
    st.text_input("Base URL", CONFIG.base_url, disabled=True)
    st.caption(f"timeout {CONFIG.request_timeout}s / retries {CONFIG.request_retries}")
    ai_clicked = st.button("生成 AI 报告并审核", use_container_width=True)

    st.divider()
    st.markdown('<p class="section-label">导出</p>', unsafe_allow_html=True)
    if AGG_FILE.exists():
        st.download_button("下载最新聚合表", AGG_FILE.read_bytes(), file_name="ETF聚合汇总表.xlsx", use_container_width=True)
    if REPORT_FILE.exists():
        st.download_button("下载最新 AI 报告", REPORT_FILE.read_bytes(), file_name="AI数据分析报告.md", use_container_width=True)
    if REVIEW_FILE.exists():
        st.download_button("下载最新审核报告", REVIEW_FILE.read_bytes(), file_name="AI审核报告.md", use_container_width=True)

if convert_clicked:
    if not active_xlsx_path().exists():
        st.error(f"原始文件不存在：{active_xlsx_path()}")
    else:
        run_context = create_run_context()
        with st.spinner("正在转换底表..."):
            csv_path = convert_active_source(run_context)
        st.success(f"转换完成：{csv_path}")

if calc_clicked:
    if not active_xlsx_path().exists() and not active_csv_path().exists():
        st.warning("请先上传或放置底表文件。")
    else:
        run_context = create_run_context()
        with st.spinner("正在计算聚合表..."):
            st.session_state["agg_tables"] = build_agg_tables(run_context)
        st.success(f"聚合计算完成。运行ID：{run_context.run_id}")

tables = get_agg_tables_from_state()

overview_tab, tables_tab, charts_tab, report_tab, history_tab = st.tabs(["概览", "聚合表", "图表", "AI 报告", "历史运行"])

with overview_tab:
    render_top_metrics(tables)
    st.divider()
    left, right = st.columns([1, 1])
    with left:
        st.markdown('<p class="section-label">底表预览</p>', unsafe_allow_html=True)
        preview = load_preview(active_csv_path())
        if preview is not None:
            st.dataframe(preview, use_container_width=True, hide_index=True)
        else:
            st.info("CSV 底表不存在。")
    with right:
        st.markdown('<p class="section-label">当前配置</p>', unsafe_allow_html=True)
        config_rows = pd.DataFrame(
            [
                {"项目": "统计区间", "值": f"{CONFIG.period_start} 至 {CONFIG.period_end}"},
                {"项目": "目标公司", "值": CONFIG.target_company},
                {"项目": "Sheet", "值": CONFIG.sheet_name},
                {"项目": "模型", "值": CONFIG.model_name},
                {"项目": "当前运行", "值": st.session_state.get("active_run_id") or ""},
            ]
        )
        st.dataframe(config_rows, use_container_width=True, hide_index=True)

with tables_tab:
    render_table_tabs(tables)

with charts_tab:
    if st.button("刷新图表"):
        if tables is None:
            run_context = current_run_context()
            st.session_state["agg_tables"] = build_agg_tables(run_context)
            tables = get_agg_tables_from_state()
    render_charts(tables)

with report_tab:
    if ai_clicked:
        if not api_key:
            st.warning("未检测到 API Key。")
        else:
            run_context = current_run_context()
            with st.spinner("正在生成 AI 报告并审核..."):
                if tables is None:
                    st.session_state["agg_tables"] = build_agg_tables(run_context)
                    tables = get_agg_tables_from_state()

                analyst = ETFAIAnalyst(
                    api_key=api_key,
                    model_name=CONFIG.model_name,
                    api_type=CONFIG.api_type,
                    base_url=CONFIG.base_url,
                    timeout=CONFIG.request_timeout,
                    max_retries=CONFIG.request_retries,
                    run_context=run_context,
                )
                reviewer = AIReviewer(
                    api_key=api_key,
                    base_url=CONFIG.base_url,
                    model_name=CONFIG.model_name,
                    timeout=CONFIG.request_timeout,
                    max_retries=CONFIG.request_retries,
                    run_context=run_context,
                )
                report = analyst.run_analysis(tables["area"], tables["track"], tables["manager"])
                review = reviewer.run_review(report, tables["area"], tables["track"], tables["manager"])
                st.session_state["report_text"] = report
                st.session_state["review_text"] = review
            st.success("AI 报告与审核生成完成。")

    report_view, review_view = st.tabs(["报告", "审核"])
    with report_view:
        render_report(st.session_state.get("report_text"))
    with review_view:
        if st.session_state.get("review_text"):
            st.markdown(st.session_state["review_text"])
        elif REVIEW_FILE.exists():
            st.markdown(REVIEW_FILE.read_text(encoding="utf-8"))
        else:
            st.info("尚未生成审核报告。")

with history_tab:
    render_history()
