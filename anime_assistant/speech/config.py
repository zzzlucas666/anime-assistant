"""Pure speech configuration defaults.

This module intentionally imports no speech backend or AI client.  Configuration
loading can therefore use these defaults without starting or importing the TTS
runtime and its optional dependencies.
"""

DEFAULT_AIVIS_ENDPOINT = "http://127.0.0.1:10101"
DEFAULT_AIVIS_TIMEOUT_SECONDS = 60.0
DEFAULT_AIVIS_MAX_CHARS = 56
DEFAULT_LOCAL_TTS_RETRY_ATTEMPTS = 1
DEFAULT_TTS_BACKEND = "aivis"
MIO_TTS_BACKEND = "mio_style_bert_vits2"
MIO_GPT_SOVITS_BACKEND = "mio_gpt_sovits_v2proplus"

DEFAULT_MIO_TTS_PYTHON = (
    "data/training_tools/Style-Bert-VITS2/venv/Scripts/python.exe"
)
DEFAULT_MIO_TTS_WORKER = "anime_assistant/speech/style_bert_worker.py"
DEFAULT_MIO_TTS_REPO = "data/training_tools/Style-Bert-VITS2"
DEFAULT_MIO_TTS_MODEL = (
    "data/mio_voice_dataset/style_bert_vits2/model_assets/mio_pilot_v1/"
    "mio_pilot_v1_e43_s2000.safetensors"
)
DEFAULT_MIO_TTS_CONFIG = (
    "data/mio_voice_dataset/style_bert_vits2/model_assets/mio_pilot_v1/config.json"
)
DEFAULT_MIO_TTS_STYLE_VECTORS = (
    "data/mio_voice_dataset/style_bert_vits2/model_assets/mio_pilot_v1/"
    "style_vectors.npy"
)

DEFAULT_MIO_GPT_SOVITS_PYTHON = (
    "data/training_tools/GPT-SoVITS/.venv/Scripts/python.exe"
)
DEFAULT_MIO_GPT_SOVITS_WORKER = "anime_assistant/speech/gpt_sovits_worker.py"
DEFAULT_MIO_GPT_SOVITS_REPO = "data/training_tools/GPT-SoVITS"
DEFAULT_MIO_GPT_SOVITS_GPT_WEIGHTS = (
    "data/mio_voice_dataset/gpt_sovits/v2proplus_v1/weights/gpt/"
    "mio_v2proplus_v1-e15.ckpt"
)
DEFAULT_MIO_GPT_SOVITS_SOVITS_WEIGHTS = (
    "data/mio_voice_dataset/gpt_sovits/v2proplus_v1/weights/sovits/"
    "mio_v2proplus_v1_e8_s768.pth"
)

DEFAULT_MIO_GPT_SOVITS_REFERENCES = {
    "neutral": {
        "audio": (
            "data/mio_voice_dataset/style_bert_vits2/Data/mio_pilot_v1/wavs/"
            "mio_pilot_0002.wav"
        ),
        "prompt": "今何時だ。おはよう。こんにちは。お昼だぞ。おやつ。",
    },
    "happy": {
        "audio": (
            "data/mio_voice_dataset/style_bert_vits2/Data/mio_pilot_v1/wavs/"
            "mio_pilot_0045.wav"
        ),
        "prompt": "うまく演奏できた。ちょっと満足かも。今日は調子いいな。",
    },
    "shy": {
        "audio": (
            "data/mio_voice_dataset/style_bert_vits2/Data/mio_pilot_v1/wavs/"
            "mio_pilot_0021.wav"
        ),
        "prompt": "見られてる？夢みたいだ。うまくできたかな。楽しんで。",
    },
    "sad": {
        "audio": (
            "data/mio_voice_dataset/style_bert_vits2/Data/mio_pilot_v1/wavs/"
            "mio_pilot_0046.wav"
        ),
        "prompt": "うまく弾けなかった。今日はダメみたいだ。",
    },
    "tired": {
        "audio": (
            "data/mio_voice_dataset/style_bert_vits2/Data/mio_pilot_v1/wavs/"
            "mio_pilot_0047.wav"
        ),
        "prompt": "食べ過ぎちゃった。眠くなってきた。",
    },
    "conversational": {
        "audio": (
            "data/mio_voice_dataset/style_bert_vits2/Data/mio_pilot_v1/wavs/"
            "mio_pilot_0014.wav"
        ),
        "prompt": "よし、うまくいったな。うん、ありがとう。じゃあな、また。",
    },
    "thoughtful": {
        "audio": (
            "data/mio_voice_dataset/style_bert_vits2/Data/mio_pilot_v1/wavs/"
            "mio_pilot_0011.wav"
        ),
        "prompt": "いろいろあるなぁ。どれにしよう。迷うなぁ。これなんかどうかな。",
    },
    "warm": {
        "audio": (
            "data/mio_voice_dataset/style_bert_vits2/Data/mio_pilot_v1/wavs/"
            "mio_pilot_0014.wav"
        ),
        "prompt": "よし、うまくいったな。うん、ありがとう。じゃあな、また。",
    },
    "cheerful": {
        "audio": (
            "data/mio_voice_dataset/style_bert_vits2/Data/mio_pilot_v1/wavs/"
            "mio_pilot_0045.wav"
        ),
        "prompt": "うまく演奏できた。ちょっと満足かも。今日は調子いいな。",
    },
    "excited": {
        "audio": (
            "data/mio_voice_dataset/style_bert_vits2/Data/mio_pilot_v1/wavs/"
            "mio_pilot_0026.wav"
        ),
        "prompt": "行ってね。ノリノリで、ハイテンションでゴー。飛ばすぞ。全力でついてこい。",
    },
    "bashful": {
        "audio": (
            "data/mio_voice_dataset/style_bert_vits2/Data/mio_pilot_v1/wavs/"
            "mio_pilot_0021.wav"
        ),
        "prompt": "見られてる？夢みたいだ。うまくできたかな。楽しんで。",
    },
    "embarrassed": {
        "audio": (
            "data/mio_voice_dataset/style_bert_vits2/Data/mio_pilot_v1/wavs/"
            "mio_pilot_0029.wav"
        ),
        "prompt": "恥ずかしい。もう今日は帰ろうかな。こんなんじゃ武道館なんて。",
    },
    "concerned": {
        "audio": (
            "data/mio_voice_dataset/style_bert_vits2/Data/mio_pilot_v1/wavs/"
            "mio_pilot_0011.wav"
        ),
        "prompt": "いろいろあるなぁ。どれにしよう。迷うなぁ。これなんかどうかな。",
    },
    "reassuring": {
        "audio": (
            "data/mio_voice_dataset/style_bert_vits2/Data/mio_pilot_v1/wavs/"
            "mio_pilot_0014.wav"
        ),
        "prompt": "よし、うまくいったな。うん、ありがとう。じゃあな、また。",
    },
    "curious": {
        "audio": (
            "data/mio_voice_dataset/style_bert_vits2/Data/mio_pilot_v1/wavs/"
            "mio_pilot_0011.wav"
        ),
        "prompt": "いろいろあるなぁ。どれにしよう。迷うなぁ。これなんかどうかな。",
    },
    "surprised": {
        "audio": (
            "data/mio_voice_dataset/style_bert_vits2/Data/mio_pilot_v1/wavs/"
            "mio_pilot_0033.wav"
        ),
        "prompt": "大凶だ。なんだかドキドキすることがあるかも。テストがうまくいきそう。",
    },
    "mild_annoyed": {
        "audio": (
            "data/mio_voice_dataset/style_bert_vits2/Data/mio_pilot_v1/wavs/"
            "mio_pilot_0030.wav"
        ),
        "prompt": "まだまだだな。もうダメかも。なんでだよ。",
    },
    "serious": {
        "audio": (
            "data/mio_voice_dataset/style_bert_vits2/Data/mio_pilot_v1/wavs/"
            "mio_pilot_0030.wav"
        ),
        "prompt": "まだまだだな。もうダメかも。なんでだよ。",
    },
    "disappointed": {
        "audio": (
            "data/mio_voice_dataset/style_bert_vits2/Data/mio_pilot_v1/wavs/"
            "mio_pilot_0046.wav"
        ),
        "prompt": "うまく弾けなかった。今日はダメみたいだ。",
    },
}

DEFAULT_MOOD_SPEAKERS = {
    "neutral": 1878365376,
    "happy": 1878365377,
    "shy": 1878365377,
    "sad": 1878365378,
    "tired": 1878365379,
}
