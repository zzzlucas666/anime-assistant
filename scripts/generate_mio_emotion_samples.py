"""Generate fixed GPT-SoVITS emotion samples from the active Mio backend."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import wave


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config_loader import load_config
from tts_service import MioGPTSoVITSClient


SAMPLES = {
    "neutral": "おかえり。今日はどんな一日だった？",
    "happy": "やった！今日はすごく調子がいいぞ。一緒に練習しよう！",
    "shy": "あ、あんまりじっと見ないでよ。恥ずかしいから……。",
    "sad": "今日はうまく弾けなかった。もう少し練習しないとだめだな……。",
    "tired": "今日はちょっと疲れたな。少しだけ休んでもいい？",
}


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
        for mood, text in SAMPLES.items():
            wav_data = client.synthesize(
                text,
                speed_scale=config.get("tts_speed_scale", 1.0),
                volume_scale=config.get("tts_volume_scale", 1.0),
                mood=mood,
            )
            output_path = output_dir / f"mio_e15_{mood}.wav"
            output_path.write_bytes(wav_data)
            with wave.open(str(output_path), "rb") as wav_file:
                sample_rate = wav_file.getframerate()
                duration = wav_file.getnframes() / sample_rate
            results.append(
                {
                    "mood": mood,
                    "text": text,
                    "output": str(output_path),
                    "sample_rate": sample_rate,
                    "duration_seconds": round(duration, 3),
                    "bytes": len(wav_data),
                }
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
