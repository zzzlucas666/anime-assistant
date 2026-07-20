from anime_assistant.ai.client import create_ai_client
from anime_assistant.infrastructure.models import normalize_profile_extraction, parse_json_object
from anime_assistant.infrastructure.logging import get_logger
import re

logger = get_logger(__name__)


def extract_profile_info(
    api_key,
    model,
    user_message,
    base_url=None,
):

    client = create_ai_client(api_key, base_url)

    prompt = f"""
分析用户的话。

如果用户表达了：

- 喜欢某个东西
- 讨厌某个东西
- 名字
- 昵称
- 用户不再喜欢或不再讨厌某个东西
- 用户纠正了之前的名字、昵称或喜好

请提取出来。

返回JSON。

格式：

{{
    "action":"add_like",
    "value":"Oasis"
}}

可选action：

add_like
remove_like
add_dislike
remove_dislike
set_name
set_nickname
none

value 必须逐字来自用户输入，禁止补充、改写或推测用户没有说出的资料。

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
        parsed = parse_json_object(response.choices[0].message.content)
        result = normalize_profile_extraction(parsed)
        value = result.get("value", "")
        normalize = lambda text: re.sub(r"[^\w\u4e00-\u9fff]+", "", str(text or "").casefold())
        if result.get("action") != "none" and normalize(value) not in normalize(user_message):
            logger.warning("资料提取值缺少用户原话证据，已拒绝：%s", value)
            return {"action": "none", "value": ""}
        return result
    except Exception as e:
        logger.warning("资料提取结果校验失败（已跳过本轮资料更新）：%s", e)
        return normalize_profile_extraction(None)
