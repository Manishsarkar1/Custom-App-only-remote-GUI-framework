# Custom App only Remote GUI framework (prototype)

This repo is a small prototype to avoid full X11-style desktop forwarding.

The idea:
- The app runs on an IoT / edge device (example: Raspberry Pi).
- The device sends JSON "UI commands" over WebSockets (`create`/`update`/`destroy`).
- A desktop client receives those commands and renders the UI locally.
- User interactions (clicks, entry submit, slider moves, checkbox toggles) are sent back as `event` messages.

## Folder layout
- `pi/` : websocket server + remote widget helpers
- `desktop/` : desktop renderer (Tkinter)
- `shared/` : tiny shared protocol constants
- `docs/` : notes

## Run

1) On the Pi (or edge device), start the server:

`python pi/server.py`

2) On the desktop, edit the Pi IP in `desktop/client_tk.py` (`PI_WS = "ws://...:8765"`) and run:

`python desktop/client_tk.py`

## Protocol (high level)
- Pi -> Desktop: `create`, `update`, `destroy`
- Desktop -> Pi: `event`
- Optional keepalive: `heartbeat` / `heartbeat_ack`

## Dependencies
- Python 3
- `websockets` python package
