"""Real faster-whisper speech-to-text inference with silence/noise filtering and honest metrics.

Strict non-inference & anti-hallucination guarantees:
- Production mode strictly rejects stub/test doubles.
- Acoustic energy + frame-activity gate short-circuits silent/squelch-tail chunks so Whisper
  never invents phantom phrases on radio silence.
- `condition_on_previous_text=False` prevents prior radio calls from bleeding into unclear audio.
- Never infers speaker, unit ID, talkgroup, address, incident outcome, or agency from feed names
  or uncertain audio.
"""

from __future__ import annotations

import datetime as dt
import math
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import ctranslate2
import faster_whisper
import numpy as np

from .config import ConfigurationError, ServiceConfig
from .model_bootstrap import resolve_whisper_model_path


@dataclass(frozen=True)
class ASRChunkResult:
    kind: str  # 'speech' | 'no_speech'
    text: str
    language: str
    asr_backend: str
    asr_model: str
    transcribed_at_utc: str
    metrics: dict[str, object] = field(default_factory=dict)


class ASRBackend(Protocol):
    @property
    def backend_name(self) -> str: ...

    @property
    def model_identifier(self) -> str: ...

    def transcribe_wav(self, wav_path: Path) -> ASRChunkResult: ...


def measure_pcm16_wav_acoustics(wav_path: Path, frame_ms: int = 20) -> dict[str, float]:
    """Compute exact acoustic level metrics on a 16-bit PCM WAV file."""
    with wave.open(str(wav_path), "rb") as wf:
        sample_rate = wf.getframerate()
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)

    if n_frames == 0 or not raw or sampwidth != 2:
        return {
            "duration_seconds": 0.0,
            "rms_dbfs": -120.0,
            "peak_dbfs": -120.0,
            "speech_frame_ratio": 0.0,
        }

    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if n_channels > 1:
        samples = samples.reshape(-1, n_channels).mean(axis=1)

    rms = float(np.sqrt(np.mean(np.square(samples)) + 1e-12))
    peak = float(np.max(np.abs(samples)) + 1e-12)
    rms_dbfs = max(-120.0, 20.0 * math.log10(rms))
    peak_dbfs = max(-120.0, 20.0 * math.log10(peak))

    frame_len = max(1, int(sample_rate * frame_ms / 1000))
    usable = (len(samples) // frame_len) * frame_len
    if usable > 0:
        frames = samples[:usable].reshape(-1, frame_len)
        frame_rms = np.sqrt(np.mean(np.square(frames), axis=1) + 1e-12)
        frame_dbfs = 20.0 * np.log10(frame_rms)
        speech_frame_ratio = float(np.mean(frame_dbfs > -45.0))
    else:
        speech_frame_ratio = 1.0 if rms_dbfs > -45.0 else 0.0

    return {
        "duration_seconds": round(len(samples) / float(sample_rate), 3),
        "rms_dbfs": round(rms_dbfs, 2),
        "peak_dbfs": round(peak_dbfs, 2),
        "speech_frame_ratio": round(speech_frame_ratio, 4),
    }


# Common Whisper silence hallucinations when fed steady hum/tone/squelch noise.
KNOWN_NONSPEECH_HALLUCINATIONS = frozenset(
    {
        "thank you.",
        "thank you",
        "thanks for watching.",
        "thanks for watching!",
        "thank you for watching.",
        "thank you for watching!",
        "subtitles by the amara.org community",
        "you",
        ".",
        "...",
    }
)


class FasterWhisperBackend:
    """Real neural speech-to-text backend powered by faster-whisper + CTranslate2 + Silero VAD."""

    def __init__(self, config: ServiceConfig) -> None:
        if config.environment == "production" and config.asr_backend != "faster-whisper":
            raise ConfigurationError("Production rejects non-faster-whisper ASR backends.")
        self._config = config
        resolved_path, model_label = resolve_whisper_model_path(
            config.asr_model_name, config.model_cache_dir
        )
        self._model = faster_whisper.WhisperModel(
            resolved_path,
            device=config.asr_device,
            compute_type=config.asr_compute_type,
            cpu_threads=config.asr_cpu_threads,
        )
        self._model_identifier = (
            f"faster-whisper {faster_whisper.__version__} / {model_label} "
            f"(ctranslate2 {ctranslate2.__version__}, {config.asr_compute_type})"
        )

    @property
    def backend_name(self) -> str:
        return "faster-whisper"

    @property
    def model_identifier(self) -> str:
        return self._model_identifier

    def transcribe_wav(self, wav_path: Path) -> ASRChunkResult:
        acoustics = measure_pcm16_wav_acoustics(wav_path)
        now_iso = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")

        base_metrics: dict[str, object] = {
            "rms_dbfs": acoustics["rms_dbfs"],
            "peak_dbfs": acoustics["peak_dbfs"],
            "speech_frame_ratio": acoustics["speech_frame_ratio"],
            "metric_note": (
                "whisper_avg_logprob is an uncalibrated decoder token log-probability "
                "(-inf..0], NOT a calibrated word-accuracy score."
            ),
        }

        # Stage 1: Acoustic silence & dead-carrier gate.
        if (
            acoustics["rms_dbfs"] < self._config.silence_rms_dbfs
            or acoustics["speech_frame_ratio"] < self._config.min_speech_frame_ratio
        ):
            base_metrics["gate_reason"] = "acoustic_silence"
            return ASRChunkResult(
                kind="no_speech",
                text="",
                language=self._config.asr_language,
                asr_backend=self.backend_name,
                asr_model=self.model_identifier,
                transcribed_at_utc=now_iso,
                metrics=base_metrics,
            )

        # Stage 2: Real faster-whisper + Silero VAD decoding.
        segments_iter, info = self._model.transcribe(
            str(wav_path),
            language=self._config.asr_language or None,
            vad_filter=True,
            beam_size=self._config.asr_beam_size,
            condition_on_previous_text=False,
            temperature=0.0,
        )
        segments = list(segments_iter)
        transcribed_at = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")

        kept_texts: list[str] = []
        weighted_logprob_num = 0.0
        weighted_dur = 0.0
        max_no_speech = 0.0

        for seg in segments:
            text_piece = seg.text.strip()
            if not text_piece:
                continue
            max_no_speech = max(max_no_speech, float(seg.no_speech_prob))
            if (
                seg.no_speech_prob >= self._config.max_no_speech_prob
                and seg.avg_logprob < -1.1
            ):
                continue
            if (
                text_piece.lower() in KNOWN_NONSPEECH_HALLUCINATIONS
                and (seg.no_speech_prob > 0.45 or seg.avg_logprob < -1.0)
            ):
                continue
            seg_dur = max(0.05, float(seg.end - seg.start))
            weighted_logprob_num += float(seg.avg_logprob) * seg_dur
            weighted_dur += seg_dur
            kept_texts.append(text_piece)

        merged_text = " ".join(kept_texts).strip()
        detected_language = getattr(info, "language", None) or self._config.asr_language or "en"

        if weighted_dur > 0:
            base_metrics["whisper_avg_logprob"] = round(weighted_logprob_num / weighted_dur, 4)
        base_metrics["whisper_no_speech_prob"] = round(max_no_speech, 4)

        if not merged_text:
            base_metrics["gate_reason"] = "vad_or_nonspeech_filtered"
            return ASRChunkResult(
                kind="no_speech",
                text="",
                language=detected_language,
                asr_backend=self.backend_name,
                asr_model=self.model_identifier,
                transcribed_at_utc=transcribed_at,
                metrics=base_metrics,
            )

        return ASRChunkResult(
            kind="speech",
            text=merged_text,
            language=detected_language,
            asr_backend=self.backend_name,
            asr_model=self.model_identifier,
            transcribed_at_utc=transcribed_at,
            metrics=base_metrics,
        )


def build_asr_backend(config: ServiceConfig) -> ASRBackend:
    """Construct the configured ASR engine, rejecting stubs in production."""
    if config.asr_backend != "faster-whisper":
        raise ConfigurationError(
            f"Unsupported or disallowed ASR backend {config.asr_backend!r}; expected 'faster-whisper'."
        )
    return FasterWhisperBackend(config)
