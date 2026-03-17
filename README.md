# Remote GUI Framework (Prototype)

A lightweight prototype for rendering an application UI on a desktop while the application logic runs on an IoT or edge device (example: Raspberry Pi). Instead of forwarding a full desktop (X11/VNC), the device streams a small JSON UI protocol over WebSockets.

## What It Does

- The device (Pi) owns the app state and decides what UI should exist.
- The device sends UI commands to the desktop: create, update, destroy.
- The desktop renders widgets locally (Tkinter) and sends user input back as events.

This is intentionally minimal and is meant as a starting point for a real protocol/layout system.

## Repo Layout

```
pi/
  server.py            # WebSocket server + Remote* widgets (Pi side)
desktop/
  client_tk.py         # Tkinter renderer (desktop side)
shared/
  protocol.py          # Shared protocol constants/helpers
docs/
  prototype_notes.txt  # Background notes
README.md
ReadThis.txt
```

## Quick Start

### 1) Start the Pi server

On the Pi (or any machine acting as the device):

```bash
python pi/server.py
```

It listens on `ws://0.0.0.0:8765` by default.

### 2) Point the desktop client at the Pi

On the desktop, edit `desktop/client_tk.py` and set:

- `PI_WS = "ws://<PI_IP>:8765"`

Then run:

```bash
python desktop/client_tk.py
```

A demo UI should appear on the desktop. Interactions get printed on the Pi/server console.

## Protocol Summary

All messages are JSON objects.

### Device -> Desktop

- `{"action":"create","widget":"label|button|entry|slider|checkbox","id":"<id>","props":{...}}`
- `{"action":"update","id":"<id>","props":{...}}`
- `{"action":"destroy","id":"<id>"}`

### Desktop -> Device

- `{"action":"event","id":"<id>","event":{...}}`

Event examples:

- button click: `{"type":"click"}`
- entry submit: `{"type":"enter","value":"..."}`
- slider change: `{"type":"slide","value":42.0}`
- checkbox toggle: `{"type":"check","checked":true}`

### Keepalive (optional)

- desktop sends: `{"action":"heartbeat"}`
- device replies: `{"action":"heartbeat_ack"}`

## Dependencies

- Python 3
- `websockets` (Python package)
- Tkinter (usually bundled with Python on Windows/macOS; may need separate install on some Linux distros)

## Troubleshooting

- If the desktop UI is blank: confirm the Pi server is running and reachable from the desktop (firewall, subnet, correct `PI_WS`).
- If you reconnect and want the UI to rebuild: the server replays the current widget registry on `hello`.
- If Tkinter is missing: install a Python distribution that includes Tkinter, or install the OS package providing it.

## Next Steps

If you want to evolve this into a real framework, the natural upgrades are:
- Add layout primitives (rows/columns/stack, sizing) instead of raw `x/y` placement.
- Add a stronger schema/versioning story and validation.
- Add reconnect semantics, acks, and batching/diffing for large UIs.

