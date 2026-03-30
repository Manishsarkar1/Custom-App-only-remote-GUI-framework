# Remote GUI Framework (Prototype)

A lightweight prototype for rendering an application UI on a desktop while the application logic runs on an IoT or edge device (example: Raspberry Pi). Instead of forwarding a full desktop (X11/VNC), the device streams a small JSON UI protocol over WebSockets.

## What It Does

- The device (Pi) owns the app state and decides what UI should exist.
- The device sends UI commands to the desktop: create, update, destroy.
- The desktop renders widgets locally (Tkinter) and sends user input back as events.
- The desktop now auto-reconnects and shows connection state in the window.

This is intentionally minimal and is meant as a starting point for a real protocol/layout system.

## Repo Layout

```
pi/
  server.py            # WebSocket server + Remote* widgets (Pi side)
desktop/
  client_tk.py         # Tkinter renderer (desktop side)
shared/
  config.py            # Shared environment-based config
  protocol.py          # Shared protocol constants/helpers/validation
tests/
  test_protocol.py     # Basic protocol validation coverage
docs/
  prototype_notes.txt  # Background notes
README.md
ReadThis.txt
```

## Quick Start

### 1) Configure the connection

Use environment variables instead of editing source files directly.

Windows PowerShell example:

```powershell
$env:REMOTE_GUI_HOST = "0.0.0.0"
$env:REMOTE_GUI_PORT = "8765"
$env:REMOTE_GUI_PI_WS = "ws://192.168.137.5:8765"
# Optional:
# $env:REMOTE_GUI_AUTH_TOKEN = "secret-token"
# $env:REMOTE_GUI_HEARTBEAT_MS = "5000"
# $env:REMOTE_GUI_RECONNECT_MS = "2000"
```

### 2) Start the Pi server

On the Pi (or any machine acting as the device):

```bash
python pi/server.py
```

### 3) Start the desktop client

On the desktop:

```bash
python desktop/client_tk.py
```

A demo UI should appear on the desktop. If the connection drops, the desktop app will retry automatically.

## Protocol Summary

All messages are JSON objects.

### Device -> Desktop

- `{"action":"create","widget":"label|button|entry|slider|checkbox","id":"<id>","props":{...}}`
- `{"action":"update","id":"<id>","props":{...}}`
- `{"action":"destroy","id":"<id>"}`

### Desktop -> Device

- `{"action":"event","id":"<id>","event":{...}}`

### Handshake And Keepalive

- desktop sends: `{"action":"hello","protocol":1}`
- device replies: `{"action":"hello_ack","protocol":1}`
- desktop sends: `{"action":"heartbeat"}`
- device replies: `{"action":"heartbeat_ack"}`

Invalid messages are now rejected with an error payload.

## Dependencies

- Python 3
- `websockets` (Python package)
- Tkinter (usually bundled with Python on Windows/macOS; may need separate install on some Linux distros)

## Tests

```bash
python -m unittest discover -s tests
```

## Next Steps

Natural follow-ups from here:
- Add layout primitives (rows/columns/stack, sizing) instead of raw `x/y` placement.
- Add more widgets and styling/state props.
- Add batching/diffing for larger UIs.
- Add stronger auth/TLS options for non-local setups.
