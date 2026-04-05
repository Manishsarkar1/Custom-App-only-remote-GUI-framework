# Remote GUI Framework (Prototype)

A lightweight prototype for rendering an application UI on a desktop while the application logic runs on an IoT or edge device. Instead of forwarding a full desktop, the device streams a compact JSON UI protocol over WebSockets.

## What Changed

- The desktop client now has light/dark theme support.
- The UI can render richer layouts with cards and scrollable columns.
- The demo now looks more like a dashboard instead of a raw widget test.
- Tooltips, stronger typography, better button variants, and more widget types are supported.

## Repo Layout

```
pi/
  server.py            # WebSocket server + remote widget helpers + demo UI
desktop/
  client_tk.py         # Tkinter renderer, theming, reconnect logic
shared/
  config.py            # Environment-based config
  protocol.py          # Protocol constants + validation
tests/
  test_protocol.py     # Basic protocol validation coverage
```

## Quick Start

### 1) Configure the connection

PowerShell example:

```powershell
$env:REMOTE_GUI_HOST = "0.0.0.0"
$env:REMOTE_GUI_PORT = "8765"
$env:REMOTE_GUI_PI_WS = "ws://192.168.137.5:8765"
$env:REMOTE_GUI_THEME = "dark"
# Optional:
# $env:REMOTE_GUI_AUTH_TOKEN = "secret-token"
# $env:REMOTE_GUI_HEARTBEAT_MS = "5000"
# $env:REMOTE_GUI_RECONNECT_MS = "2000"
```

### 2) Start the Pi server

```bash
python pi/server.py
```

### 3) Start the desktop client

```bash
python desktop/client_tk.py
```

## Supported Widgets

- `label`
- `button`
- `entry`
- `slider`
- `checkbox`
- `dropdown`
- `progress`
- `textarea`
- `row`
- `column`
- `card`
- `scroll_column`
- `separator`
- `spinner`
- `radio_group`

## Useful Props

- `x`, `y` for absolute placement
- `parent` for nested layouts
- `layout` for `padx`, `pady`, `fill`, `expand`, `side`, `anchor`
- `width`, `height`
- `visible`, `disabled`
- `variant` for button/progress styling
- `font_role` like `hero`, `title`, `section`, `subtitle`, `metric`, `caption`
- `tooltip`
- `wrap` for labels

## UX Improvements

- Auto reconnect with visible connection state
- Throttled slider events
- Scrollable content regions
- Card-style dashboard sections
- Radio groups and indeterminate spinner support
- Text areas with `Ctrl+Enter` submit

## Tests

```bash
python -m unittest discover -s tests
```

## Current Limits

- Layout is still a simple pack/place hybrid, not a full flexbox/grid engine.
- Styling is desktop-side only; the protocol sends style hints rather than a full design system schema.
- Advanced features from the larger wishlist like charts, tabs, modals, drag-and-drop, TLS, and plugin architecture are still not implemented.
