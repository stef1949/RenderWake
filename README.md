
<h1 align="center">
RenderWake

</h1>

RenderWake keeps your computer awake **only while Blender is rendering**, and releases the wake lock when rendering ends—so normal sleep/idle behaviour returns when you’re not rendering.

## Features

- Prevents system sleep during:
  - Still renders (F12)
  - Animation renders
  - Render cancellations (releases cleanly)
- Optional status bar indicator: `Awake: ON/OFF`
- Cross-platform:
  - **Windows**: uses `SetThreadExecutionState`
  - **macOS**: uses `caffeinate`
  - **Linux**: uses `systemd-inhibit` when available

## Install

### Via Extensions (recommended)
1. Drag the Zip onto blender.
2. In Blender: **Preferences → Extensions → Install from Disk…**
3. Enable **RenderWake** in the add-ons list.

### Via legacy add-ons
1. Install `addon/renderwake.py` via **Preferences → Add-ons → Install…**
2. Enable **RenderWake**

## Usage

Just render as normal. RenderWake:
- acquires the wake lock on render start
- releases it on render end or cancel

Explainable status indicator (optional) is shown in Blender’s status bar.

## Preferences

- **Enable**: master toggle
- **Show status indicator**: shows `Awake: ON/OFF` in the status bar
- **Verbose logging**: prints state changes to the console

## macOS note

By default, RenderWake uses:

- `caffeinate -d` (prevents display sleep too)

If you prefer allowing the display to sleep while still preventing system idle sleep, change it to:

- `caffeinate -i`

## Linux note

RenderWake uses `systemd-inhibit` if it’s available. If your system doesn’t have it (non-systemd distros), RenderWake won’t inhibit sleep (safe no-op). Contributions welcome for additional inhibit backends.

## License

MIT License
