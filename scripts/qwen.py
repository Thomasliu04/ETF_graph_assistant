import os
from openai import OpenAI

try:
    api_key = os.getenv("ETF_AI_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("请先设置环境变量 ETF_AI_API_KEY 或 DASHSCOPE_API_KEY")

    client = OpenAI(
        api_key=api_key,
        # 以下为华北2（北京）地域的URL，各地域的URL不同。调用时请将WorkspaceId替换为真实的业务空间ID。
        base_url="https://ws-809e4eujqwysgybs.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
    )

    completion = client.chat.completions.create(
        model="qwen3.7-plus",  # 模型列表: https://help.aliyun.com/model-studio/getting-started/models
        messages=[
            {'role': 'system', 'content': 'You are a helpful assistant.'},
            {'role': 'user', 'content': '你是谁？'}
        ],
        timeout=30  # 增加超时时间，防止网络慢直接断连
    )
    print(completion.choices[0].message.content)
except Exception as e:
    print(f"错误信息：{e}")
    print("请参考文档：https://help.aliyun.com/model-studio/developer-reference/error-code")
