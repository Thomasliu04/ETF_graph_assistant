import json
from pathlib import Path

try:
    from .llm_client import LLMClient
    from .run_context import RunContext
except ImportError:
    from llm_client import LLMClient
    from run_context import RunContext

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
        # 定位项目根目录
        script_dir = Path(__file__).parent
        self.project_root = script_dir.parent
        skill_md = self.project_root / "skills.md"

        # 重点：这里用变量skill_md，不要再写 "skills.md"
        with open(skill_md, "r", encoding="utf-8") as f:
            self.skill_prompt = f.read()

        # API地址逻辑不变
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

    def df_to_json(self, df):
        data = df.round(2).to_dict(orient="records")
        return json.dumps(data, ensure_ascii=False)

    def run_analysis(self, area_df, track_df, manager_df):
        input_data = f"""
【区域ETF聚合数据】
{self.df_to_json(area_df)}

【赛道ETF聚合数据】
{self.df_to_json(track_df)}

【管理人ETF排名数据】
{self.df_to_json(manager_df)}
"""
        full_prompt = f"{self.skill_prompt}\n下面是本次待分析的结构化数据：\n{input_data}"
        if self.run_context:
            self.run_context.save_text("analyst_prompt", self.run_context.prompt_dir, "analyst_prompt.md", full_prompt)

        analysis_result = self.client.chat(
            messages=[{"role": "user", "content": full_prompt}],
            temperature=0.2,
            artifact_prefix="analyst",
        )

        # 报告保存到项目根的result文件夹，防止跑到scripts/output
        report_path = self.project_root / "result" / "AI数据分析报告第一版测试.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(analysis_result)
        if self.run_context:
            self.run_context.save_text("analysis_report", self.run_context.ai_dir, "report.md", analysis_result)
            self.run_context.record_artifact("latest_analysis_report", report_path)
        print("✅ AI分析报告已生成至 result/AI数据分析报告第一版测试.md")
        return analysis_result
