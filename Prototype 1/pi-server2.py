# pi_server.py
# Raspberry Pi: runs the backend + pushes UI commands to the laptop
# Works with websockets v10–v13 (handler accepts optional path)

import asyncio
import json
import uuid
from typing import Callable, Dict, Any, Optional
import websockets

HOST = "0.0.0.0"
PORT = 8765

# Optional auth (set to None to disable)
AUTH_TOKEN = None

# Connected clients
_clients = set()

# Widget registry: wid -> {"type": str, "props": dict, "callback": callable|None}
_widget_registry: Dict[str, Dict[str, Any]] = {}

# ===== Utilities =====
def _msg(obj: Dict[str, Any]) -> str:
    return json.dumps(obj, separators=(",", ":"))

async def _broadcast(obj: Dict[str, Any]):
    if not _clients:
        return
    msg = _msg(obj)
    await asyncio.wait([ws.send(msg) for ws in list(_clients)])

def _mkid() -> str:
    return uuid.uuid4().hex[:8]

# ===== Incoming message handler =====
async def _handle_incoming(ws, data: Dict[str, Any]):
    act = data.get("action")
    if act == "hello":
        if AUTH_TOKEN and data.get("token") != AUTH_TOKEN:
            await ws.send(_msg({"action": "error", "reason": "auth_failed"}))
            await ws.close(code=4401, reason="auth failed")
            return
        await ws.send(_msg({"action": "hello_ack", "protocol": 1}))
        # Replay current UI state
        for wid, meta in _widget_registry.items():
            await ws.send(_msg({
                "action": "create",
                "widget": meta["type"],
                "id": wid,
                "props": meta["props"]
            }))

    elif act == "event":
        wid = data.get("id")
        ev = data.get("event")
        info = _widget_registry.get(wid)
        cb = info.get("callback") if info else None
        if cb:
            loop = asyncio.get_running_loop()
            def run_cb():
                try:
                    cb(ev)
                except Exception as e:
                    print("Callback error:", e)
            loop.run_in_executor(None, run_cb)

    elif act == "heartbeat":
        await ws.send(_msg({"action": "heartbeat_ack"}))

    else:
        print("Unhandled from client:", data)

# ===== Websocket server =====
async def handler(ws, *_) -> None:
    print("Laptop Connected!")
    _clients.add(ws)
    try:
        async for msg in ws:
            try:
                data = json.loads(msg)
            except json.JSONDecodeError:
                continue
            await _handle_incoming(ws, data)
    except websockets.ConnectionClosed:
        pass
    finally:
        _clients.discard(ws)
        print("Laptop disconnected!")

async def start_server():
    print(f"Starting Pi server on ws://{HOST}:{PORT}")
    async with websockets.serve(handler, HOST, PORT):
        await asyncio.Future()

# ===== Remote Widgets =====
class RemoteWidget:
    def __init__(self, widget_type: str, props: Optional[Dict[str, Any]]=None,
                 callback: Optional[Callable[[Dict[str, Any]], None]]=None):
        self.id = _mkid()
        self.type = widget_type
        self.props = props or {}
        _widget_registry[self.id] = {"type": widget_type, "props": self.props, "callback": callback}
        asyncio.get_event_loop().create_task(_broadcast({
            "action": "create", "widget": self.type, "id": self.id, "props": self.props
        }))

    def update(self, props: Dict[str, Any]):
        self.props.update(props)
        _widget_registry[self.id]["props"] = self.props
        asyncio.get_event_loop().create_task(_broadcast({
            "action": "update", "id": self.id, "props": props
        }))

    def destroy(self):
        _widget_registry.pop(self.id, None)
        asyncio.get_event_loop().create_task(_broadcast({
            "action": "destroy", "id": self.id
        }))

class RemoteLabel(RemoteWidget):
    def __init__(self, text: str, x=10, y=10):
        super().__init__("label", {"text": text, "x": x, "y": y})

class RemoteButton(RemoteWidget):
    def __init__(self, text: str, x=10, y=10, callback=None):
        super().__init__("button", {"text": text, "x": x, "y": y}, callback=callback)

# ===== Small Demo =====
async def _demo():
    await asyncio.sleep(0.5)

    def on_click(ev):
        print("Pi: Button clicked event:", ev)
        label.update({"text": "Clicked!"})

    label = RemoteLabel("Hello from Pi", x=20, y=20)
    btn = RemoteButton("Press me", x=10, y=60, callback=on_click)

    await asyncio.sleep(3)
    label.update({"text": "Updated from Pi"})

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(start_server())
    loop.create_task(_demo())  # Remove if using own app
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
