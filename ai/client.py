"""AI 服务客户端工厂。"""

from openai import OpenAI


DEFAULT_BASE_URL = "https://api.deepseek.com"


def create_ai_client(api_key, base_url=None):
    """创建 OpenAI 兼容客户端，服务地址可由配置覆盖。"""
    return OpenAI(
        api_key=api_key,
        base_url=base_url or DEFAULT_BASE_URL,
    )
