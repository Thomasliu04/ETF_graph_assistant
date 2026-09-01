import json
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from scripts.config import AppConfig
from scripts.data_calc import ETFDataCalculator
from scripts.pipeline import (
    DEFAULT_AGG_NAMES,
    build_run_context,
    compute_tables,
    convert_xlsx,
    format_user_error,
    run_ai_with_review,
)
from scripts.contracts import default_agg_names, get_load_info, plugin_catalog_rows
from scripts.report_display import prepare_report_for_reading
from scripts.report_sections import SECTION_KEYS, SECTION_TITLES, split_sections
from scripts.review_ai import extract_review_payload
from scripts.run_context import RunContext
from scripts.visual_plot import ETFVisualizer


CONFIG = AppConfig()
PROJECT_ROOT = CONFIG.project_root
RESULT_DIR = CONFIG.result_dir
UPLOAD_DIR = CONFIG.data_dir / "uploads"
AGG_FILE = RESULT_DIR / "ETF聚合汇总表.xlsx"
REPORT_FILE = RESULT_DIR / "AI数据分析报告第一版测试.md"
REVIEW_FILE = RESULT_DIR / "AI审核报告.md"


def active_agg_names() -> list[str]:
    try:
        return default_agg_names()
    except Exception:
        return list(DEFAULT_AGG_NAMES)

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


LOOP_MODE_LABELS = {
    "generate": "全文生成+全量审核",
    "section_revise": "章节局部改写+增量复审",
    "full_revise": "全文反馈改写+增量复审",
    "early_stop_no_gain": "分数增益不足，提前停止",
}


def init_state():
    st.session_state.setdefault("source_xlsx_path", str(CONFIG.xlsx_path))
    st.session_state.setdefault("csv_path", str(CONFIG.csv_path))
    st.session_state.setdefault("agg_tables", None)
    st.session_state.setdefault("report_text", None)
    st.session_state.setdefault("review_text", None)
    st.session_state.setdefault("review_score", None)
    st.session_state.setdefault("ai_loop_log", None)
    st.session_state.setdefault("failed_sections", None)
    st.session_state.setdefault("active_run_id", None)
    st.session_state.setdefault("active_run_dir", None)


def clear_ai_session_outputs() -> None:
    st.session_state["report_text"] = None
    st.session_state["review_text"] = None
    st.session_state["review_score"] = None
    st.session_state["ai_loop_log"] = None
    st.session_state["failed_sections"] = None


def sync_ai_session_from_run(run_context: RunContext | None, report=None, review=None, score=None) -> None:
    """把 pipeline / run_manifest 中的 AI 结果写入 session。"""
    if report is not None:
        st.session_state["report_text"] = report
    if review is not None:
        st.session_state["review_text"] = review
    if score is not None or report is not None:
        st.session_state["review_score"] = score

    if run_context is None:
        return
    manifest = run_context.manifest or {}
    st.session_state["ai_loop_log"] = manifest.get("ai_loop_log") or []
    st.session_state["failed_sections"] = manifest.get("final_failed_sections") or []
    if st.session_state.get("review_score") is None and manifest.get("final_review_score") is not None:
        st.session_state["review_score"] = manifest.get("final_review_score")


def score_pass_label(score: int | None) -> str:
    if score is None:
        return "未解析"
    if score >= CONFIG.pass_score:
        return f"达标（≥{CONFIG.pass_score}）"
    return f"未达标（<{CONFIG.pass_score}）"


def safe_name(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in name)


def status_badge(ready: bool, label: str) -> str:
    status_class = "status-ok" if ready else "status-warn"
    text = "就绪" if ready else "缺失"
    return f'<span class="status-pill {status_class}">{label}: {text}</span>'


def file_ready(path: Path) -> bool:
    return path.exists()


def agg_ready() -> bool:
    """聚合表：磁盘 Excel 或本会话已算出的表，任一即可视为就绪。"""
    tables = st.session_state.get("agg_tables")
    return file_ready(AGG_FILE) or bool(tables)


def report_ready() -> bool:
    return file_ready(REPORT_FILE) or bool(st.session_state.get("report_text"))


def active_xlsx_path() -> Path:
    return Path(st.session_state["source_xlsx_path"])


def active_csv_path() -> Path:
    return Path(st.session_state["csv_path"])


def render_app_header(container=None) -> None:
    target = container if container is not None else st
    target.markdown(
        f"""
        <div class="app-header">
            <p class="app-title">ETF Graph Assistant</p>
            <p class="app-subtitle">上传底表 → 聚合导出 Excel → AI 生成与章节改写审核</p>
            <div class="status-line">
                {status_badge(file_ready(active_xlsx_path()), "Excel 底表")}
                {status_badge(file_ready(active_csv_path()), "CSV 底表")}
                {status_badge(agg_ready(), "聚合表")}
                {status_badge(report_ready(), "AI 报告")}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def create_run_context() -> RunContext:
    run_context = build_run_context(CONFIG, source_xlsx=active_xlsx_path())
    st.session_state["active_run_id"] = run_context.run_id
    st.session_state["active_run_dir"] = str(run_context.run_dir)
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
    clear_ai_session_outputs()
    st.session_state["active_run_id"] = None
    st.session_state["active_run_dir"] = None
    return target


def convert_active_source(run_context: RunContext | None = None) -> Path:
    return convert_xlsx(CONFIG, active_xlsx_path(), active_csv_path(), run_context=run_context)


def build_agg_tables(run_context: RunContext | None = None) -> dict[str, pd.DataFrame]:
    if not active_csv_path().exists():
        convert_active_source(run_context)
    tables, _excel_path = compute_tables(
        CONFIG, active_csv_path(), run_context=run_context, agg_names=active_agg_names()
    )
    return tables


def excel_download_bytes(tables: dict[str, pd.DataFrame] | None) -> bytes | None:
    if tables:
        return ETFDataCalculator.tables_to_excel_bytes(tables)
    if AGG_FILE.exists():
        return AGG_FILE.read_bytes()
    return None


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
        for col, label in zip(cols, ["区域", "赛道", "管理人", "目标公司"]):
            col.metric(label, "未计算")
        return

    area = tables["area"]
    track = tables["track"]
    manager = tables["manager"]

    cols = st.columns(4)
    cols[0].metric("区域数量", f"{len(area)}")
    cols[1].metric("赛道数量", f"{len(track)}")
    cols[2].metric("管理人数量", f"{len(manager)}")
    if "target_summary" in tables and not tables["target_summary"].empty:
        summary = tables["target_summary"].iloc[0]
        cols[3].metric(
            CONFIG.target_company,
            f"{summary['规模增量']:.2f} 亿",
            f"增速 {summary['规模增速'] * 100:.1f}%" if pd.notna(summary["规模增速"]) else None,
        )
    else:
        cols[3].metric("目标公司", "未匹配")

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

    tab_defs = [
        ("区域", "area"),
        ("赛道", "track"),
        ("管理人", "manager"),
        ("国家队", "national_team"),
        ("目标公司总览", "target_summary"),
        ("目标公司区域", "target_by_area"),
        ("目标公司赛道", "target_by_track"),
        ("目标公司梯队", "target_top_bottom"),
    ]
    available = [(label, key) for label, key in tab_defs if key in tables]
    tabs = st.tabs([label for label, _ in available])
    for tab, (_, key) in zip(tabs, available):
        with tab:
            st.dataframe(tables[key], use_container_width=True, hide_index=True)


def render_charts(tables: dict[str, pd.DataFrame] | None):
    st.info(
        "图表仅为可选预览，不是主交付物。建议下载「ETF聚合汇总表.xlsx」后，"
        "用 Excel 自带图表功能按需调整。"
    )
    if not tables:
        st.caption("请先完成聚合计算。")
        return
    if st.button("生成简易预览图"):
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


def render_markdown_block(text: str) -> None:
    st.markdown(text)


def render_report(report_text: str | None, *, use_tabs: bool = True):
    text = report_text
    if not text and REPORT_FILE.exists():
        text = REPORT_FILE.read_text(encoding="utf-8")
    if not text:
        st.info("尚未生成 AI 分析报告。")
        return

    show_citations = st.toggle(
        "显示行内出处（来源：…）",
        value=False,
        key=f"show_citations_{'tabs' if use_tabs else 'hist'}",
        help="默认隐藏出处以方便阅读；出处仍保留在下方列表与原始下载文件中。",
    )

    if show_citations:
        display_text = text
        citations: list[str] = []
    else:
        display_text, citations = prepare_report_for_reading(text)

    parts = split_sections(display_text)
    has_sections = any(key in parts for key in SECTION_KEYS)

    def _render_body(body: str) -> None:
        render_markdown_block(body)

    if not has_sections:
        _render_body(display_text)
    elif not use_tabs:
        _render_body(display_text)
        for key in SECTION_KEYS:
            if key not in parts:
                continue
            with st.expander(SECTION_TITLES[key], expanded=False):
                _render_body(parts[key])
    else:
        labels = ["全文"]
        keys: list[str | None] = [None]
        for key in SECTION_KEYS:
            if key in parts:
                labels.append(SECTION_TITLES[key])
                keys.append(key)
        if parts.get("preamble"):
            labels.append("前言")
            keys.append("preamble")

        tabs = st.tabs(labels)
        for tab, key in zip(tabs, keys):
            with tab:
                if key is None:
                    _render_body(display_text)
                else:
                    _render_body(parts.get(key) or "")

    if not show_citations:
        with st.expander(f"证据出处（{len(citations)}）", expanded=False):
            if not citations:
                st.caption("未识别到「来源：…」标注。")
            else:
                for i, cite in enumerate(citations, start=1):
                    st.markdown(f"{i}. `{cite}`")
        st.caption("百分比已尽量格式化为 xx%；原始带出处全文可在左侧下载。")


def render_loop_log(loop_log: list | None, *, failed_sections: list | None = None):
    st.markdown('<p class="section-label">生成-审核 Loop</p>', unsafe_allow_html=True)
    score = st.session_state.get("review_score")
    cols = st.columns(4)
    cols[0].metric("审核得分", "—" if score is None else str(score))
    cols[1].metric("达标判定", score_pass_label(score))
    cols[2].metric("改写上限", str(CONFIG.max_revise_rounds))
    cols[3].metric("达标线", str(CONFIG.pass_score))

    if failed_sections:
        st.caption("最终仍标记的失败章节：" + "、".join(failed_sections))

    if not loop_log:
        st.caption("暂无 loop 记录。完成 AI 生成后会显示各轮模式与分数。")
        return

    rows = []
    for item in loop_log:
        mode = item.get("mode", "")
        rows.append(
            {
                "轮次": item.get("attempt", ""),
                "模式": LOOP_MODE_LABELS.get(mode, mode),
                "得分": item.get("score", ""),
                "失败章节": "、".join(item.get("failed_sections") or []) or "—",
                "JSON解析": "是" if item.get("parse_ok") else ("—" if mode == "early_stop_no_gain" else "否"),
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def render_review_panel(review_text: str | None):
    text = review_text
    if not text and REVIEW_FILE.exists():
        text = REVIEW_FILE.read_text(encoding="utf-8")
    if not text:
        st.info("尚未生成审核报告。")
        return

    payload = extract_review_payload(text)
    summary_cols = st.columns(3)
    summary_cols[0].metric("解析得分", "—" if payload.get("score") is None else str(payload["score"]))
    summary_cols[1].metric("失败章节数", str(len(payload.get("failed_sections") or [])))
    summary_cols[2].metric("错误条数", str(len(payload.get("errors") or [])))

    failed = payload.get("failed_sections") or []
    if failed:
        st.caption("失败章节：" + "、".join(failed))
    instructions = (payload.get("rewrite_instructions") or "").strip()
    if instructions:
        st.info(f"重写指令：{instructions}")

    errors = payload.get("errors") or []
    if errors:
        with st.expander(f"结构化错误清单（{len(errors)}）", expanded=False):
            err_rows = []
            for err in errors:
                if not isinstance(err, dict):
                    continue
                err_rows.append(
                    {
                        "章节": err.get("section", ""),
                        "类型": err.get("type", ""),
                        "原文": err.get("quote", ""),
                        "证据": err.get("evidence", ""),
                        "修正": err.get("fix", ""),
                    }
                )
            if err_rows:
                st.dataframe(pd.DataFrame(err_rows), use_container_width=True, hide_index=True)

    st.markdown(text)


def render_history():
    runs = list_runs()
    if not runs:
        st.info("尚无历史运行。")
        return

    labels = []
    for run in runs:
        manifest = load_manifest(run)
        created_at = manifest.get("created_at", run.name)
        score = manifest.get("final_review_score", "")
        score_part = f"  |  得分 {score}" if score != "" and score is not None else ""
        labels.append(f"{run.name}  |  {created_at}{score_part}")

    selected_label = st.selectbox("历史运行", labels)
    selected_run = runs[labels.index(selected_label)]
    manifest = load_manifest(selected_run)

    st.markdown('<p class="section-label">运行信息</p>', unsafe_allow_html=True)
    cfg = manifest.get("config") or {}
    info = pd.DataFrame(
        [
            {"项目": "run_id", "值": selected_run.name},
            {"项目": "created_at", "值": manifest.get("created_at", "")},
            {"项目": "git_commit", "值": manifest.get("git_commit", "")},
            {"项目": "final_review_score", "值": manifest.get("final_review_score", "")},
            {
                "项目": "final_failed_sections",
                "值": "、".join(manifest.get("final_failed_sections") or []) or "—",
            },
            {"项目": "pass_score", "值": cfg.get("pass_score", "")},
            {"项目": "max_revise_rounds", "值": cfg.get("max_revise_rounds", "")},
            {"项目": "min_score_gain", "值": cfg.get("min_score_gain", "")},
        ]
    )
    st.dataframe(info, use_container_width=True, hide_index=True)

    loop_log = manifest.get("ai_loop_log") or []
    if loop_log:
        st.markdown('<p class="section-label">本次 Loop 轨迹</p>', unsafe_allow_html=True)
        loop_rows = []
        for item in loop_log:
            mode = item.get("mode", "")
            loop_rows.append(
                {
                    "轮次": item.get("attempt", ""),
                    "模式": LOOP_MODE_LABELS.get(mode, mode),
                    "得分": item.get("score", ""),
                    "失败章节": "、".join(item.get("failed_sections") or []) or "—",
                }
            )
        st.dataframe(pd.DataFrame(loop_rows), use_container_width=True, hide_index=True)

    report_path = selected_run / "ai" / "report.md"
    review_path = selected_run / "ai" / "review.md"
    table_dir = selected_run / "tables"
    excel_path = selected_run / "ETF聚合汇总表.xlsx"

    report_tab, table_tab, review_tab, file_tab = st.tabs(["报告", "聚合表", "审核", "文件"])
    with report_tab:
        if report_path.exists():
            render_report(report_path.read_text(encoding="utf-8"), use_tabs=False)
            st.download_button("下载本次报告", report_path.read_bytes(), file_name=f"{selected_run.name}_report.md")
        else:
            st.info("该运行没有 AI 报告。")

    with table_tab:
        if excel_path.exists():
            st.download_button(
                "下载本次运行 Excel 汇总表",
                excel_path.read_bytes(),
                file_name=f"{selected_run.name}_ETF聚合汇总表.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        table_files = sorted(table_dir.glob("*.csv")) if table_dir.exists() else []
        if not table_files:
            st.info("该运行没有聚合表。")
        else:
            selected_table = st.selectbox("聚合表文件", [p.name for p in table_files])
            table_path = table_dir / selected_table
            st.dataframe(pd.read_csv(table_path, encoding="utf-8-sig"), use_container_width=True, hide_index=True)
            st.download_button("下载当前 CSV", table_path.read_bytes(), file_name=selected_table)

    with review_tab:
        if review_path.exists():
            render_review_panel(review_path.read_text(encoding="utf-8"))
            st.download_button("下载本次审核", review_path.read_bytes(), file_name=f"{selected_run.name}_review.md")
        else:
            st.info("该运行没有审核报告。")

    with file_tab:
        files = [p for p in selected_run.rglob("*") if p.is_file()]
        file_rows = [{"文件": str(p.relative_to(selected_run)), "大小": p.stat().st_size} for p in files]
        st.dataframe(pd.DataFrame(file_rows), use_container_width=True, hide_index=True)


init_state()

# 刷新页面后，尽量从当前 run 的 manifest 恢复 AI loop 展示
if st.session_state.get("active_run_dir") and not st.session_state.get("ai_loop_log"):
    try:
        run_dir = Path(st.session_state["active_run_dir"])
        manifest = load_manifest(run_dir)
        if manifest.get("ai_loop_log") is not None:
            st.session_state["ai_loop_log"] = manifest.get("ai_loop_log") or []
        if manifest.get("final_failed_sections") is not None:
            st.session_state["failed_sections"] = manifest.get("final_failed_sections") or []
        if st.session_state.get("review_score") is None and manifest.get("final_review_score") is not None:
            st.session_state["review_score"] = manifest.get("final_review_score")
        if not st.session_state.get("report_text"):
            report_path = run_dir / "ai" / "report.md"
            if report_path.exists():
                st.session_state["report_text"] = report_path.read_text(encoding="utf-8")
        if not st.session_state.get("review_text"):
            review_path = run_dir / "ai" / "review.md"
            if review_path.exists():
                st.session_state["review_text"] = review_path.read_text(encoding="utf-8")
    except Exception:
        pass

# 先占位，等侧边栏操作跑完再刷新状态灯，避免“算完了仍显示缺失”
header_slot = st.empty()
render_app_header(header_slot)

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

    one_click = st.button(
        "一键分析",
        type="primary",
        use_container_width=True,
        help="转换+聚合+导出Excel+AI生成/章节改写审核（默认不生成图表）",
    )
    convert_clicked = st.button("仅转换底表", use_container_width=True)
    calc_clicked = st.button("仅计算并导出 Excel", use_container_width=True)

    st.divider()
    st.markdown('<p class="section-label">AI 设置</p>', unsafe_allow_html=True)
    env_key = CONFIG.api_key or ""
    api_key = st.text_input("API Key", value=env_key, type="password", placeholder="读取 .env 或手动输入")
    st.text_input("模型", CONFIG.model_name, disabled=True)
    st.text_input("厂商", CONFIG.api_type, disabled=True)
    st.text_input("Base URL", CONFIG.resolved_base_url, disabled=True)
    st.caption(
        f"目标公司 {CONFIG.target_company} · timeout {CONFIG.request_timeout}s · "
        f"请求重试 {CONFIG.request_retries}"
    )
    st.caption(
        f"审核达标 {CONFIG.pass_score} 分 · 最多局部改写 {CONFIG.max_revise_rounds} 轮 · "
        f"最小增益 {CONFIG.min_score_gain}"
    )
    ai_clicked = st.button(
        "仅生成 AI 报告并审核",
        use_container_width=True,
        help="低分时按失败章节局部改写，再增量复审，直到达标或触发熔断",
    )

    st.divider()
    st.markdown('<p class="section-label">导出 Excel</p>', unsafe_allow_html=True)
    excel_bytes = excel_download_bytes(st.session_state.get("agg_tables"))
    if excel_bytes:
        st.download_button(
            "下载聚合汇总表.xlsx",
            excel_bytes,
            file_name="ETF聚合汇总表.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            type="primary",
        )
        st.caption("含目录页与全部聚合/目标公司切片，可用 Excel 自行制图。")
    else:
        st.caption("完成聚合后可在此下载多 sheet Excel。")
    if REPORT_FILE.exists():
        st.download_button("下载最新 AI 报告", REPORT_FILE.read_bytes(), file_name="AI数据分析报告.md", use_container_width=True)
    if REVIEW_FILE.exists():
        st.download_button("下载最新审核报告", REVIEW_FILE.read_bytes(), file_name="AI审核报告.md", use_container_width=True)

if one_click:
    if not active_xlsx_path().exists() and not active_csv_path().exists():
        st.warning("请先上传或放置底表文件。")
    else:
        progress = st.progress(0, text="准备开始…")
        status = st.status("正在执行一键分析…", expanded=True)
        try:
            run_context = create_run_context()
            do_ai = bool(api_key)

            # —— 阶段 1：转换 ——
            status.update(label="阶段 1/3 · 转换底表", state="running")
            status.write("① 读取 Excel / CSV，转换并校验字段")
            progress.progress(5, text="阶段 1/3 · 转换底表")
            if active_xlsx_path().exists():
                convert_xlsx(CONFIG, active_xlsx_path(), active_csv_path(), run_context=run_context)
            elif active_csv_path().exists():
                run_context.copy_input(active_csv_path())
            else:
                raise FileNotFoundError("未找到底表 Excel 或 CSV")
            status.write("✓ 底表转换完成")
            progress.progress(25, text="阶段 1/3 · 转换完成")

            # —— 阶段 2：聚合 ——
            status.update(label="阶段 2/3 · 聚合计算与导出 Excel", state="running")
            status.write("② 计算标准聚合 + 目标公司切片，并导出 Excel")
            progress.progress(35, text="阶段 2/3 · 聚合计算中")
            tables, excel_path = compute_tables(
                CONFIG,
                active_csv_path(),
                run_context=run_context,
                agg_names=active_agg_names(),
            )
            st.session_state["agg_tables"] = tables
            status.write(f"✓ 聚合完成，Excel：{excel_path.name if excel_path else '已导出'}")
            progress.progress(55, text="阶段 2/3 · 聚合完成")

            # —— 阶段 3：AI ——
            st.session_state["active_run_id"] = run_context.run_id
            st.session_state["active_run_dir"] = str(run_context.run_dir)

            if not do_ai:
                status.write("③ 未配置 API Key，跳过 AI")
                progress.progress(100, text="完成（已跳过 AI）")
                clear_ai_session_outputs()
                status.update(label="聚合与 Excel 导出完成（已跳过 AI）", state="complete")
                st.warning("未配置 API Key，已完成转换/聚合/Excel 导出；配置 Key 后可再点「一键分析」生成报告。")
            else:
                status.update(label="阶段 3/3 · AI 生成与审核", state="running")
                status.write(
                    "③ AI 子步骤："
                    "3.1 生成全文 → 3.2 全量审核 → "
                    "3.3 必要时改写 → 3.4 增量复审"
                    f"（达标≥{CONFIG.pass_score}；最多改写 {CONFIG.max_revise_rounds} 轮）"
                )
                progress.progress(60, text="阶段 3/3 · 3.1 准备生成")

                def _ai_progress(message: str, fraction: float) -> None:
                    # AI 阶段占整体 60%~98%
                    overall = 60 + int(38 * fraction)
                    progress.progress(min(overall, 98), text=f"阶段 3/3 · {message}")
                    status.write(f"… {message}")

                report, review, score = run_ai_with_review(
                    CONFIG,
                    tables,
                    api_key=api_key,
                    run_context=run_context,
                    on_progress=_ai_progress,
                )
                sync_ai_session_from_run(
                    run_context, report=report, review=review, score=score
                )
                score_text = (
                    f"审核得分 {score}（{score_pass_label(score)}）"
                    if score is not None
                    else "审核得分未解析"
                )
                loop_log = (run_context.manifest or {}).get("ai_loop_log") or []
                revise_n = sum(
                    1 for item in loop_log if item.get("mode") in {"section_revise", "full_revise"}
                )
                progress.progress(100, text=f"全部完成 · {score_text}")
                status.update(label=f"一键分析完成 · {score_text}", state="complete")
                st.success(
                    f"完成。运行ID：{run_context.run_id}，{score_text}"
                    + (f"，改写 {revise_n} 轮" if revise_n else "")
                    + "。请从左侧下载聚合汇总表.xlsx。"
                )
        except Exception as exc:
            status.update(label="一键分析失败", state="error")
            progress.progress(0, text="失败")
            st.error(format_user_error(exc))

if convert_clicked:
    if not active_xlsx_path().exists():
        st.error(f"原始文件不存在：{active_xlsx_path()}")
    else:
        try:
            run_context = create_run_context()
            with st.spinner("正在转换底表..."):
                csv_path = convert_active_source(run_context)
            st.success(f"转换完成：{csv_path}")
        except Exception as exc:
            st.error(format_user_error(exc))

if calc_clicked:
    if not active_xlsx_path().exists() and not active_csv_path().exists():
        st.warning("请先上传或放置底表文件。")
    else:
        try:
            run_context = create_run_context()
            with st.spinner("正在计算聚合表（含目标公司切片）..."):
                st.session_state["agg_tables"] = build_agg_tables(run_context)
            st.success(f"聚合计算完成。运行ID：{run_context.run_id}")
        except Exception as exc:
            st.error(format_user_error(exc))

# 操作完成后刷新顶部状态灯（同一轮即可变为“就绪”）
render_app_header(header_slot)

tables = get_agg_tables_from_state()

overview_tab, tables_tab, export_tab, charts_tab, report_tab, history_tab = st.tabs(
    ["概览", "聚合表", "导出 Excel", "图表预览", "AI 报告", "历史运行"]
)

with overview_tab:
    render_top_metrics(tables)
    overview_excel = excel_download_bytes(tables)
    if overview_excel:
        st.download_button(
            "下载 ETF聚合汇总表.xlsx",
            overview_excel,
            file_name="ETF聚合汇总表.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
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
                {"项目": "审核达标分", "值": str(CONFIG.pass_score)},
                {"项目": "最多局部改写轮数", "值": str(CONFIG.max_revise_rounds)},
                {"项目": "最小分数增益", "值": str(CONFIG.min_score_gain)},
                {"项目": "当前运行", "值": st.session_state.get("active_run_id") or ""},
            ]
        )
        st.dataframe(config_rows, use_container_width=True, hide_index=True)

        st.markdown('<p class="section-label">已加载聚合</p>', unsafe_allow_html=True)
        try:
            catalog = plugin_catalog_rows()
            info = get_load_info()
            st.caption(
                f"来源：{info.get('source', '')}"
                + (f"；警告 {len(info.get('warnings') or [])} 条" if info.get("warnings") else "")
            )
            if catalog:
                st.dataframe(pd.DataFrame(catalog), use_container_width=True, hide_index=True)
            else:
                st.caption("暂无聚合插件。")
            st.caption("新增标准聚合：编辑 configs/聚合登记表.xlsx（详见 docs/如何新增一张聚合表.md）")
        except Exception as exc:
            st.warning(f"读取聚合登记表失败：{exc}")

with tables_tab:
    render_table_tabs(tables)
    table_excel = excel_download_bytes(tables)
    if table_excel:
        st.download_button(
            "下载当前全部聚合表（Excel）",
            table_excel,
            file_name="ETF聚合汇总表.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

with export_tab:
    st.markdown('<p class="section-label">主交付物</p>', unsafe_allow_html=True)
    st.write(
        "聚合结果会导出为多工作表 Excel：首表「目录」列出各 sheet 说明，"
        "其后为区域/赛道/管理人/国家队/目标公司切片。可直接用 Excel 图表功能制图。"
    )
    export_excel = excel_download_bytes(tables)
    if export_excel:
        st.download_button(
            "下载 ETF聚合汇总表.xlsx",
            export_excel,
            file_name="ETF聚合汇总表.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
        )
        if tables:
            st.dataframe(
                ETFDataCalculator.build_excel_catalog(tables),
                use_container_width=True,
                hide_index=True,
            )
    else:
        st.info("尚未生成聚合表。请先点击「一键分析」或「仅计算并导出 Excel」。")
    if AGG_FILE.exists():
        st.caption(f"服务器落盘路径：{AGG_FILE}")

with charts_tab:
    render_charts(tables)

with report_tab:
    if ai_clicked:
        if not api_key:
            st.warning("未检测到 API Key。")
        else:
            try:
                run_context = current_run_context()
                progress = st.progress(0, text="准备 AI 阶段…")
                status = st.status("正在生成 AI 报告并审核…", expanded=True)
                if tables is None:
                    status.write("先计算聚合表…")
                    progress.progress(10, text="计算聚合表…")
                    st.session_state["agg_tables"] = build_agg_tables(run_context)
                    tables = get_agg_tables_from_state()
                    status.write("✓ 聚合表就绪")

                def _ai_progress(message: str, fraction: float) -> None:
                    progress.progress(int(100 * fraction), text=message)
                    status.write(f"… {message}")

                report, review, score = run_ai_with_review(
                    CONFIG,
                    tables,
                    api_key=api_key,
                    run_context=run_context,
                    on_progress=_ai_progress,
                )
                sync_ai_session_from_run(
                    run_context, report=report, review=review, score=score
                )
                score_text = (
                    f"审核得分 {score}（{score_pass_label(score)}）"
                    if score is not None
                    else "审核得分未解析"
                )
                progress.progress(100, text=f"完成 · {score_text}")
                status.update(label=f"AI 完成 · {score_text}", state="complete")
                st.success(f"AI 报告与审核生成完成，{score_text}。")
            except Exception as exc:
                st.error(format_user_error(exc))

    render_loop_log(
        st.session_state.get("ai_loop_log"),
        failed_sections=st.session_state.get("failed_sections"),
    )

    report_view, review_view = st.tabs(["报告", "审核"])
    with report_view:
        render_report(st.session_state.get("report_text"))
    with review_view:
        render_review_panel(st.session_state.get("review_text"))

with history_tab:
    render_history()
