"""Stream WAV audio to a HomePod via RAOP.

For v0.1 we save the synthesized audio to a known file and emit a log line
that the voice-bridge service can pick up. A future version will use pyatv
or a similar library to negotiate the RAOP session and push audio frames.

Why stub-for-now: pyatv's push API requires setup code (Settings → AirPlay →
Security on the HomePod) and a complex handshake. The skeleton is here so
; the rest of the agent's voice flow can be exercised end-to-end without
that handshake — the audio lands at a known path on disk.

The macOS helper `voice/raop_push.py` (run separately by the user) reads
that path and pushes it to the HomePod via the system audio stack (e.g.,
a shairport-sync receiver on the HomePod, or an Airfoil-style hop).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from shared.log import get_logger
from shared.util import state_dir

from .discover import HomePodInfo

log = get_logger("voice.stream")

AUDIO_DROP = state_dir() / "voice-drop.wav"


async def stream_wav(pod: HomePodInfo, wav_bytes: bytes) -> None:
    """Persist the audio for the macOS push helper to pick up."""
    AUDIO_DROP.parent.mkdir(parents=True, exist_ok=True)
    AUDIO_DROP.write_bytes(wav_bytes)
    log.info(
        "stream.dropped",
        path=str(AUDIO_DROP),
        bytes=len(wav_bytes),
        pod=pod.name,
        pod_address=pod.address,
    )


async def say(text: str, pod: HomePodInfo | None = None) -> None:
    """Convenience: synthesize TTS + drop for the macOS push helper."""
    from .tts import synthesize

    if pod is None:
        from .discover import find_homepod

        pod = await find_homepod()
    if not pod:
        log.warning("say.no_pod")
        return

    tts = await synthesize(text)
    log.info("say.tts", bytes=len(tts.audio), pod=pod.name)
    await stream_wav(pod, tts.audio)