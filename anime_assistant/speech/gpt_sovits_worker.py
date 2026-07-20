"""GPT-SoVITS V2ProPlus inference worker for the Python 3.14 GUI.

The model stays resident in an isolated Python 3.10 process. Requests and
events use the same newline-delimited protocol as the Style-Bert worker.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import traceback


EVENT_PREFIX = "MIO_TTS_EVENT\t"


def force_all_japanese_segments(lang_segmenter):
    """让 ``all_ja`` 真正把拉丁字母片段也交给日文前端。

    GPT-SoVITS 的 LangSegmenter 会在应用默认语言之前优先把纯英文片段
    标记成 ``en``。这会延迟导入 g2p_en，并在离线环境中尝试下载 NLTK
    cmudict。Mio 的输出本来就是日语；交给 pyopenjtalk 处理拉丁字母既能
    保留名称，又不会让一次英文歌名使整条语音失败。
    """
    if getattr(lang_segmenter, "_mio_all_ja_forced", False):
        return

    original_get_texts = lang_segmenter.getTexts

    def get_texts(text, default_lang=""):
        segments = original_get_texts(text, default_lang)
        if default_lang == "ja":
            for segment in segments:
                if isinstance(segment, dict):
                    segment["lang"] = "ja"
        return segments

    lang_segmenter.getTexts = staticmethod(get_texts)
    lang_segmenter._mio_all_ja_forced = True


def emit(event_type, **payload):
    print(
        EVENT_PREFIX + json.dumps({"type": event_type, **payload}, ensure_ascii=False),
        flush=True,
    )


def apply_output_gain(audio, volume, peak_limit=0.98):
    """Apply output gain without hard-clipping generated speech.

    GPT-SoVITS normally returns floating-point audio, but a few expressive
    generations can exceed full scale.  Direct clipping turns those peaks into
    audible crackle, so preserve the waveform and lower the complete result
    just enough to leave a small amount of headroom.
    """
    scaled = audio * volume
    if getattr(scaled, "size", 0):
        peak = float(abs(scaled).max())
        if peak > peak_limit:
            scaled = scaled * (peak_limit / peak)
    return scaled


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--gpt-weights", required=True)
    parser.add_argument("--sovits-weights", required=True)
    parser.add_argument("--references", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--device", default="cuda")
    return parser.parse_args()


def main():
    args = parse_args()
    repo_path = Path(args.repo).resolve()
    sys.path.insert(0, str(repo_path))
    sys.path.insert(0, str(repo_path / "GPT_SoVITS"))
    os.chdir(repo_path)

    try:
        emit("status", stage="imports", message="正在加载 GPT-SoVITS 推理依赖")
        import jieba
        import jieba.posseg
        import numpy as np
        import soundfile as sf
        import torch
        import torchaudio

        # Japanese inference still imports the optional accelerated Chinese
        # tokenizer. The regular implementation exposes the same API.
        sys.modules.setdefault("jieba_fast", jieba)
        sys.modules.setdefault("jieba_fast.posseg", jieba.posseg)

        # Current Torchaudio routes loading through TorchCodec on Windows.
        # All reference files are PCM WAV, so SoundFile is sufficient.
        def load_wav_without_torchcodec(path):
            audio, sample_rate = sf.read(path, dtype="float32", always_2d=True)
            return torch.from_numpy(audio.T.copy()), sample_rate

        torchaudio.load = load_wav_without_torchcodec

        from GPT_SoVITS.TTS_infer_pack.TTS import TTS, TTS_Config
        from text.LangSegmenter import LangSegmenter

        force_all_japanese_segments(LangSegmenter)

        emit("status", stage="references", message="正在验证 Mio 情绪参考音频")
        references = json.loads(args.references)
        if not isinstance(references, dict) or "neutral" not in references:
            raise ValueError("GPT-SoVITS references must include neutral")
        for mood, reference in references.items():
            if not isinstance(reference, dict):
                raise ValueError(f"Invalid reference entry: {mood}")
            audio_path = Path(str(reference.get("audio", "")))
            prompt = str(reference.get("prompt", "")).strip()
            if not audio_path.is_file() or not prompt:
                raise FileNotFoundError(f"Invalid {mood} reference: {audio_path}")

        emit("status", stage="model", message="正在加载 Mio GPT 与 SoVITS 权重")
        config = TTS_Config(
            {
                "custom": {
                    "device": args.device,
                    "is_half": args.device.startswith("cuda"),
                    "version": "v2ProPlus",
                    "t2s_weights_path": str(Path(args.gpt_weights).resolve()),
                    "vits_weights_path": str(Path(args.sovits_weights).resolve()),
                    "cnhuhbert_base_path": str(
                        repo_path
                        / "GPT_SoVITS"
                        / "pretrained_models"
                        / "chinese-hubert-base"
                    ),
                    "bert_base_path": str(
                        repo_path
                        / "GPT_SoVITS"
                        / "pretrained_models"
                        / "chinese-roberta-wwm-ext-large"
                    ),
                }
            }
        )
        pipeline = TTS(config)
        output_dir = Path(args.output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        emit("fatal", message=str(exc), detail=traceback.format_exc(limit=8))
        return 1

    emit(
        "ready",
        pid=os.getpid(),
        gpt=Path(args.gpt_weights).name,
        sovits=Path(args.sovits_weights).name,
    )
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
            emit("error", id=request_id, message="Empty GPT-SoVITS request")
            continue

        try:
            mood = str(request.get("mood", "neutral")).strip().lower()
            voice_style = str(
                request.get("voice_style", "conversational")
            ).strip().lower()
            reference = references.get(
                voice_style,
                references.get(mood, references["neutral"]),
            )
            speed = max(0.5, min(2.0, float(request.get("speed_scale", 1.0))))
            volume = max(0.0, min(2.0, float(request.get("volume_scale", 1.0))))
            synthesis_request = {
                "text": text,
                "text_lang": "all_ja",
                "ref_audio_path": reference["audio"],
                "prompt_text": reference["prompt"],
                "prompt_lang": "all_ja",
                "top_k": 15,
                "top_p": 1.0,
                "temperature": 1.0,
                "text_split_method": "cut5",
                "batch_size": 1,
                "split_bucket": False,
                "speed_factor": speed,
                "seed": 42,
                "parallel_infer": False,
                "repetition_penalty": 1.35,
                "super_sampling": False,
                "streaming_mode": False,
            }
            sample_rate, audio = next(pipeline.run(synthesis_request))
            audio = np.asarray(audio)
            if np.issubdtype(audio.dtype, np.integer):
                full_scale = float(max(abs(np.iinfo(audio.dtype).min), np.iinfo(audio.dtype).max))
                audio = audio.astype(np.float32) / full_scale
            else:
                audio = audio.astype(np.float32)
            audio = apply_output_gain(audio, volume)
            output_path = output_dir / f"{request_id}.wav"
            sf.write(output_path, audio, sample_rate, subtype="PCM_16")
            emit(
                "result",
                id=request_id,
                path=str(output_path),
                mood=mood,
                voice_style=voice_style,
                bytes=output_path.stat().st_size,
            )
        except Exception as exc:
            emit(
                "error",
                id=request_id,
                message=str(exc),
                detail=traceback.format_exc(limit=8),
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
