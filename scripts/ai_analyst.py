import json
from pathlib import Path

import pandas as pd

try:
    from .llm_client import LLMClient
    from .run_context import RunContext
except ImportError:
    from llm_client import LLMClient
    from run_context import RunContext

# 进入分析 Prompt 的表及展示名（顺序固定，便于对照 Skill）
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
    ):
        self.api_key = api_key
        self.model = model_name
        self.api_type = api_type
        self.run_context = run_context
        script_dir = Path(__file__).parent
        self.project_root = script_dir.parent
        skill_md = self.project_root / "skills.md"

        with open(skill_md, "r", encoding="utf-8") as f:
            self.skill_prompt = f.read()

        if api_type == "aliyun":
            default_base_url = "https://ws-809e4eujqwysgybs.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
            self.api_url = f"{(base_url or default_base_url).rstrip('/')}/chat/completions"
        elif api_type == "openai":
            self.api_url = f"{(base_url or 'https://api.openai.com/v1').rstrip('/')}/chat/completions"
        else:
            raise ValueError("api_type仅支持aliyun或openai")
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

    def build_input_payload(self, tables: dict[str, pd.DataFrame]) -> str:
        blocks = []
        for key, title, source_name in ANALYSIS_TABLE_ORDER:
            df = tables.get(key)
            if df is None or df.empty:
                continue
            blocks.append(f"【{title} | 来源键={source_name}】\n{self.df_to_json(df)}")
        if not blocks:
            raise ValueError("没有可分析的数据表，请先完成聚合计算。")
        return "\n\n".join(blocks)

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
        full_prompt = f"{self.skill_prompt}\n下面是本次待分析的结构化数据：\n{input_data}"
        if self.run_context:
            self.run_context.save_text(
                "analyst_prompt", self.run_context.prompt_dir, "analyst_prompt.md", full_prompt
            )
            self.run_context.record_value(
                "analyst_input_tables",
                [key for key, _, _ in ANALYSIS_TABLE_ORDER if key in table_map and not table_map[key].empty],
            )

        analysis_result = self.client.chat(
            messages=[{"role": "user", "content": full_prompt}],
            temperature=0.2,
            artifact_prefix="analyst",
        )

        report_path = self.project_root / "result" / "AI数据分析报告第一版测试.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(analysis_result)
        if self.run_context:
            self.run_context.save_text(
                "analysis_report", self.run_context.ai_dir, "report.md", analysis_result
            )
            self.run_context.record_artifact("latest_analysis_report", report_path)
        print("✅ AI分析报告已生成至 result/AI数据分析报告第一版测试.md")
        return analysis_result
