"""CLI / Web 共用的分析流水线。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

try:
    from .ai_analyst import ETFAIAnalyst
    from .config import AppConfig
    from .data_calc import ETFDataCalculator
    from .review_ai import AIReviewer
    from .run_context import RunContext
    from .visual_plot import ETFVisualizer
except ImportError:
    from ai_analyst import ETFAIAnalyst
    from config import AppConfig
    from data_calc import ETFDataCalculator
    from review_ai import AIReviewer
    from run_context import RunContext
    from visual_plot import ETFVisualizer

DEFAULT_AGG_NAMES = ["area", "track", "manager", "national_team"]


@dataclass
class PipelineResult:
    run_context: RunContext
    tables: dict[str, pd.DataFrame]
    excel_path: Path | None = None
    report_text: str | None = None
    review_text: str | None = None
    review_score: int | None = None
    steps: list[str] = field(default_factory=list)
    ai_skipped_reason: str | None = None


def format_user_error(exc: Exception) -> str:
    """把技术异常转成用户可读说明。"""
    msg = str(exc).strip() or exc.__class__.__name__
    if isinstance(exc, FileNotFoundError):
        return f"找不到文件：{msg}\n请先上传或放置 ETF 底表 Excel。"
    if isinstance(exc, ValueError):
        return (
            f"数据校验或计算失败：{msg}\n"
            "请检查：1) Sheet 名是否正确；2) 必要字段是否齐全；"
            "3) 增量是否等于期末-期初，且等于新发+净值+持营；"
            "4) 目标公司名称是否能在管理人列中匹配。"
        )
    if isinstance(exc, KeyError):
        return f"缺少必要数据表或字段：{msg}"
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return f"AI 请求失败：{msg}\n请检查网络、API Key、base_url 与超时设置。"
    return f"运行失败：{msg}"


def extract_review_score(review_text: str) -> int | None:
    match = re.search(r"总分[:：]\s*(\d+)", review_text or "")
    if not match:
        return None
    return int(match.group(1))


def build_run_context(config: AppConfig, source_xlsx: Path | None = None) -> RunContext:
    run_context = RunContext(config.run_dir)
    run_context.record_value(
        "config",
        {
            "source_xlsx_path": str(source_xlsx or config.xlsx_path),
            "data_contract_version": config.data_contract_version,
            "sheet_name": config.sheet_name,
            "period_start": config.period_start,
            "period_end": config.period_end,
            "target_company": config.target_company,
            "api_type": config.api_type,
            "model_name": config.model_name,
            "base_url": config.base_url,
            "max_retry_times": config.max_retry_times,
            "request_timeout": config.request_timeout,
            "request_retries": config.request_retries,
        },
    )
    return run_context


def convert_xlsx(
    config: AppConfig,
    xlsx_path: Path,
    csv_path: Path,
    run_context: RunContext | None = None,
) -> Path:
    if not xlsx_path.exists():
        raise FileNotFoundError(str(xlsx_path))
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    ETFDataCalculator.xlsx_to_csv(xlsx_path, csv_path, sheet_name=config.sheet_name)
    if run_context:
        run_context.copy_input(xlsx_path)
        run_context.copy_input(csv_path)
    return csv_path


def compute_tables(
    config: AppConfig,
    csv_path: Path,
    run_context: RunContext | None = None,
    agg_names: list[str] | None = None,
) -> dict[str, pd.DataFrame]:
    calc = ETFDataCalculator(base_csv_path=str(csv_path), run_context=run_context)
    tables = calc.calc_analysis_tables(
        agg_names=agg_names or DEFAULT_AGG_NAMES,
        include_target_company=True,
        target_company=config.target_company,
    )
    excel_path = Path(calc.export_agg_tables(tables))
    return tables, excel_path


def generate_charts(
    config: AppConfig,
    tables: dict[str, pd.DataFrame],
    run_context: RunContext | None = None,
) -> None:
    """可选预览图；主交付物是 Excel，不建议作为默认流程。"""
    plot = ETFVisualizer(save_dir=config.output_dir, run_context=run_context)
    plot.plot_area_increment(tables["area"])
    plot.plot_track_top10(tables["track"])
    plot.plot_manager_top20(tables["manager"])


def run_ai_with_review(
    config: AppConfig,
    tables: dict[str, pd.DataFrame],
    api_key: str,
    run_context: RunContext | None = None,
) -> tuple[str, str, int | None]:
    analyst = ETFAIAnalyst(
        api_key=api_key,
        model_name=config.model_name,
        api_type=config.api_type,
        base_url=config.base_url,
        timeout=config.request_timeout,
        max_retries=config.request_retries,
        run_context=run_context,
    )
    reviewer = AIReviewer(
        api_key=api_key,
        base_url=config.base_url,
        model_name=config.model_name,
        timeout=config.request_timeout,
        max_retries=config.request_retries,
        run_context=run_context,
    )

    retry_count = 0
    final_report = ""
    final_review = ""
    review_score: int | None = None

    while retry_count <= config.max_retry_times:
        final_report = analyst.run_analysis(tables)
        final_review = reviewer.run_review(final_report, tables)
        review_score = extract_review_score(final_review)

        if review_score is None:
            # 解析失败：允许有限次重跑，避免静默给 50 分
            if retry_count < config.max_retry_times:
                retry_count += 1
                continue
            break

        if review_score >= 80:
            break
        if retry_count < config.max_retry_times:
            retry_count += 1
            continue
        break

    if run_context is not None and review_score is not None:
        run_context.record_value("final_review_score", review_score)
    return final_report, final_review, review_score


def run_full_pipeline(
    config: AppConfig,
    xlsx_path: Path | None = None,
    csv_path: Path | None = None,
    api_key: str | None = None,
    run_ai: bool = True,
    run_charts: bool = False,
    run_context: RunContext | None = None,
) -> PipelineResult:
    """
    一键：转 CSV → 校验聚合（含目标公司切片）→ 导出 Excel →（可选）AI 分析+审核。
    图表默认关闭；需要预览时可传 run_charts=True。
    """
    source_xlsx = Path(xlsx_path or config.xlsx_path)
    target_csv = Path(csv_path or config.csv_path)
    ctx = run_context or build_run_context(config, source_xlsx=source_xlsx)
    result = PipelineResult(run_context=ctx, tables={})

    if source_xlsx.exists():
        result.steps.append("convert")
        convert_xlsx(config, source_xlsx, target_csv, run_context=ctx)
    elif target_csv.exists():
        result.steps.append("reuse_csv")
        if ctx:
            ctx.copy_input(target_csv)
    else:
        raise FileNotFoundError(
            f"未找到底表 Excel（{source_xlsx}）或 CSV（{target_csv}），请先上传文件。"
        )

    result.steps.append("aggregate_export_excel")
    result.tables, result.excel_path = compute_tables(config, target_csv, run_context=ctx)

    if run_charts:
        result.steps.append("charts")
        generate_charts(config, result.tables, run_context=ctx)

    key = api_key if api_key is not None else config.api_key
    if not run_ai:
        result.ai_skipped_reason = "run_ai_disabled"
        return result
    if not key:
        result.ai_skipped_reason = "missing_api_key"
        if ctx:
            ctx.record_value("ai_skipped", "missing_api_key")
        return result

    result.steps.append("ai_review")
    report, review, score = run_ai_with_review(config, result.tables, api_key=key, run_context=ctx)
    result.report_text = report
    result.review_text = review
    result.review_score = score
    return result
