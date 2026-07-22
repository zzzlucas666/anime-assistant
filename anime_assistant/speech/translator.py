"""Text translation used only by the speech pipeline."""

from anime_assistant.ai.client import create_ai_client
from anime_assistant.speech.text import contains_japanese_kana, prepare_spoken_text


class JapaneseSpeechTranslator:
    """把界面中的中文回复转换成仅供语音后端发声的自然日语。"""

    def __init__(self, api_key, model, base_url=None):
        self.model = model
        self.client = create_ai_client(api_key, base_url)

    def translate(self, text):
        cleaned = prepare_spoken_text(text)
        if not cleaned or contains_japanese_kana(cleaned):
            return cleaned

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "把用户提供的角色台词翻译成自然、口语化的日语。"
                        "保持原本的语气、情绪和句子数量，不添加解释、括号动作、"
                        "说话人名称或引号，只输出日语台词。英文人名、乐队名、"
                        "歌名和缩写也要转写成自然的日语片假名，不保留拉丁字母。"
                    ),
                },
                {"role": "user", "content": cleaned},
            ],
            temperature=0.2,
        )
        content = response.choices[0].message.content if response.choices else ""
        return prepare_spoken_text(content)
