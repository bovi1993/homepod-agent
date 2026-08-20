# CONTRIBUTING

## For humans

Open a PR. Run `make lint` and `make test` first.

## For AI coding agents

Read `README.md` first. The architecture is six services:

1. `agent/homekit/` — pyhap HAP controller
2. `agent/llm/` — FastAPI agent with local/hosted LLM routing
3. `agent/voice/` — macOS HomePod AirPlay bridge
4. `ipad-listen/` — Swift iPad mic client
5. `dashboard/` — Next.js UI
6. `agent/cameras/` — ONVIF + RTSP

### Hard constraints

- **Apple removed programmatic HomeKit on macOS 26.** Use `pyhap`, not the
  `HomeKit.framework` Swift API.
- **HomePod's microphone is locked to Siri.** iPad handles mic input; HomePod
  is speaker only.
- **Agent runs on the same LAN as the HomeKit accessories.** No remote pairing.

### Conventions

- Python 3.11+, `uv` for deps.
- TypeScript + Next.js 15 App Router + Tailwind for dashboard.
- Swift 5.10+, SwiftPM for iPad app.
- HTTP: `{"ok": bool, "data"?: ..., "error"?: ...}`.
- WebSocket: JSON-line framed.
- HomeKit pairing code: XXX-XX-XXX.

### Common pitfalls

- Pairing needs iPhone scan within 60s.
- RTSP/ONVIF devices need auth credentials.
- Local Ollama must be running for local LLM.

See `docs/architecture.md` for the full architecture.