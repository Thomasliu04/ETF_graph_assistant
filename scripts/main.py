import re
from data_calc import ETFDataCalculator
from ai_analyst import ETFAIAnalyst
from visual_plot import ETFVisualizer
from review_ai import AIReviewer
from config import AppConfig
from run_context import RunContext


if __name__ == "__main__":
    config = AppConfig()
    run_context = RunContext(config.run_dir)
    run_context.record_value(
        "config",
        {
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
    print(f"本次运行ID：{run_context.run_id}")
    print(f"运行留痕目录：{run_context.run_dir}")

    # 3. 执行XLSX转CSV
    run_context.copy_input(config.xlsx_path)
    csv_file = ETFDataCalculator.xlsx_to_csv(config.xlsx_path, config.csv_path, sheet_name=config.sheet_name)
    run_context.copy_input(config.csv_path)

    # ========== 第一步：Pandas数据聚合（现在读取csv） ==========
    calc = ETFDataCalculator(base_csv_path=csv_file, run_context=run_context)
    agg_tables = calc.calc_registered_aggs(["area", "track", "manager", "national_team"])
    df_area = agg_tables["area"]
    df_track = agg_tables["track"]
    df_manager = agg_tables["manager"]
    calc.export_agg_tables(agg_tables)

    # ========== 第二步：可视化 ==========
    plot = ETFVisualizer(save_dir=config.output_dir, run_context=run_context)
    plot.plot_area_increment(df_area)
    plot.plot_track_top10(df_track)
    plot.plot_manager_top20(df_manager)

    # ========== 全局统一API配置 ==========
    api_key = config.api_key
    if not api_key:
        print("\n未检测到 API Key，已跳过AI生成与审核。")
        print("如需启用AI阶段，请设置环境变量 ETF_AI_API_KEY 或 DASHSCOPE_API_KEY。")
        run_context.record_value("ai_skipped", "missing_api_key")
        raise SystemExit(0)

    # ========== 第三步：AI生成报告 + AI自动审核循环 ==========
    # 初始化生成AI、审核AI
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
    final_review_result = ""

    while retry_count <= config.max_retry_times:
        print(f"\n===== 第 {retry_count + 1} 轮生成分析报告 =====")
        current_report = analyst.run_analysis(df_area, df_track, df_manager)
        print("\n===== 开始执行AI自动校验审核 =====")
        current_review = reviewer.run_review(current_report, df_area, df_track, df_manager)

        # 正则提取审核总分
        score_match = re.search(r"总分[:：]\s*(\d+)", current_review)
        review_score = int(score_match.group(1)) if score_match else 50
        print(f"\n本次审核可信度得分：{review_score}")

        # 分支判断
        if review_score >= 80:
            final_report = current_report
            final_review_result = current_review
            print(f"✅ 审核通过，分数{review_score}，无需重写报告")
            break
        elif 60 <= review_score < 80 and retry_count < config.max_retry_times:
            retry_count += 1
            print(f"⚠️ 分数{review_score}，存在多处数据/逻辑错误，自动重新生成报告")
            continue
        else:
            final_report = current_report
            final_review_result = current_review
            print(f"❌ 分数{review_score}，严重失真，已达最大重试次数，请人工完整复核result内两份文档")
            break

    # 最终输出
    print("\n" + "=" * 60)
    print("📌 最终AI分析报告内容：")
    print(final_report)
    print("\n" + "=" * 60)
    print("📌 AI自动审核完整校验报告（保存在result/AI审核报告.md）：")
    print(final_review_result)
    run_context.record_value("final_review_score", review_score)
