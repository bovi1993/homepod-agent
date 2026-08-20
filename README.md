# homepod-agent

A local-first home automation system that turns your HomeKit network, HomePod speaker,
and always-on iPad into a single conversational interface controlled by a small LLM
agent that lives on your Mac.

## What it does

- **Reads HomeKit state** — every accessory in your home (lights, locks, thermostats, sensors, HomePods, cameras)
- **Writes HomeKit commands** — turn on the kitchen lights, lock the front door, set the bedroom thermostat
- **Speaks through HomePod** — AirPlay 2 streams TTS responses to a HomePod in your chosen room
- **Listens through an iPad** — always-on iPad captures speech, runs ASR, sends transcripts to the agent
- **Routes between local and hosted LLMs** — small local model for routine; Claude or GPT for complex reasoning
- **Controls Xiaomi air purifiers + Dreame vacuums** — local miio via tokens from Xiaomi/Dreamehome cloud (`docs/devices.md`)
- **Shows everything on a dashboard** — Next.js UI with device grid, camera feeds, chat panel, automation editor

## Architecture

```
┌────────────────────────────────────────────────────────┐
│  iPad (always-on) ─── audio ──┐                       │
│                               │                       │
│  Dashboard (Next.js) ───┐    │                       │
│                          ▼    ▼                       │
│  ┌───────────────────────────────────────────┐         │
│  │   Agent service (FastAPI + LLM router)    │         │
│  │   - Ollama (Qwen 2.5 7B) for routine      │         │
│  │   - Anthropic / OpenAI for complex        │         │
│  └──────────────┬────────────────────────────┘         │
│                 │                                       │
│       ┌─────────┼─────────┐                             │
│       │         │         │                             │
│  ┌────▼────┐ ┌──▼────┐ ┌──▼────────┐                    │
│  │ HomeKit │ │ Voice │ │  Cameras  │                    │
│  │  (pyhap)│ │bridge │ │ (ONVIF +  │                    │
│  │  HAP    │ │(macOS)│ │ RTSP→HLS) │                    │
│  └────┬────┘ └──┬────┘ └───────────┘                    │
│       │        │                                         │
│       ▼        ▼                                         │
│  HAP socket  AirPlay 2                                   │
│       │        │                                         │
│  ┌────▼────────▼────┐                                    │
│  │  Ziggo LAN 192.168.178.0/24                          │
│  │  HomePod 192.168.178.63 (Bedroom)                    │
│  │  Cameras ...                                          │
│  └──────────────────┘                                   │
└────────────────────────────────────────────────────────┘
```

See [`docs/architecture.md`](docs/architecture.md) for the full breakdown.

## Quick start

> **Status:** v0.1 scaffold — functional but rough. Each subsystem is real code you can run, not a mockup.

### Requirements

- macOS 14+ on the Mac that runs the agent
- Python 3.11+ (use `uv` to manage)
- Node 20+ (for the dashboard)
- A HomeKit home with at least one accessory (we tested with a HomePod)
- An iPad on the same network (for voice input — Phase 2)
- [Ollama](https://ollama.com/) installed locally for the small model
- Optional: Anthropic or OpenAI API key for the hosted fallback

### Install

```bash
git clone https://github.com/bovi1993/homepod-agent
cd homepod-agent
make install          # installs all components
make pair             # generates HomeKit setup code; scan with iPhone Home app
make run              # boots all services
```

Then open:
- Dashboard: http://localhost:3000
- Agent API: http://localhost:8000/docs
- Voice bridge: starts on the HomePod you selected

### Repo layout

```
agent/                 Python agent + HomeKit + cameras + voice bridge
  homekit/             pyhap-based HAP controller
  llm/                 FastAPI service with LLM router
  cameras/             ONVIF discovery + RTSP proxy
  voice/               macOS HomePod AirPlay bridge
ipad-listen/           Swift app for always-on iPad mic client
dashboard/             Next.js 15 dashboard
docs/                  Architecture, pairing, voice docs
```

## What's where in this scaffold

| Layer | Folder | Status |
|---|---|---|
| HomeKit control | `agent/homekit/` | Working — REST + WebSocket API over pyhap |
| LLM agent | `agent/llm/` | Working — Ollama + Anthropic routing |
| Voice output (HomePod) | `agent/voice/` | Working — mDNS discovery + AirPlay 2 stream |
| Voice input (iPad) | `ipad-listen/` | Skeleton — basic Swift client, WebSocket audio |
| Dashboard | `dashboard/` | Working — room-first dark UI, scenes, device tiles, chat/cameras |
| Cameras | `agent/cameras/` | Skeleton — ONVIF discovery, RTSP→HLS placeholder |

## License

MIT (TBD — confirm with owner).

## Related

- [home-assistant/core](https://github.com/home-assistant/core) — alternative open-source platform with HomeKit integration via [`homekit_controller`](https://www.home-assistant.io/integrations/homekit/)
- [apple/homekit-adk](https://github.com/apple/homekit-adk) — Apple's official HomeKit ADK for embedded accessory development
- [maximkulkin/iphone](https://github.com/maximkulkin/iphone) — HAP-NodeJS reference implementation
- [b0mbayslag/homepod-agent](https://github.com/) — this repo