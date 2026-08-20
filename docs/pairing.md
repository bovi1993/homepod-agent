# HomeKit pairing

## Overview

The agent joins your HomeKit network as a **bridge accessory**. After pairing, the
agent can read and write every accessory in the home through the bridge.

## Pairing steps

1. **Make sure you're signed into the same Apple ID** on the Mac that runs the
   agent and the iPhone you'll pair with. The HomeKit pairing is per-iCloud-account.

2. **Start the pairing helper:**
   ```bash
   make pair
   ```
   This runs `agent/homekit/pair.py`. The helper boots a temporary HAP accessory
   in "unpaired" mode and prints a setup code.

3. **Note the setup code** (e.g., `528-23-142`). The helper also prints an ANSI
   QR code you can scan with the iPhone camera.

4. **On the iPhone**, open the **Home** app:
   - Tap "+" (top right)
   - Tap "Add Accessory"
   - Tap "More options..." if the bridge doesn't show up automatically
   - Scan the QR code OR tap "Enter code manually" and type the XXX-XX-XXX code

5. **Confirm the pairing** on the iPhone. You'll see a "Bridge Would Like to Be
   Added" prompt with a 6-digit code. Make sure it matches what the helper printed.

6. **Assign the bridge to a room** when prompted. The agent bridge will appear as
   "HomePod Agent" in your home.

7. **Wait for pairing to complete.** The helper will print "PAIRED" within 60
   seconds. If it times out, run `make pair` again.

8. **The pairing config is saved** to `~/.homepod-agent/pairing.json`. Future
   `make run` calls use this config.

## After pairing

- The agent can now read every accessory in your home.
- Run `make smoke` to verify the agent can list all accessories.
- The HomePod (and any other paired accessory) shows up in the dashboard.

## Unpairing

To remove the agent from your home:

```bash
make unpair
```

Or on the iPhone: Home app → tap the "HomePod Agent" bridge → "Remove from Home".

## Troubleshooting

### "Pairing timed out"

- The iPhone and Mac must be on the same network.
- The iPhone Home app must be signed in to the same iCloud account.
- mDNS must be allowed on your network (some routers block multicast by default).

### "Bridge already paired"

The agent thinks it's paired but the iPhone can't find it. Run `make unpair`
then `make pair` again.

### "Permission denied writing pairing.json"

The agent stores pairing config in `~/.homepod-agent/`. Make sure this directory
is writable by your user.

### Bridge paired but accessories don't show up

- The agent bridge is a HomeKit accessory; it can only access accessories in
  the same home.
- If you have multiple homes, the agent is paired to one home only. Use the
  Home app to move the bridge between homes if needed.