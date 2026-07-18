"""Style-Bert-VITS2 inference worker used by the Python 3.14 GUI process.

The worker runs inside the isolated Python 3.10 training environment and keeps
the model resident between requests.  Communication uses newline-delimited
JSON events on stdin/stdout; model logs may share stdout, so protocol messages
always carry a distinct prefix.
"""

from __future__ import annotations

import argparse
from io import BytesIO
import json
import os
from pathlib import Path
import sys
import traceback
import wave


EVENT_PREFIX = "MIO_TTS_EVENT\t"


def emit(event_type, **payload):
    message = {"type": event_type, **payload}
    print(EVENT_PREFIX + json.dumps(message, ensure_ascii=False), flush=True)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--style-vectors", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--sdp-ratio", type=float, default=0.35)
    parser.add_argument("--noise", type=float, default=0.5)
    parser.add_argument("--noise-w", type=float, default=0.7)
    parser.add_argument("--style-weight", type=float, default=1.0)
    return parser.parse_args()


def encode_wav(sample_rate, audio, volume_scale):
    import numpy as np

    audio = audio.astype(np.float32) * max(0.0, min(2.0, float(volume_scale)))
    audio = np.clip(audio, -32768.0, 32767.0).astype(np.int16)
    output = BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio.tobytes())
    return output.getvalue()


def main():
    args = parse_args()
    repo_path = Path(args.repo).resolve()
    sys.path.insert(0, str(repo_path))
    os.chdir(repo_path)

    try:
        from style_bert_vits2.constants import Languages
        from style_bert_vits2.tts_model import TTSModel

        model = TTSModel(
            model_path=Path(args.model),
            config_path=Path(args.config),
            style_vec_path=Path(args.style_vectors),
            device=args.device,
        )
        model.load()
        output_dir = Path(args.output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        emit("fatal", message=str(exc), detail=traceback.format_exc(limit=5))
        return 1

    emit("ready", pid=os.getpid(), model=Path(args.model).name)
    for raw_line in sys.stdin:
        try:
            request = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if request.get("command") == "shutdown":
            emit("stopped")
            return 0

        request_id = str(request.get("id", ""))
        text = str(request.get("text", "")).strip()
        if not request_id or not text:
            emit("error", id=request_id, message="Empty Mio TTS request")
            continue

        try:
            speed_scale = max(0.5, min(2.0, float(request.get("speed_scale", 1.0))))
            sample_rate, audio = model.infer(
                text,
                language=Languages.JP,
                speaker_id=0,
                sdp_ratio=args.sdp_ratio,
                noise=args.noise,
                noise_w=args.noise_w,
                length=1.0 / speed_scale,
                style="Neutral",
                style_weight=args.style_weight,
            )
            wav_data = encode_wav(
                sample_rate,
                audio,
                request.get("volume_scale", 1.0),
            )
            output_path = output_dir / f"{request_id}.wav"
            output_path.write_bytes(wav_data)
            emit("result", id=request_id, path=str(output_path), bytes=len(wav_data))
        except Exception as exc:
            emit(
                "error",
                id=request_id,
                message=str(exc),
                detail=traceback.format_exc(limit=5),
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
