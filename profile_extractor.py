from openai import OpenAI
import json
from logger_utils import get_logger

logger = get_logger(__name__)


def extract_profile_info(
    api_key,
    model,
    user_message
):

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com"
    )

    prompt = f"""
分析用户的话。

如果用户表达了：

- 喜欢某个东西
- 讨厌某个东西
- 名字
- 昵称

请提取出来。

返回JSON。

格式：

{{
    "action":"add_like",
    "value":"Oasis"
}}

可选action：

add_like
add_dislike
set_name
set_nickname
none

用户输入：

{user_message}

只返回JSON。
"""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": prompt
                }
            ]
        )
    except Exception as e:
        logger.warning("资料提取调用失败（已跳过本轮资料更新）：%s", e)
        return {
            "action": "none",
            "value": ""
        }

    try:
        return json.loads(
            response.choices[0].message.content
        )
    except Exception:
        return {
            "action": "none",
            "value": ""
        }