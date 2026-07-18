"""WAV data structures and Live2D mouth-envelope processing."""

from dataclasses import dataclass
from io import BytesIO
import math
import wave


class SpeechAudioError(RuntimeError):
    """Raised when synthesized audio cannot be decoded or combined."""


@dataclass(frozen=True)
class SpeechAudio:
    wav_data: bytes
    mouth_envelope: tuple[float, ...]
    envelope_window_ms: int
    spoken_text: str


def build_mouth_envelope(wav_data, window_ms=33):
    """Calculate a smooth 0..1 amplitude envelope from PCM WAV data."""
    try:
        import numpy as np

        with wave.open(BytesIO(wav_data), "rb") as wav_file:
            channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            sample_rate = wav_file.getframerate()
            raw = wav_file.readframes(wav_file.getnframes())
    except (ImportError, EOFError, wave.Error, ValueError):
        return ()

    dtype = {1: np.uint8, 2: np.int16, 4: np.int32}.get(sample_width)
    if dtype is None or not raw:
        return ()

    samples = np.frombuffer(raw, dtype=dtype).astype(np.float64)
    if sample_width == 1:
        samples -= 128.0
    if channels > 1:
        usable = len(samples) - (len(samples) % channels)
        samples = samples[:usable].reshape(-1, channels).mean(axis=1)

    window_size = max(1, int(sample_rate * window_ms / 1000))
    rms_values = []
    full_scale = float(2 ** (sample_width * 8 - 1))
    for start in range(0, len(samples), window_size):
        chunk = samples[start:start + window_size]
        if len(chunk):
            rms_values.append(math.sqrt(float(np.mean(chunk * chunk))) / full_scale)
    if not rms_values:
        return ()

    rms = np.asarray(rms_values)
    floor = float(np.percentile(rms, 18))
    ceiling = max(float(np.percentile(rms, 92)), floor + 1e-6)
    normalized = np.clip((rms - floor) / (ceiling - floor), 0.0, 1.0)
    shaped = np.sqrt(normalized) * 0.9
    return tuple(float(value) for value in shaped)


def combine_speech_audio(audio_batch, pause_ms=90):
    """Combine a reply's PCM WAV chunks into one gap-safe audio stream."""
    audio_batch = list(audio_batch or [])
    if not audio_batch:
        return None
    if len(audio_batch) == 1:
        return audio_batch[0]

    decoded = []
    reference = None
    for audio in audio_batch:
        try:
            with wave.open(BytesIO(audio.wav_data), "rb") as wav_file:
                params = (
                    wav_file.getnchannels(),
                    wav_file.getsampwidth(),
                    wav_file.getframerate(),
                    wav_file.getcomptype(),
                    wav_file.getcompname(),
                )
                frames = wav_file.readframes(wav_file.getnframes())
        except (EOFError, wave.Error) as exc:
            raise SpeechAudioError(f"Invalid WAV returned by TTS backend: {exc}") from exc
        if reference is None:
            reference = params
        elif params[:4] != reference[:4]:
            raise SpeechAudioError("TTS backend returned incompatible WAV formats")
        decoded.append(frames)

    channels, sample_width, sample_rate, compression, compression_name = reference
    pause_frames = max(0, int(sample_rate * max(0, pause_ms) / 1000))
    silence_sample = b"\x80" if sample_width == 1 else b"\x00" * sample_width
    silence = silence_sample * channels * pause_frames

    output = BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.setcomptype(compression, compression_name)
        for index, frames in enumerate(decoded):
            if index:
                wav_file.writeframesraw(silence)
            wav_file.writeframesraw(frames)
    wav_data = output.getvalue()
    return SpeechAudio(
        wav_data=wav_data,
        mouth_envelope=build_mouth_envelope(wav_data),
        envelope_window_ms=33,
        spoken_text="".join(audio.spoken_text for audio in audio_batch),
    )
