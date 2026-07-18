"""Generate fixed GPT-SoVITS voice-style samples from the active Mio backend."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import wave


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from anime_assistant.infrastructure.config import load_config
from anime_assistant.speech.service import MioGPTSoVITSClient, SpeechSynthesisService


SAMPLES = (
    ("conversational", "neutral", "おかえり。今日はどんな一日だった？"),
    ("thoughtful", "neutral", "そうだな……少しずつ試してみるのがいいと思う。"),
    ("warm", "happy", "ありがとう。そう言ってもらえると、やっぱり嬉しいよ。"),
    ("cheerful", "happy", "やった。今日はすごく調子がいいぞ。"),
    ("bashful", "shy", "そ、そんなふうに言われると、ちょっと恥ずかしいよ。"),
    ("embarrassed", "shy", "もう、急にそんなこと言うなよ。顔が熱くなるだろ。"),
    ("concerned", "neutral", "大丈夫か？無理に元気なふりをしなくてもいいんだぞ。"),
    ("reassuring", "neutral", "焦らなくていいよ。少し休んでから、また一緒に考えよう。"),
    ("mild_annoyed", "neutral", "もう、からかうなよ。そんなこと言ってもだめだからな。"),
)


def main():
    output_dir = (
        ROOT
        / "data"
        / "mio_voice_dataset"
        / "gpt_sovits"
        / "v2proplus_v1"
        / "emotion_listening"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    config = load_config()
    client = MioGPTSoVITSClient(config)
    results = []
    try:
        for index, (voice_style, mood, text) in enumerate(SAMPLES, start=1):
            print(
                f"[{index}/{len(SAMPLES)}] 正在生成 {voice_style}...",
                flush=True,
            )
            speed_multiplier = SpeechSynthesisService._emotion_speed_multiplier(
                mood,
                0.7,
                "none",
                0.0,
                voice_style,
                0.75,
            )
            wav_data = client.synthesize(
                text,
                speed_scale=config.get("tts_speed_scale", 1.0) * speed_multiplier,
                volume_scale=config.get("tts_volume_scale", 1.0),
                mood=mood,
                voice_style=voice_style,
            )
            output_path = output_dir / f"mio_e15_{voice_style}.wav"
            output_path.write_bytes(wav_data)
            with wave.open(str(output_path), "rb") as wav_file:
                sample_rate = wav_file.getframerate()
                duration = wav_file.getnframes() / sample_rate
            results.append(
                {
                    "mood": mood,
                    "voice_style": voice_style,
                    "speed_multiplier": round(speed_multiplier, 3),
                    "text": text,
                    "output": str(output_path),
                    "sample_rate": sample_rate,
                    "duration_seconds": round(duration, 3),
                    "bytes": len(wav_data),
                }
            )
            print(
                f"[{index}/{len(SAMPLES)}] 已完成 {voice_style}: "
                f"{duration:.2f}s",
                flush=True,
            )
    finally:
        client.close()

    report = {
        "backend": "mio_gpt_sovits_v2proplus",
        "gpt_weights": config["mio_gpt_sovits_gpt_weights"],
        "sovits_weights": config["mio_gpt_sovits_sovits_weights"],
        "results": results,
    }
    report_path = output_dir / "report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
