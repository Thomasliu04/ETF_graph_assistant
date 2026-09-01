"""CLI / Web 共用的分析流水线。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import pandas as pd

try:
    from .ai_analyst import ETFAIAnalyst
    from .config import AppConfig
    from .contracts import default_agg_names, ensure_plugins_loaded
    from .data_calc import ETFDataCalculator
    from .report_sections import normalize_section_keys
    from .review_ai import AIReviewer, extract_review_payload
    from .run_context import RunContext
    from .visual_plot import ETFVisualizer
except ImportError:
    from ai_analyst import ETFAIAnalyst
    from config import AppConfig
    from contracts import default_agg_names, ensure_plugins_loaded
    from data_calc import ETFDataCalculator
    from report_sections import normalize_section_keys
    from review_ai import AIReviewer, extract_review_payload
    from run_context import RunContext
    from visual_plot import ETFVisualizer

# 兼容旧引用；运行时以 default_agg_names() 为准
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
    """兼容旧接口：优先结构化 JSON，再回退正文总分。"""
    payload = extract_review_payload(review_text)
    return payload.get("score")


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
            "base_url": config.resolved_base_url,
            "chat_completions_url": config.chat_completions_url,
            "max_retry_times": config.max_retry_times,
            "pass_score": config.pass_score,
            "max_revise_rounds": config.max_revise_rounds,
            "min_score_gain": config.min_score_gain,
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
    ensure_plugins_loaded()
    calc = ETFDataCalculator(base_csv_path=str(csv_path), run_context=run_context)
    tables = calc.calc_analysis_tables(
        agg_names=agg_names or default_agg_names(),
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
    on_progress: Callable[[str, float], None] | None = None,
) -> tuple[str, str, int | None]:
    """
    生成 → 结构化审核 →（必要时）章节局部改写 / 一次全文反馈改写 → 增量复审。
    保留历史最高分版本；达标、无增益或达到改写轮数上限时结束。

    on_progress(message, fraction): fraction 为 0~1，表示 AI 阶段内部进度。
    """
    def _progress(message: str, fraction: float) -> None:
        if on_progress is not None:
            on_progress(message, max(0.0, min(1.0, fraction)))

    analyst = ETFAIAnalyst(
        api_key=api_key,
        model_name=config.model_name,
        api_type=config.api_type,
        base_url=config.base_url or None,
        timeout=config.request_timeout,
        max_retries=config.request_retries,
        run_context=run_context,
        target_company=config.target_company,
        api_url=config.chat_completions_url,
    )
    reviewer = AIReviewer(
        api_key=api_key,
        base_url=config.resolved_base_url,
        model_name=config.model_name,
        timeout=config.request_timeout,
        max_retries=config.request_retries,
        run_context=run_context,
        api_url=config.chat_completions_url,
    )

    pass_score = config.pass_score
    max_revise_rounds = max(0, config.max_revise_rounds)
    min_score_gain = max(0, config.min_score_gain)

    loop_log: list[dict] = []
    best_report = ""
    best_review = ""
    best_score: int | None = None
    best_payload: dict = {}

    _progress("3.1/4 准备生成：组装数据与写作 Prompt…", 0.02)
    _progress("3.1/4 已提交全文生成请求，等待模型返回（通常最耗时）…", 0.08)
    current_report = analyst.run_analysis(tables)
    _progress("3.1/4 全文报告已生成，准备送审…", 0.38)

    _progress("3.2/4 已提交全量审核请求，等待打分与错误清单…", 0.42)
    current_review = reviewer.run_review(current_report, tables)
    current_payload = extract_review_payload(current_review)
    current_score = current_payload.get("score")

    def _remember(mode: str, report: str, review: str, payload: dict, score: int | None) -> None:
        entry = {
            "attempt": len(loop_log),
            "mode": mode,
            "score": score,
            "failed_sections": list(payload.get("failed_sections") or []),
            "parse_ok": bool(payload.get("parse_ok")),
        }
        loop_log.append(entry)
        nonlocal best_report, best_review, best_score, best_payload
        if score is None:
            if best_score is None and not best_report:
                best_report, best_review, best_payload = report, review, payload
            return
        if best_score is None or score > best_score:
            best_report, best_review, best_score, best_payload = report, review, score, payload

    _remember("generate", current_report, current_review, current_payload, current_score)
    if current_score is not None and current_score >= pass_score:
        _progress(f"3.2/4 审核已达标（{current_score}分），无需改写", 0.95)
    else:
        score_label = str(current_score) if current_score is not None else "未解析"
        _progress(f"3.2/4 首轮得分 {score_label}（未达标），进入改写循环…", 0.48)

    revise_rounds = 0
    full_revise_used = False
    prev_score_for_gain = current_score

    while True:
        if current_score is not None and current_score >= pass_score:
            break
        if revise_rounds >= max_revise_rounds:
            _progress(
                f"3.3/4 已达改写上限（{max_revise_rounds} 轮），停止改写",
                0.88,
            )
            break

        failed_sections = normalize_section_keys(current_payload.get("failed_sections") or [])
        if not failed_sections:
            failed_sections = normalize_section_keys(
                [
                    err.get("section")
                    for err in (current_payload.get("errors") or [])
                    if isinstance(err, dict)
                ]
            )

        mode = "section_revise"
        round_no = revise_rounds + 1
        # 改写阶段占用约 0.50~0.90
        base = 0.50 + 0.18 * revise_rounds / max(max_revise_rounds, 1)
        try:
            if failed_sections:
                sec = "、".join(failed_sections)
                _progress(
                    f"3.3/4 第 {round_no} 轮局部改写：{sec}（已提交，等待模型）…",
                    base,
                )
                current_report = analyst.revise_sections(
                    tables,
                    current_report,
                    current_payload,
                    section_keys=failed_sections,
                )
                changed = failed_sections
                _progress(f"3.3/4 第 {round_no} 轮局部改写完成", base + 0.06)
            elif not full_revise_used:
                _progress(
                    f"3.3/4 第 {round_no} 轮全文反馈改写（已提交，等待模型）…",
                    base,
                )
                current_report = analyst.revise_full_with_feedback(
                    tables, current_report, current_payload
                )
                changed = ["area", "track", "manager", "target"]
                full_revise_used = True
                mode = "full_revise"
                _progress(f"3.3/4 第 {round_no} 轮全文改写完成", base + 0.06)
            else:
                break
        except ValueError:
            if not full_revise_used:
                _progress(
                    f"3.3/4 第 {round_no} 轮全文反馈改写（已提交，等待模型）…",
                    base,
                )
                current_report = analyst.revise_full_with_feedback(
                    tables, current_report, current_payload
                )
                changed = ["area", "track", "manager", "target"]
                full_revise_used = True
                mode = "full_revise"
                _progress(f"3.3/4 第 {round_no} 轮全文改写完成", base + 0.06)
            else:
                break

        revise_rounds += 1
        _progress(
            f"3.4/4 第 {revise_rounds} 轮增量复审（已提交，等待打分）…",
            min(base + 0.10, 0.90),
        )
        sliced = analyst.slice_tables_for_sections(tables, changed)
        current_review = reviewer.run_delta_review(
            full_report=current_report,
            changed_sections=changed,
            previous_errors=list(current_payload.get("errors") or []),
            tables=tables,
            sliced_tables=sliced,
        )
        current_payload = extract_review_payload(current_review)
        current_score = current_payload.get("score")
        _remember(mode, current_report, current_review, current_payload, current_score)
        score_label = str(current_score) if current_score is not None else "未解析"
        _progress(
            f"3.4/4 第 {revise_rounds} 轮复审完成，得分 {score_label}",
            min(base + 0.14, 0.92),
        )

        if current_score is not None and current_score >= pass_score:
            _progress(f"3.4/4 复审达标（{current_score}分）", 0.95)
            break

        if (
            prev_score_for_gain is not None
            and current_score is not None
            and (current_score - prev_score_for_gain) < min_score_gain
        ):
            loop_log.append(
                {
                    "attempt": len(loop_log),
                    "mode": "early_stop_no_gain",
                    "score": current_score,
                    "prev_score": prev_score_for_gain,
                    "min_score_gain": min_score_gain,
                }
            )
            _progress(
                f"3.4/4 分数增益不足（{prev_score_for_gain}→{current_score}），提前结束",
                0.93,
            )
            break
        prev_score_for_gain = current_score if current_score is not None else prev_score_for_gain

    final_report = best_report or current_report
    final_review = best_review or current_review
    review_score = best_score if best_score is not None else current_score
    _progress("3/4 整理最佳版本报告与审核结果…", 0.96)

    if run_context is not None:
        run_context.record_value("ai_loop_log", loop_log)
        if review_score is not None:
            run_context.record_value("final_review_score", review_score)
        run_context.record_value(
            "final_failed_sections",
            list((best_payload or current_payload).get("failed_sections") or []),
        )
        # 确保 result/ 与 ai/ 目录落盘的是最佳版本
        if final_report:
            analyst._save_report(final_report, artifact_name="report.md")
        if final_review:
            reviewer._save_review(final_review, filename="review.md")

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
