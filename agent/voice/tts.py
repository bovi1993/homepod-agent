"""Local TTS synthesis.

Two engines:
  - pyttsx3 — fully offline, no network, low quality
  - piper — better quality, also local, requires model file

For v0.1 we default to pyttsx3 if available, else fall back to a stub that
emits a sine wave so the audio pipeline can be smoke-tested without a real
TTS engine.
"""

from __future__ import annotations

import asyncio
import io
import wave
from dataclasses import dataclass
from typing import Any

from shared.log import get_logger

log = get_logger("voice.tts")


@dataclass
class TtsResult:
    audio: bytes
    sample_rate: int
    sample_width: int
    channels: int
    format: str  # "wav" | "pcm"


async def synthesize(
    text: str, voice: str | None = None, engine: str = "auto"
) -> TtsResult:
    """Synthesize speech to WAV bytes."""
    if engine in ("auto", "pyttsx3"):
        out = await asyncio.to_thread(_pyttsx3_synth, text, voice)
        if out:
            return out
    if engine in ("auto", "piper"):
        out = await asyncio.to_thread(_piper_synth, text, voice)
        if out:
            return out
    log.warning("tts.no_engine", hint="returning stub sine wave")
    return _stub_sine(text)


def _pyttsx3_synth(text: str, voice: str | None) -> TtsResult | None:
    try:
        import pyttsx3
    except ImportError:
        return None
    try:
        engine = pyttsx3.init()
        if voice:
            engine.setProperty("voice", voice)
        buf = io.BytesIO()
        engine.save_to_file(text, "/tmp/_tts.wav")
        engine.runAndWait()
        with open("/tmp/_tts.wav", "rb") as f:
            data = f.read()
        # Read sample rate from the WAV header.
        with wave.open("/tmp/_tts.wav", "rb") as w:
            sr = w.getframerate()
            sw = w.getsampwidth()
            ch = w.getnchannels()
        return TtsResult(audio=data, sample_rate=sr, sample_width=sw, channels=ch, format="wav")
    except Exception as e:
        log.warning("tts.pyttsx3_failed", error=str(e))
        return None


def _piper_synth(text: str, voice: str | None) -> TtsResult | None:
    try:
        # piper is heavy — only import if explicitly requested
        pass
    except ImportError:
        return None
    return None


def _stub_sine(text: str) -> TtsResult:
    """Generate a 1s 440Hz sine wave as a 'voice' placeholder."""
    import math

    sr = 16000
    duration = min(2.0, max(0.5, len(text) * 0.05))
    n = int(sr * duration)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        for i in range(n):
            v = int(32767 * 0.1 * math.sin(2 * math.pi * 440 * i / sr))
            w.writeframes(v.to_bytes(2, "little", signed=True))
    return TtsResult(audio=buf.getvalue(), sample_rate=sr, sample_width=2, channels=1, format="wav")