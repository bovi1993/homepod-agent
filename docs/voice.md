# Voice pipeline

## Input (iPad → agent)

The iPad (`ipad-listen/` Swift app) acts as the voice-input device. The HomePod's
microphone is locked to Siri and cannot be used by third-party apps.

### How it works

1. iPad runs `IPadListen.app` continuously (always-on).
2. AVAudioEngine captures mic at 16kHz mono PCM.
3. Audio is Opus-compressed to ~32 kbps to fit WebSocket bandwidth.
4. Frames stream over WebSocket to `agent/llm/voice_input.py` on the Mac.
5. Whisper small model on the Mac transcribes (latency: ~500ms per utterance).
6. Transcript is fed to the LLM agent as a "user message".

### Setup

1. Build the iPad app:
   ```bash
   cd ipad-listen
   swift build -c release
   ```

2. Install on the iPad (one-time, requires Xcode device pairing).

3. Configure the WebSocket URL in the iPad app's settings panel:
   `ws://<mac-ip>:8765/voice`

4. Tap "Start Listening" once. The app keeps listening until you tap "Stop".

### Push-to-talk mode

For privacy moments where you don't want always-listening:

- Long-press volume up: enters push-to-talk mode.
- Hold to record, release to send.
- iPad shows a red dot while recording.

## Output (agent → HomePod)

The HomePod is the voice output. The macOS bridge (`agent/voice/main.py`) handles
streaming TTS audio over AirPlay 2.

### How it works

1. Agent generates text response.
2. Bridge picks TTS engine based on length:
   - Short (< 200 chars): local Piper TTS
   - Long: hosted ElevenLabs / OpenAI TTS
3. Audio encoded as AAC-LC, wrapped in RTP, encrypted with HomePod's RSA key.
4. Streamed via RAOP to the HomePod.

### HomePod discovery

The bridge discovers HomePods via mDNS (Bonjour):

```
_airplay._tcp.local
_raop._tcp.local
```

The bridge picks the HomePod based on a setting (`HOME_POD_ROOM=bedroom`) or the
first one found.

### Setup

The bridge auto-discovers HomePods. No manual configuration needed if your HomePod
is on the same LAN as the Mac.

To set a specific HomePod:

```bash
export HOMEPOD_ROOM="Bedroom"
```

Or pass to `make run` directly.

## Latency budget

End-to-end voice → response latency target: < 2 seconds.

| Step | Latency |
|---|---|
| iPad mic capture | ~50ms |
| Opus encode | ~10ms |
| WebSocket transit | ~20ms |
| Whisper transcription | ~500ms |
| LLM inference (local) | ~500ms |
| TTS synthesis | ~300ms |
| RAOP stream start | ~200ms |
| AirPlay buffer fill | ~200ms |
| **Total** | **~1.8s** |

## Privacy considerations

- **Always-listening mode**: iPad microphone is always on. Anyone in the room
  can be heard by the agent. Use push-to-talk mode for privacy.
- **Audio retention**: raw audio is discarded after Whisper transcription. Only
  the text transcript is retained in agent memory.
- **Local-only by default**: TTS uses local Piper. Hosted TTS (ElevenLabs) is
  opt-in via config.
- **LLM hosting**: routine queries use local Ollama. Complex queries may go
  to Anthropic — only text is sent, not audio.

## Hardware notes

### iPad requirements

- iPad with iOS 17+ (microphone + WebSocket)
- Always-on requires power adapter
- Wi-Fi connection to same LAN as Mac

### HomePod requirements

- HomePod, HomePod mini, or HomePod 2nd gen
- Must be on same LAN
- "Allow Speakers and TV" enabled in Home settings (for AirPlay)

### Mac requirements

- Apple Silicon (M1+) for local Whisper + Ollama
- 16GB RAM minimum
- AirPlay-capable network interface (Wi-Fi or wired)