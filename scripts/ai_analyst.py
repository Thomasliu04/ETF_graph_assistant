import json
from pathlib import Path

import pandas as pd

try:
    from .contracts import META, analysis_table_order, ensure_plugins_loaded
    from .llm_client import LLMClient
    from .report_display import normalize_report_punctuation
    from .report_sections import (
        SECTION_HEADERS,
        extract_section_bodies,
        merge_sections,
        normalize_section_keys,
        split_sections,
        tables_for_sections,
    )
    from .run_context import RunContext
except ImportError:
    from contracts import META, analysis_table_order, ensure_plugins_loaded
    from llm_client import LLMClient
    from report_display import normalize_report_punctuation
    from report_sections import (
        SECTION_HEADERS,
        extract_section_bodies,
        merge_sections,
        normalize_section_keys,
        split_sections,
        tables_for_sections,
    )
    from run_context import RunContext

# 兼容旧引用；运行时以 analysis_table_order() 为准
ANALYSIS_TABLE_ORDER = [
    ("area", "区域ETF聚合数据", "area_agg"),
    ("track", "赛道ETF聚合数据", "track_agg"),
    ("manager", "管理人ETF排名数据", "manager_agg"),
    ("national_team", "国家队聚合数据", "national_team_agg"),
    ("target_summary", "目标公司总览", "target_summary"),
    ("target_by_area", "目标公司分区域", "target_by_area"),
    ("target_by_track", "目标公司分赛道", "target_by_track"),
    ("target_top_bottom", "目标公司增量/缩水梯队", "target_top_bottom"),
]

class ETFAIAnalyst:
    def __init__(
        self,
        api_key: str,
        model_name: str = "qwen-plus",
        api_type: str = "aliyun",
        base_url: str | None = None,
        timeout: int = 120,
        max_retries: int = 2,
        run_context: RunContext | None = None,
        target_company: str | None = None,
        *,
        api_url: str | None = None,
        client: LLMClient | None = None,
    ):
        self.api_key = api_key
        self.model = model_name
        self.api_type = api_type
        self.run_context = run_context
        self.target_company = target_company or META.target_company
        script_dir = Path(__file__).parent
        self.project_root = script_dir.parent
        skill_md = self.project_root / "skills.md"

        with open(skill_md, "r", encoding="utf-8") as f:
            self.skill_prompt = f.read()

        if client is not None:
            self.client = client
            self.api_url = client.api_url
        else:
            if api_url:
                self.api_url = api_url
            else:
                try:
                    from .providers import resolve_chat_completions_url
                except ImportError:
                    from providers import resolve_chat_completions_url

                self.api_url = resolve_chat_completions_url(api_type, base_url)
            self.client = LLMClient(
                api_key=api_key,
                api_url=self.api_url,
                model_name=model_name,
                timeout=timeout,
                max_retries=max_retries,
                run_context=run_context,
            )

    def df_to_json(self, df: pd.DataFrame) -> str:
        data = df.round(2).to_dict(orient="records")
        return json.dumps(data, ensure_ascii=False)

    def _manager_name_col(self, df: pd.DataFrame) -> str | None:
        for candidate in ("管理人", "基金公司"):
            if candidate in df.columns:
                return candidate
        return None

    def _slice_manager_df(self, df: pd.DataFrame, *, for_target: bool = False) -> pd.DataFrame:
        """压缩 manager 表：目标公司行 + 增量 TOP20（或仅目标公司行）。"""
        if df is None or df.empty:
            return df
        name_col = self._manager_name_col(df)
        aliases = list(META.target_company_aliases) + [self.target_company]
        aliases = [a for a in aliases if a]

        target_mask = pd.Series(False, index=df.index)
        if name_col:
            series = df[name_col].astype(str)
            for alias in aliases:
                target_mask = target_mask | series.str.contains(alias, na=False, regex=False)

        if for_target:
            sliced = df.loc[target_mask]
            return sliced if not sliced.empty else df.head(1).copy()

        top = df
        if "规模增量" in df.columns:
            top = df.sort_values("规模增量", ascending=False).head(20)
        elif "增量排名" in df.columns:
            top = df.sort_values("增量排名", ascending=True).head(20)
        else:
            top = df.head(20)

        parts = [top]
        if target_mask.any():
            parts.append(df.loc[target_mask])
        out = pd.concat(parts, axis=0)
        return out[~out.index.duplicated(keep="first")].copy()

    def slice_tables_for_sections(
        self,
        tables: dict[str, pd.DataFrame],
        section_keys: list[str],
    ) -> dict[str, pd.DataFrame]:
        needed = tables_for_sections(section_keys)
        sliced: dict[str, pd.DataFrame] = {}
        for key in needed:
            df = tables.get(key)
            if df is None or df.empty:
                continue
            if key == "manager":
                # manager 章节：TOP20+目标公司；仅 target 引用时：只保留目标公司行
                only_target = "manager" not in normalize_section_keys(section_keys)
                sliced[key] = self._slice_manager_df(df, for_target=only_target)
            else:
                sliced[key] = df
        return sliced

    def build_input_payload(
        self,
        tables: dict[str, pd.DataFrame],
        *,
        table_keys: list[str] | None = None,
    ) -> str:
        ensure_plugins_loaded()
        table_order = analysis_table_order()
        allowed = set(table_keys) if table_keys is not None else None
        blocks = []
        for key, title, source_name in table_order:
            if allowed is not None and key not in allowed:
                continue
            df = tables.get(key)
            if df is None or df.empty:
                continue
            blocks.append(f"【{title} | 来源键={source_name}】\n{self.df_to_json(df)}")
        if not blocks:
            raise ValueError("没有可分析的数据表，请先完成聚合计算。")
        return "\n\n".join(blocks)

    def _save_report(self, analysis_result: str, *, artifact_name: str = "report.md") -> str:
        analysis_result = normalize_report_punctuation(analysis_result or "")
        report_path = self.project_root / "result" / "AI数据分析报告第一版测试.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(analysis_result)
        if self.run_context:
            self.run_context.save_text(
                "analysis_report", self.run_context.ai_dir, artifact_name, analysis_result
            )
            self.run_context.record_artifact("latest_analysis_report", report_path)
        print("✅ AI分析报告已生成至 result/AI数据分析报告第一版测试.md")
        return analysis_result

    def run_analysis(self, tables: dict[str, pd.DataFrame] | pd.DataFrame, *legacy_dfs):
        """
        新接口：run_analysis(tables_dict)
        兼容旧接口：run_analysis(area_df, track_df, manager_df)
        """
        if isinstance(tables, dict):
            table_map = tables
        else:
            area_df, track_df, manager_df = tables, legacy_dfs[0], legacy_dfs[1]
            table_map = {"area": area_df, "track": track_df, "manager": manager_df}

        input_data = self.build_input_payload(table_map)
        anchor_hint = "\n".join(f"- {SECTION_HEADERS[k]}" for k in SECTION_HEADERS)
        full_prompt = (
            f"{self.skill_prompt}\n"
            f"下面是本次待分析的结构化数据：\n{input_data}\n\n"
            f"请严格按以下四个锚点标题分章输出（标题不可改写）：\n{anchor_hint}"
        )
        if self.run_context:
            self.run_context.save_text(
                "analyst_prompt", self.run_context.prompt_dir, "analyst_prompt.md", full_prompt
            )
            self.run_context.record_value(
                "analyst_input_tables",
                [key for key, _, _ in analysis_table_order() if key in table_map and not table_map[key].empty],
            )

        analysis_result = self.client.chat(
            messages=[{"role": "user", "content": full_prompt}],
            temperature=0.2,
            artifact_prefix="analyst",
        )
        return self._save_report(analysis_result, artifact_name="report.md")

    def revise_sections(
        self,
        tables: dict[str, pd.DataFrame],
        full_report: str,
        review_feedback: dict,
        section_keys: list[str] | None = None,
    ) -> str:
        """仅改写失败章节，拼回全文。"""
        failed = normalize_section_keys(
            section_keys or review_feedback.get("failed_sections") or []
        )
        if not failed:
            failed = normalize_section_keys(
                [err.get("section") for err in review_feedback.get("errors") or [] if isinstance(err, dict)]
            )
        if not failed:
            raise ValueError("没有可局部改写的章节（failed_sections 为空）")

        section_bodies = extract_section_bodies(full_report, failed)
        sliced_tables = self.slice_tables_for_sections(tables, failed)
        input_data = self.build_input_payload(sliced_tables, table_keys=list(sliced_tables.keys()))

        errors = [
            err
            for err in (review_feedback.get("errors") or [])
            if isinstance(err, dict) and str(err.get("section", "")).lower() in failed
        ]
        feedback_json = json.dumps(
            {
                "score": review_feedback.get("score"),
                "failed_sections": failed,
                "errors": errors,
                "rewrite_instructions": review_feedback.get("rewrite_instructions") or "",
            },
            ensure_ascii=False,
            indent=2,
        )
        section_blocks = "\n\n".join(section_bodies[k] for k in failed if k in section_bodies)
        required_headers = "\n".join(SECTION_HEADERS[k] for k in failed)

        prompt = f"""你是ETF研报写作者。请根据审核反馈，仅重写下列失败章节。

# 写作规范（摘要）
{self.skill_prompt}

# 相关数据表（已按章节裁剪）
{input_data}

# 待改写章节原文
{section_blocks}

# 审核反馈（JSON）
{feedback_json}

# 硬性要求
1. 只输出需要改写的章节，不要输出未失败章节。
2. 每个章节必须以对应锚点标题开头，标题不可改写：
{required_headers}
3. 必须依据数据表修正错误；禁止编造数字；关键数字标注来源。
4. 目标公司产品梯队必须来自 target_top_bottom，禁止误用全市场 track_agg TOP 产品。
"""
        if self.run_context:
            self.run_context.save_text(
                "analyst_revise_prompt",
                self.run_context.prompt_dir,
                "analyst_revise_prompt.md",
                prompt,
            )
            self.run_context.record_value("analyst_revise_sections", failed)

        revised_text = self.client.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            artifact_prefix="analyst_revise",
        )
        # 从模型输出中尽量抽出各章节再合并
        revised_parts = extract_section_bodies(revised_text, failed)
        # 若模型把多章挤在一起但锚点齐全，extract 可用；否则整段当作唯一章节
        present = [k for k in failed if k in revised_parts and "待补充" not in revised_parts[k] and "缺失该章节" not in revised_parts[k]]
        if not present:
            if len(failed) == 1:
                revised_parts = {failed[0]: revised_text.strip()}
            else:
                parsed = split_sections(revised_text)
                revised_parts = {k: parsed[k] for k in failed if k in parsed}

        merged = merge_sections(full_report, revised_parts, ensure_all_sections=True)
        return self._save_report(merged, artifact_name="report_revised.md")

    def revise_full_with_feedback(
        self,
        tables: dict[str, pd.DataFrame],
        full_report: str,
        review_feedback: dict,
    ) -> str:
        """带压缩审核反馈的全文改写（仅作解析失败/无章节时的兜底，限用一次）。"""
        input_data = self.build_input_payload(tables)
        feedback_json = json.dumps(
            {
                "score": review_feedback.get("score"),
                "failed_sections": review_feedback.get("failed_sections") or [],
                "errors": review_feedback.get("errors") or [],
                "rewrite_instructions": review_feedback.get("rewrite_instructions") or "",
            },
            ensure_ascii=False,
            indent=2,
        )
        anchor_hint = "\n".join(f"- {SECTION_HEADERS[k]}" for k in SECTION_HEADERS)
        prompt = f"""{self.skill_prompt}

下面是本次待分析的结构化数据：
{input_data}

# 上一版报告
{full_report}

# 审核反馈（必须据此修正）
{feedback_json}

请输出完整修订版报告。必须严格使用以下四个锚点标题：
{anchor_hint}
"""
        if self.run_context:
            self.run_context.save_text(
                "analyst_full_revise_prompt",
                self.run_context.prompt_dir,
                "analyst_full_revise_prompt.md",
                prompt,
            )

        analysis_result = self.client.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            artifact_prefix="analyst_full_revise",
        )
        return self._save_report(analysis_result, artifact_name="report_full_revised.md")
