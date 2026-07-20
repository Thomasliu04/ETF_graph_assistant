from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

try:
    from .contracts import analysis_table_order, ensure_plugins_loaded
    from .llm_client import LLMClient
    from .report_sections import (
        extract_section_bodies,
        normalize_section_keys,
        tables_for_sections,
    )
    from .run_context import RunContext
except ImportError:
    from contracts import analysis_table_order, ensure_plugins_loaded
    from llm_client import LLMClient
    from report_sections import (
        extract_section_bodies,
        normalize_section_keys,
        tables_for_sections,
    )
    from run_context import RunContext

# 兼容旧引用；运行时以 analysis_table_order() 为准
REVIEW_TABLE_ORDER = [
    ("area", "区域维度聚合表", "area_agg"),
    ("track", "赛道维度聚合表", "track_agg"),
    ("manager", "管理人维度聚合表", "manager_agg"),
    ("national_team", "国家队聚合表", "national_team_agg"),
    ("target_summary", "目标公司总览", "target_summary"),
    ("target_by_area", "目标公司分区域", "target_by_area"),
    ("target_by_track", "目标公司分赛道", "target_by_track"),
    ("target_top_bottom", "目标公司增量/缩水梯队", "target_top_bottom"),
]

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_SCORE_RE = re.compile(r"总分[:：]\s*(\d+)")


def _extract_balanced_json_objects(text: str) -> list[str]:
    """从文本中提取平衡的 JSON 对象字符串（支持嵌套）。"""
    objects: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] != "{":
            i += 1
            continue
        depth = 0
        in_str = False
        escape = False
        start = i
        for j in range(i, n):
            ch = text[j]
            if in_str:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    objects.append(text[start : j + 1])
                    i = j + 1
                    break
        else:
            break
    return objects


def extract_review_payload(review_text: str) -> dict[str, Any]:
    """
    从审核输出解析结构化结果。
    优先 JSON 代码块；失败则回退正文「总分：xx」。
    """
    text = review_text or ""
    payload: dict[str, Any] = {
        "score": None,
        "errors": [],
        "failed_sections": [],
        "rewrite_instructions": "",
        "raw_text": text,
        "parse_ok": False,
    }

    candidates: list[str] = []
    for match in _JSON_FENCE_RE.finditer(text):
        candidates.extend(_extract_balanced_json_objects(match.group(1)))
    # 正文中也可能直接贴 JSON
    candidates.extend(_extract_balanced_json_objects(text))

    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict) or "score" not in data:
            continue
        score = data.get("score")
        try:
            score_int = int(score) if score is not None else None
        except (TypeError, ValueError):
            score_int = None
        errors = data.get("errors") if isinstance(data.get("errors"), list) else []
        failed = normalize_section_keys(data.get("failed_sections") or [])
        if not failed:
            failed = normalize_section_keys(
                [e.get("section") for e in errors if isinstance(e, dict)]
            )
        payload.update(
            {
                "score": score_int,
                "errors": errors,
                "failed_sections": failed,
                "rewrite_instructions": str(data.get("rewrite_instructions") or ""),
                "parse_ok": score_int is not None,
            }
        )
        break

    if payload["score"] is None:
        match = _SCORE_RE.search(text)
        if match:
            payload["score"] = int(match.group(1))

    return payload


class AIReviewer:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model_name="qwen3.7-plus",
        timeout: int = 120,
        max_retries: int = 2,
        run_context: RunContext | None = None,
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.model_name = model_name
        self.api_url = f"{base_url.rstrip('/')}/chat/completions"
        self.run_context = run_context
        self.client = LLMClient(
            api_key=api_key,
            api_url=self.api_url,
            model_name=model_name,
            timeout=timeout,
            max_retries=max_retries,
            run_context=run_context,
        )

        script_dir = Path(__file__).parent
        self.project_root = script_dir.parent
        self.check_skill_path = self.project_root / "skill_check.md"
        with open(self.check_skill_path, "r", encoding="utf-8") as f:
            self.check_rule = f.read()

    def df_to_text(self, df: pd.DataFrame, table_name: str, source_name: str) -> str:
        return (
            f"【{table_name} | 来源键={source_name}】\n"
            f"{df.to_csv(index=False, encoding='utf-8-sig')}"
        )

    def build_table_text(
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
            blocks.append(self.df_to_text(df, title, source_name))
        if not blocks:
            raise ValueError("没有可供审核对照的数据表。")
        return "\n\n".join(blocks)

    def _system_message(self) -> str:
        return (
            "你是专业ETF数据审核专员，仅依靠传入数据表校验报告，"
            "禁止使用外部行业知识，严格按规则打分输出。"
            "输出中必须包含一行：总分：xx；"
            "并在文末追加一个 JSON 代码块，字段含 score、errors、failed_sections、rewrite_instructions。"
        )

    def _save_review(self, review_output: str, *, filename: str = "review.md") -> str:
        save_path = self.project_root / "result" / "AI审核报告.md"
        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(review_output)
        if self.run_context:
            self.run_context.save_text(
                "review_report", self.run_context.ai_dir, filename, review_output
            )
            self.run_context.record_artifact("latest_review_report", save_path)
        return review_output

    def run_review(self, report_text, tables: dict[str, pd.DataFrame] | pd.DataFrame, *legacy_dfs):
        """
        新接口：run_review(report_text, tables_dict)
        兼容旧接口：run_review(report_text, area_df, track_df, manager_df)
        """
        if isinstance(tables, dict):
            table_map = tables
        else:
            area_df, track_df, manager_df = tables, legacy_dfs[0], legacy_dfs[1]
            table_map = {"area": area_df, "track": track_df, "manager": manager_df}

        table_all_text = self.build_table_text(table_map)
        user_msg = f"""
# 待校验原始数据源
{table_all_text}

# 需要你审核的AI分析报告
{report_text}

严格按照下方校验规则执行全量校验，输出标准化审核打分报告：
{self.check_rule}
"""
        messages = [
            {"role": "system", "content": self._system_message()},
            {"role": "user", "content": user_msg},
        ]
        if self.run_context:
            self.run_context.save_text(
                "reviewer_prompt", self.run_context.prompt_dir, "reviewer_prompt.md", user_msg
            )

        review_output = self.client.chat(
            messages=messages,
            temperature=0.01,
            artifact_prefix="reviewer",
        )
        return self._save_review(review_output, filename="review.md")

    def run_delta_review(
        self,
        full_report: str,
        changed_sections: list[str],
        previous_errors: list[dict],
        tables: dict[str, pd.DataFrame],
        *,
        sliced_tables: dict[str, pd.DataFrame] | None = None,
    ) -> str:
        """增量复审：重点核对变更章节与上一轮错误是否已修复。"""
        changed = normalize_section_keys(changed_sections)
        table_keys = tables_for_sections(changed) if changed else None
        source_tables = sliced_tables if sliced_tables is not None else tables
        if table_keys:
            # 若传入的是裁剪后的表，按可用键构建；否则从全量表取子集键
            available = [k for k in table_keys if k in source_tables and not source_tables[k].empty]
            table_text = self.build_table_text(source_tables, table_keys=available or None)
        else:
            table_text = self.build_table_text(source_tables)

        changed_bodies = extract_section_bodies(full_report, changed) if changed else {}
        changed_text = "\n\n".join(changed_bodies.get(k, "") for k in changed)
        prev_errors_json = json.dumps(previous_errors or [], ensure_ascii=False, indent=2)

        user_msg = f"""
# 审核模式
增量复审（delta review）

# 本轮已改写章节
{", ".join(changed) if changed else "（无）"}

# 已改写章节正文
{changed_text or "（无）"}

# 完整报告（供跨章节一致性与总分判断）
{full_report}

# 上一轮错误清单（请核对是否已修复）
{prev_errors_json}

# 相关原始数据源（已按变更章节裁剪）
{table_text}

严格按照下方校验规则执行增量复审，输出标准化审核打分报告（含文末 JSON）：
{self.check_rule}
"""
        messages = [
            {"role": "system", "content": self._system_message()},
            {"role": "user", "content": user_msg},
        ]
        if self.run_context:
            self.run_context.save_text(
                "reviewer_delta_prompt",
                self.run_context.prompt_dir,
                "reviewer_delta_prompt.md",
                user_msg,
            )
            self.run_context.record_value("reviewer_delta_sections", changed)

        review_output = self.client.chat(
            messages=messages,
            temperature=0.01,
            artifact_prefix="reviewer_delta",
        )
        return self._save_review(review_output, filename="review_delta.md")
