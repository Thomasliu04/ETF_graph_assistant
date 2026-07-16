from config import AppConfig
from pipeline import format_user_error, run_full_pipeline


if __name__ == "__main__":
    config = AppConfig()
    try:
        result = run_full_pipeline(config=config, run_ai=True)
    except Exception as exc:
        print(format_user_error(exc))
        raise SystemExit(1) from exc

    print(f"本次运行ID：{result.run_context.run_id}")
    print(f"运行留痕目录：{result.run_context.run_dir}")
    print(f"已完成步骤：{', '.join(result.steps)}")
    print(f"数据表：{list(result.tables)}")
    if result.excel_path:
        print(f"Excel 已导出：{result.excel_path}")

    if result.ai_skipped_reason:
        print(f"\n已跳过AI阶段：{result.ai_skipped_reason}")
        if result.ai_skipped_reason == "missing_api_key":
            print("如需启用AI，请设置环境变量 ETF_AI_API_KEY 或在 .env 中配置。")
        raise SystemExit(0)

    print("\n" + "=" * 60)
    print("📌 最终AI分析报告内容：")
    print(result.report_text)
    print("\n" + "=" * 60)
    print("📌 AI自动审核完整校验报告（保存在result/AI审核报告.md）：")
    print(result.review_text)
    if result.review_score is not None:
        print(f"\n最终审核得分：{result.review_score}")
    else:
        print("\n未能从审核结果中解析总分，请人工查看审核报告。")
