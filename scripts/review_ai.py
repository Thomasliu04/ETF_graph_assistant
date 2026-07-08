from pathlib import Path

try:
    from .llm_client import LLMClient
    from .run_context import RunContext
except ImportError:
    from llm_client import LLMClient
    from run_context import RunContext

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

        # 读取项目根目录审核规则md
        script_dir = Path(__file__).parent
        self.project_root = script_dir.parent
        self.check_skill_path = self.project_root / "skill_check.md"
        with open(self.check_skill_path, "r", encoding="utf-8") as f:
            self.check_rule = f.read()

    # DataFrame转文本传给审核模型
    def df_to_text(self, df, table_name: str) -> str:
        return f"【{table_name}原始数据表】\n{df.to_csv(index=False, encoding='utf-8-sig')}"

    def run_review(self, report_text, df_area, df_track, df_manager):
        # 拼接三张原始数据表
        table_all_text = "\n\n".join([
            self.df_to_text(df_area, "区域维度聚合表"),
            self.df_to_text(df_track, "赛道维度聚合表"),
            self.df_to_text(df_manager, "管理人维度聚合表")
        ])

        # 组装prompt
        user_msg = f"""
# 待校验原始数据源
{table_all_text}

# 需要你审核的AI分析报告
{report_text}

严格按照下方校验规则执行全量校验，输出标准化审核打分报告：
{self.check_rule}
"""
        messages = [
                {"role": "system", "content": "你是专业ETF数据审核专员，仅依靠传入数据表校验报告，禁止使用外部行业知识，严格按规则打分输出"},
                {"role": "user", "content": user_msg}
        ]
        if self.run_context:
            self.run_context.save_text("reviewer_prompt", self.run_context.prompt_dir, "reviewer_prompt.md", user_msg)

        review_output = self.client.chat(
            messages=messages,
            temperature=0.01,
            artifact_prefix="reviewer",
        )

        # 保存审核报告至result文件夹
        save_path = self.project_root / "result" / "AI审核报告.md"
        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(review_output)
        if self.run_context:
            self.run_context.save_text("review_report", self.run_context.ai_dir, "review.md", review_output)
            self.run_context.record_artifact("latest_review_report", save_path)
        return review_output
