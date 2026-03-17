import asyncio
import json
import uuid
from typing import Callable, Dict, Any, Optional

import websockets

import os
import sys

# Allow running this script from its folder or repo root.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from shared.protocol import (
    ACTION_CREATE,
    ACTION_DESTROY,
    ACTION_ERROR,
    ACTION_EVENT,
    ACTION_HEARTBEAT,
    ACTION_HEARTBEAT_ACK,
    ACTION_HELLO,
    ACTION_HELLO_ACK,
    ACTION_UPDATE,
    PROTOCOL_VERSION,
    dumps,
)

HOST = "0.0.0.0"
PORT = 8765
AUTH_TOKEN = None  # optional auth token (set to None to disable)

_clients = set()
_widget_registry: Dict[str, Dict[str, Any]] = {}


def _mkid() -> str:
    return uuid.uuid4().hex[:8]


async def _broadcast(obj: Dict[str, Any]):
    if not _clients:
        return

    msg = dumps(obj)
    clients = list(_clients)
    results = await asyncio.gather(*(ws.send(msg) for ws in clients), return_exceptions=True)

    # Drop clients that errored (usually disconnected).
    for ws, res in zip(clients, results):
        if isinstance(res, Exception):
            _clients.discard(ws)


def _safe_cb(ev: Dict[str, Any], cb: Callable[[Dict[str, Any]], None]):
    try:
        cb(ev)
    except Exception as e:
        print("Callback error:", e)


async def _handle_incoming(ws, data: Dict[str, Any]):
    act = data.get("action")

    if act == ACTION_HELLO:
        if AUTH_TOKEN and data.get("token") != AUTH_TOKEN:
            await ws.send(dumps({"action": ACTION_ERROR, "reason": "auth_failed"}))
            await ws.close(code=4401, reason="Auth Failed")
            return

        await ws.send(dumps({"action": ACTION_HELLO_ACK, "protocol": PROTOCOL_VERSION}))

        # Replay current UI state so the client can rebuild if reconnected.
        for wid, meta in _widget_registry.items():
            await ws.send(
                dumps(
                    {
                        "action": ACTION_CREATE,
                        "widget": meta["type"],
                        "id": wid,
                        "props": meta["props"],
                    }
                )
            )

    elif act == ACTION_EVENT:
        wid = data.get("id")
        ev = data.get("event")
        info = _widget_registry.get(wid)
        cb = info.get("callback") if info else None
        if cb and isinstance(ev, dict):
            # Callbacks are kept synchronous for simplicity.
            _safe_cb(ev, cb)

    elif act == ACTION_HEARTBEAT:
        await ws.send(dumps({"action": ACTION_HEARTBEAT_ACK}))

    else:
        print("Unhandled from client:", data)


async def handler(ws, *_):
    print("Desktop connected")
    _clients.add(ws)
    try:
        async for msg in ws:
            try:
                data = json.loads(msg)
            except Exception:
                continue
            if isinstance(data, dict):
                await _handle_incoming(ws, data)
    except websockets.ConnectionClosed:
        pass
    finally:
        _clients.discard(ws)
        print("Desktop disconnected")


async def start_server():
    print(f"Starting Pi server on ws://{HOST}:{PORT}")
    async with websockets.serve(handler, HOST, PORT):
        await asyncio.Future()  # run forever


class RemoteWidget:
    def __init__(
        self,
        widget_type: str,
        props: Optional[Dict[str, Any]] = None,
        callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self.id = _mkid()
        self.type = widget_type
        self.props = props or {}

        _widget_registry[self.id] = {"type": widget_type, "props": self.props, "callback": callback}

        loop = asyncio.get_running_loop()
        loop.create_task(
            _broadcast({"action": ACTION_CREATE, "widget": self.type, "id": self.id, "props": self.props})
        )

    def update(self, props: Dict[str, Any]):
        self.props.update(props)
        _widget_registry[self.id]["props"] = self.props

        loop = asyncio.get_running_loop()
        loop.create_task(_broadcast({"action": ACTION_UPDATE, "id": self.id, "props": props}))

    def destroy(self):
        _widget_registry.pop(self.id, None)

        loop = asyncio.get_running_loop()
        loop.create_task(_broadcast({"action": ACTION_DESTROY, "id": self.id}))


class RemoteLabel(RemoteWidget):
    def __init__(self, text: str, x=10, y=10):
        super().__init__("label", {"text": text, "x": x, "y": y})


class RemoteButton(RemoteWidget):
    def __init__(self, text: str, x=10, y=10, callback=None):
        super().__init__("button", {"text": text, "x": x, "y": y}, callback=callback)


class RemoteEntry(RemoteWidget):
    def __init__(self, text: str = "", x=10, y=10, callback=None):
        super().__init__("entry", {"text": text, "x": x, "y": y}, callback=callback)


class RemoteCheckbox(RemoteWidget):
    def __init__(self, label: str, checked=False, x=10, y=10, callback=None):
        super().__init__(
            "checkbox",
            {"label": label, "checked": checked, "x": x, "y": y},
            callback=callback,
        )


class RemoteSlider(RemoteWidget):
    def __init__(self, min_value=0, max_value=100, value=50, x=10, y=10, callback=None):
        super().__init__(
            "slider",
            {"min": min_value, "max": max_value, "value": value, "x": x, "y": y},
            callback=callback,
        )


async def _demo():
    await asyncio.sleep(0.5)

    def on_click(ev):
        print("Pi: Button clicked event:", ev)
        label.update({"text": "Clicked!"})

    def on_checkbox(ev):
        print("Pi: CheckBox event:", ev)

    def on_slider(ev):
        print("Pi: Slider event:", ev)

    def on_entry(ev):
        print("Pi: Entry event:", ev)

    label = RemoteLabel("Hello from Pi", x=20, y=20)
    RemoteButton("Press me", x=10, y=60, callback=on_click)
    RemoteCheckbox("Enable Feature", x=10, y=100, callback=on_checkbox)
    RemoteSlider(0, 100, 30, x=10, y=140, callback=on_slider)
    RemoteEntry("Type and press Enter", x=10, y=180, callback=on_entry)

    await asyncio.sleep(3)
    label.update({"text": "Updated from Pi"})


if __name__ == "__main__":
    import json

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    loop.create_task(start_server())
    loop.create_task(_demo())  # remove this when using your own app logic

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass

