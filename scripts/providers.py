"""国内主流大模型厂商的 OpenAI 兼容接口预设。

换厂商时优先改 .env：
  ETF_AI_API_TYPE=<下方 key>
  ETF_AI_MODEL_NAME=<该厂模型名>
  ETF_AI_API_KEY=<密钥>
  # 可选覆盖：ETF_AI_BASE_URL=...

绝大多数厂商走 POST {base}/chat/completions + Bearer Token。
若某厂协议不同，再在此扩展 ProviderSpec（path / header 风格），业务侧无需改。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderSpec:
    """单个厂商的默认接入参数。"""

    key: str
    label: str
    default_base_url: str
    chat_path: str = "/chat/completions"
    # 可选：文档里常见的示例模型名，仅作提示，不强制
    example_models: tuple[str, ...] = ()

    def chat_url(self, base_url: str | None = None) -> str:
        root = (base_url or self.default_base_url).rstrip("/")
        path = self.chat_path if self.chat_path.startswith("/") else f"/{self.chat_path}"
        return f"{root}{path}"


# key 与 ETF_AI_API_TYPE 对齐（大小写不敏感）
PROVIDER_SPECS: dict[str, ProviderSpec] = {
    "aliyun": ProviderSpec(
        key="aliyun",
        label="阿里云百炼 / 兼容模式（项目默认 endpoint）",
        default_base_url=(
            "https://ws-809e4eujqwysgybs.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
        ),
        example_models=("qwen3.7-plus", "qwen-plus", "qwen-max"),
    ),
    "dashscope": ProviderSpec(
        key="dashscope",
        label="阿里云 DashScope 兼容模式（公网）",
        default_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        example_models=("qwen-plus", "qwen-max", "qwen-turbo"),
    ),
    "deepseek": ProviderSpec(
        key="deepseek",
        label="DeepSeek",
        default_base_url="https://api.deepseek.com/v1",
        example_models=("deepseek-chat", "deepseek-reasoner"),
    ),
    "zhipu": ProviderSpec(
        key="zhipu",
        label="智谱 GLM",
        default_base_url="https://open.bigmodel.cn/api/paas/v4",
        example_models=("glm-4-flash", "glm-4", "glm-4.5"),
    ),
    "moonshot": ProviderSpec(
        key="moonshot",
        label="月之暗面 Kimi",
        default_base_url="https://api.moonshot.cn/v1",
        example_models=("moonshot-v1-8k", "moonshot-v1-32k", "kimi-k2-0711-preview"),
    ),
    "siliconflow": ProviderSpec(
        key="siliconflow",
        label="硅基流动",
        default_base_url="https://api.siliconflow.cn/v1",
        example_models=("deepseek-ai/DeepSeek-V3", "Qwen/Qwen2.5-72B-Instruct"),
    ),
    "volcengine": ProviderSpec(
        key="volcengine",
        label="火山方舟 Doubao",
        default_base_url="https://ark.cn-beijing.volces.com/api/v3",
        example_models=("doubao-pro-32k", "doubao-lite-32k"),
    ),
    "openai": ProviderSpec(
        key="openai",
        label="OpenAI",
        default_base_url="https://api.openai.com/v1",
        example_models=("gpt-4o", "gpt-4o-mini"),
    ),
    "custom": ProviderSpec(
        key="custom",
        label="自定义 OpenAI 兼容接口（必须设置 ETF_AI_BASE_URL）",
        default_base_url="",
        example_models=(),
    ),
}

# 别名，方便记忆
_ALIASES = {
    "qwen": "dashscope",
    "tongyi": "dashscope",
    "glm": "zhipu",
    "bigmodel": "zhipu",
    "kimi": "moonshot",
    "doubao": "volcengine",
    "ark": "volcengine",
    "ali": "aliyun",
}


def normalize_provider_key(api_type: str) -> str:
    key = (api_type or "aliyun").strip().lower()
    return _ALIASES.get(key, key)


def get_provider(api_type: str) -> ProviderSpec:
    key = normalize_provider_key(api_type)
    if key not in PROVIDER_SPECS:
        known = ", ".join(sorted(PROVIDER_SPECS))
        raise ValueError(
            f"未知 ETF_AI_API_TYPE={api_type!r}。可选：{known}；"
            "或使用 custom 并设置 ETF_AI_BASE_URL。"
        )
    return PROVIDER_SPECS[key]


def resolve_chat_completions_url(api_type: str, base_url: str | None = None) -> str:
    """根据厂商预设 + 可选 BASE_URL 覆盖，得到完整 chat/completions URL。"""
    provider = get_provider(api_type)
    override = (base_url or "").strip() or None
    if provider.key == "custom" and not override:
        raise ValueError("ETF_AI_API_TYPE=custom 时必须设置 ETF_AI_BASE_URL。")
    return provider.chat_url(override)


def list_providers() -> list[ProviderSpec]:
    return list(PROVIDER_SPECS.values())
