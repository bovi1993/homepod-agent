# Home app UX — research, principles, automation

> Surface: **Operate + Monitor** (not marketing).  
> Goal: glance + act in under 2 taps; agent/chat for the long tail.

## Research synthesis (2025–2026 smart-home UI)

Sources of practice (not cloning brands):

| Pattern | Who does it well | What we take |
|---------|------------------|--------------|
| Room-first hierarchy | Apple Home | Group by room; favorites above the fold |
| Status at a glance | Apple Home, HA sections | Security / climate / air strip before device grid |
| Big tappable tiles | iOS Control Center, HA button-card | Tile **is** the control (tap = toggle), not a read-only card |
| Scenes > individual devices | Apple Home, HA scenes | “Good night”, “Away”, “Clean” as first-class chips |
| Density without clutter | Linear (product UI density) | Dark canvas, luminance elevation, one accent |
| Suggested automations | HA prototype / community | Surface *why* automation, not only device lists |
| Voice + typed chat as long tail | Siri / agent chat | Chat is secondary; home is primary |
| Cameras as exception | Ring / Nest | Motion badge + large preview; don’t bury in Settings |

**Anti-patterns we avoid**

- Centered hero + three feature cards (marketing layout on a control surface)
- Duplicate lists (all devices AND by-room with same tiles twice)
- Read-only status cards with no action
- Generic indigo SaaS chrome with fake metrics
- Showing RTSP URLs as primary camera labels

## Design system (homepod-agent dashboard)

- **Mode:** dark-first (`#08090a` canvas) — wall tablets + evening use
- **Accent:** cool violet for interactive chrome only (`#7170ff`)
- **State colors:** green = on/secure, amber = attention, red = alarm/offline, blue = active job (cleaning)
- **Type:** system SF / Inter stack; labels 12–13px medium; names 15px
- **Tiles:** 1:1-ish min height, 14–16px radius, border `white/8%`, active glow when on
- **Nav:** bottom bar on mobile, top compact on desktop — Home · Chat · Cameras · Settings
- **Command:** persistent “Ask home…” jump to chat with suggested prompts

## Information architecture

```
Home
  ├─ Greeting + connection pills (agent / HK / devices / live)
  ├─ Status strip (doors, climate, air, vacuum)
  ├─ Scenes (Away, Home, Clean, Night) — cloud/local when wired
  ├─ Favorites (user-pinned + high-signal devices)
  └─ Rooms → actionable tiles

Chat          long-tail natural language + tool traces
Cameras       grid, motion first
Settings      health, pods, paths, cloud-sync hints
```

## Automation roadmap (local-first)

Priority automations once tokens/devices are live:

1. **Away** — when last phone leaves LAN (or explicit scene): vacuum start, lights off, lock check via agent
2. **Air quality** — purifier auto on when AQI > threshold; off when clean + empty home optional
3. **Night** — dim/off non-essentials; vacuum docked; cameras motion-priority notifications
4. **Filter / bin** — agent memory fact + dashboard badge when filter_life low or vacuum error
5. **HomeKit mirror** — same scenes exposed as HAP switches so Siri / Home.app stay source of truth for family

Rules:

- Prefer **local miio** triggers; cloud only for token refresh
- Every automation must be **visible** (badge or log line) and **overridable** in UI
- Never hide destructive actions (factory reset, unpair) in one-tap tiles

## Success metrics

- Time to toggle vacuum/purifier from open app: **≤ 2 taps**
- Empty state explains next action (cloud-sync / power on device)
- Works offline for already-tokened local devices
- Readable on iPad landscape and phone portrait
