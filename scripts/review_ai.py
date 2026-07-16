from pathlib import Path

import pandas as pd

try:
    from .llm_client import LLMClient
    from .run_context import RunContext
except ImportError:
    from llm_client import LLMClient
    from run_context import RunContext

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

    def build_table_text(self, tables: dict[str, pd.DataFrame]) -> str:
        blocks = []
        for key, title, source_name in REVIEW_TABLE_ORDER:
            df = tables.get(key)
            if df is None or df.empty:
                continue
            blocks.append(self.df_to_text(df, title, source_name))
        if not blocks:
            raise ValueError("没有可供审核对照的数据表。")
        return "\n\n".join(blocks)

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
            {
                "role": "system",
                "content": (
                    "你是专业ETF数据审核专员，仅依靠传入数据表校验报告，"
                    "禁止使用外部行业知识，严格按规则打分输出。"
                    "输出中必须包含一行：总分：xx"
                ),
            },
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

        save_path = self.project_root / "result" / "AI审核报告.md"
        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(review_output)
        if self.run_context:
            self.run_context.save_text(
                "review_report", self.run_context.ai_dir, "review.md", review_output
            )
            self.run_context.record_artifact("latest_review_report", save_path)
        return review_output
