# HomePod Agent — Architecture

## Overview

A local-first home automation system. Components:

| Component | Language | Role |
|---|---|---|
| `agent/homekit/` | Python | HAP controller, joins HomeKit network, exposes state |
| `agent/llm/` | Python | FastAPI service with local/hosted LLM routing |
| `agent/voice/` | Python | macOS HomePod AirPlay bridge |
| `ipad-listen/` | Swift | iPad always-on mic client |
| `dashboard/` | TypeScript | Next.js 15 web dashboard |
| `agent/cameras/` | Python | ONVIF discovery + RTSP→HLS |

## Data flow

```
iPad mic (16kHz PCM)
   │ WebSocket (wss://)
   ▼
agent/llm/main.py
   │ - Whisper ASR → text
   │ - Classifier (local vs hosted)
   │ - LLM call with tool schema
   ▼
agent/homekit/state.py  (REST + WebSocket)
   │ pyhap HAP socket
   ▼
HomeKit accessories (LAN)
   │
   ▼ (state change → tts)
agent/voice/main.py
   │ mDNS discover HomePod
   │ AirPlay 2 stream
   ▼
HomePod (192.168.178.63)
```

## LLM routing

- **Routine queries** ("turn on the lights", "is the front door locked?")
  → Ollama (Qwen 2.5 7B) running locally on the Mac.
- **Complex reasoning** ("diagnose why the kitchen lights keep flickering",
  "set up an automation for when nobody's home")
  → Anthropic Claude Sonnet 4 / OpenAI GPT-4o via API.
- **Classifier**: small prompt-engineered function on Ollama; if confidence
  is low or query matches complex-pattern keywords, route to hosted.

## HomeKit pairing

1. `make pair` runs `agent/homekit/pair.py` which boots a temporary HAP
   accessory in "unpaired" mode.
2. Helper prints an `XXX-XX-XXX` setup code and a QR code (terminal ANSI).
3. User opens iPhone Home app → "+" → "Add Accessory" → scan QR / enter code.
4. iPhone pairs the bridge to the home.
5. Helper persists the pairing config to `~/.homepod-agent/pairing.json`.
6. Bridge is now a real accessory in the home; the agent can read/write all
   other accessories in that home through the bridge.

## Voice pipeline

### Input (iPad → agent)

- AVAudioEngine captures mic at 16kHz mono.
- Compressed with Opus to reduce bandwidth.
- Streamed over WebSocket to `agent/llm/voice_input.py`.
- Whisper small model on the Mac transcribes.
- Transcript fed to LLM agent.

### Output (agent → HomePod)

- Agent generates text response.
- If short (< 200 chars), use a local TTS (Piper or espeak).
- If longer, use Anthropic TTS or ElevenLabs.
- Audio encoded as AAC-LC, wrapped in RTP, sent over RAOP.
- Handled by `agent/voice/stream.py` using `pyatv` protocol.

## State persistence

- HomeKit pairing: `~/.homepod-agent/pairing.json` (encrypted at rest)
- LLM memory: `~/.homepod-agent/memory.db` (SQLite)
- Camera config: `~/.homepod-agent/cameras.yaml`
- Logs: `~/.homepod-agent/logs/*.log` (rotated)

## Failure modes

| Failure | Detection | Response |
|---|---|---|
| HomeKit bridge offline | HAP socket disconnect | Restart pyhap, re-pair if needed |
| Local LLM unavailable | Ollama HTTP 5xx | Fall back to hosted |
| Hosted LLM rate limit | HTTP 429 | Backoff + retry with local |
| HomePod unreachable | mDNS NXDOMAIN, no RAOP response | Skip TTS, surface in dashboard |
| iPad disconnected | WebSocket close | Agent enters text-only mode |
| Camera RTSP timeout | TCP timeout | Show "offline" in dashboard |

## Hardware requirements

- Mac with Apple Silicon (M1+) for local LLM inference
- 16GB RAM minimum (32GB recommended for 70B models)
- 50GB disk for model cache
- HomeKit-compatible accessories on the same LAN
- One HomePod (or HomePod mini) for voice output
- One iPad for voice input (always-on)