# Xiaomi air purifier + Dreame (Dreamehome) vacuum

Local control via [python-miio](https://github.com/rytilahti/python-miio) (MIoT).
Tokens come from Xiaomi cloud (same account as the **Mi Home** / **Xiaomi Home** /
**Dreamehome** app for most EU Dreame robots).

## Quick start

```bash
# 1. Pull IP + token from your Xiaomi/Dreamehome account (EU server = de)
cd agent
PYTHONPATH=. .venv/bin/python -m devices cloud-sync \
  --username 'you@example.com' \
  --password '…' \
  --country de

# 2. Check live status over LAN
PYTHONPATH=. .venv/bin/python -m devices status

# 3. Control
PYTHONPATH=. .venv/bin/python -m devices cmd ap-XXXX on
PYTHONPATH=. .venv/bin/python -m devices cmd vac-XXXX start
PYTHONPATH=. .venv/bin/python -m devices cmd vac-XXXX home

# 4. HTTP API (also started by `homepod-agent serve`)
PYTHONPATH=. .venv/bin/python -m devices serve --port 8002
```

Or via the top-level CLI:

```bash
homepod-agent devices cloud-sync --username … --password … --country de
homepod-agent devices status
homepod-agent devices discover
```

Config is stored at **`~/.homepod-agent/devices.yaml`** (mode `0600`).  
Passwords are **never** written to disk — only username, country, and last sync time.

## Manual config

If cloud-sync is unavailable, paste IP + 32-char hex token yourself:

```yaml
devices:
  - id: ap-living
    name: Living Room Purifier
    kind: air_purifier
    model: zhimi.airpurifier.mb4
    ip: 192.168.178.40
    token: "0123456789abcdef0123456789abcdef"
    room: Living Room
  - id: vac-main
    name: Dreame
    kind: vacuum
    model: dreame.vacuum.p2028
    ip: 192.168.178.41
    token: "0123456789abcdef0123456789abcdef"
    room: Hallway
```

## LAN discovery

```bash
homepod-agent devices discover
```

Modern firmware often **does not** answer miio UDP hello until you already have
the token. Cloud-sync is the reliable path.

## HomeKit

When the HAP bridge starts, every `air_purifier` / `vacuum` entry in
`devices.yaml` is added as a child accessory:

| Device        | HomeKit type                         | On / Off behaviour      |
|---------------|--------------------------------------|-------------------------|
| Air purifier  | AirPurifier + AirQuality + Filter    | power on/off            |
| Vacuum        | Fanv2 + Battery                      | start clean / return dock |

After adding devices, restart the bridge (or re-pair if Home.app cached an old
accessory list). New child AIDs may need a Home.app refresh.

## LLM tools

The agent gains:

- `list_devices` — AQI, power, battery, cleaning state  
- `set_air_purifier` — on/off, mode, fan level  
- `control_vacuum` — `start` | `stop` | `home` | `locate`

API base: `http://127.0.0.1:8002`

## Supported models (via python-miio)

**Air purifiers:** Zhimi MIoT models (`zhimi.airpurifier.*`, `zhimi.airp.*`) plus
classic `AirPurifier` fallback.

**Dreame vacuums:** `dreame.vacuum.mc1808` (1C), `p2008` (F9), `p2009` (D9),
`p2028` (Z10 Pro), `p2041o`, `p2150a`, `p2150o`, and other MIoT Dreame mappings
shipped in python-miio. Newer Dreamehome-only models may need a mapping update
— open an issue with the model string from cloud-sync.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `cloud login failed` | Correct password; try `--country cn` if the account is CN; disable 2FA app blocks or use the Xiaomi account that owns the devices |
| `missing ip/token` | Re-run cloud-sync while the phone is on the same Wi-Fi so cloud has `localip` |
| `status DOWN` / timeout | Device off, on guest Wi-Fi, or AP isolation on the Ziggo router — allow client-to-client |
| Home.app no purifier | Ensure bridge restarted after devices.yaml filled; force-quit Home.app |
| Vacuum unsupported model | Check `model:` from cloud-sync against python-miio `DreameVacuum` mappings |
