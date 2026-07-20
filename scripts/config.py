import os
from dataclasses import dataclass
from pathlib import Path

try:
    from .contracts import META
except ImportError:
    from contracts import META

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_project_env(env_path: Path):
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path)
        return
    except ModuleNotFoundError:
        pass

    if not env_path.exists():
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


load_project_env(PROJECT_ROOT / ".env")


def env_str(name: str, default: str) -> str:
    return os.getenv(name, default)


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"环境变量 {name} 必须是整数，当前值：{value}") from exc


@dataclass(frozen=True)
class AppConfig:
    project_root: Path = PROJECT_ROOT
    data_dir: Path = PROJECT_ROOT / "data"
    result_dir: Path = PROJECT_ROOT / "result"
    output_dir: Path = PROJECT_ROOT / "output"
    run_dir: Path = PROJECT_ROOT / "runs"
    xlsx_path: Path = PROJECT_ROOT / "data" / "etf底表.xlsx"
    csv_path: Path = PROJECT_ROOT / "data" / "etf底表.csv"
    skill_path: Path = PROJECT_ROOT / "skills.md"
    review_skill_path: Path = PROJECT_ROOT / "skill_check.md"
    # 口径默认值来自数据契约；可用同名字段覆盖（例如测试时注入）
    sheet_name: str = META.sheet_name
    period_start: str = META.period_start
    period_end: str = META.period_end
    target_company: str = META.target_company
    data_contract_version: str = META.version
    api_type: str = env_str("ETF_AI_API_TYPE", "aliyun")
    model_name: str = env_str("ETF_AI_MODEL_NAME", "qwen3.7-plus")
    base_url: str = env_str(
        "ETF_AI_BASE_URL",
        "https://ws-809e4eujqwysgybs.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
    )
    max_retry_times: int = env_int("ETF_AI_REPORT_RETRIES", 2)
    # 生成-审核 loop：达标分、局部改写轮数、最小分数增益（无增益则熔断）
    pass_score: int = env_int("ETF_AI_PASS_SCORE", 80)
    max_revise_rounds: int = env_int("ETF_AI_MAX_REVISE_ROUNDS", 2)
    min_score_gain: int = env_int("ETF_AI_MIN_SCORE_GAIN", 5)
    request_timeout: int = env_int("ETF_AI_REQUEST_TIMEOUT", 300)
    request_retries: int = env_int("ETF_AI_REQUEST_RETRIES", 2)

    @property
    def api_key(self) -> str | None:
        return os.getenv("ETF_AI_API_KEY") or os.getenv("DASHSCOPE_API_KEY") or os.getenv("OPENAI_API_KEY")

    @property
    def chat_completions_url(self) -> str:
        if self.api_type == "openai":
            return "https://api.openai.com/v1/chat/completions"
        return f"{self.base_url.rstrip('/')}/chat/completions"
