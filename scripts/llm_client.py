from __future__ import annotations

import time
from typing import Any

import requests

try:
    from .run_context import RunContext
except ImportError:
    from run_context import RunContext


class LLMClient:
    def __init__(
        self,
        api_key: str,
        api_url: str,
        model_name: str,
        timeout: int = 120,
        max_retries: int = 2,
        run_context: RunContext | None = None,
    ):
        self.api_key = api_key
        self.api_url = api_url
        self.model_name = model_name
        self.timeout = timeout
        self.max_retries = max_retries
        self.run_context = run_context

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        artifact_prefix: str,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        if self.run_context:
            self.run_context.save_json(
                f"{artifact_prefix}_request",
                self.run_context.ai_dir,
                f"{artifact_prefix}_request.json",
                {"url": self.api_url, "payload": payload},
            )

        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = requests.post(self.api_url, headers=headers, json=payload, timeout=self.timeout)
                resp.raise_for_status()
                break
            except requests.exceptions.Timeout as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    raise TimeoutError(
                        f"AI请求超时：url={self.api_url}，model={self.model_name}，"
                        f"timeout={self.timeout}s，attempts={self.max_retries + 1}。"
                        "请检查网络是否能访问该国内endpoint，或在.env中调整 "
                        "ETF_AI_BASE_URL / ETF_AI_MODEL_NAME / ETF_AI_REQUEST_TIMEOUT。"
                    ) from exc
                time.sleep(2 * (attempt + 1))
            except requests.exceptions.ConnectionError as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    raise ConnectionError(
                        f"AI请求连接失败：url={self.api_url}，model={self.model_name}，"
                        f"attempts={self.max_retries + 1}。请检查网络、代理/VPN、base_url和服务商区域。"
                    ) from exc
                time.sleep(2 * (attempt + 1))
        else:
            raise RuntimeError(f"AI请求失败：{last_error}")

        response_json = resp.json()

        if self.run_context:
            self.run_context.save_json(
                f"{artifact_prefix}_response",
                self.run_context.ai_dir,
                f"{artifact_prefix}_response.json",
                response_json,
            )

        return response_json["choices"][0]["message"]["content"]
