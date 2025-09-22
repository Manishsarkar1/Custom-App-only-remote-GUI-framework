#pi_server
#Raspberry pi runs the backend + pushes UI commands to the laptop
#works with websockets v10-13 (handler accepts optional path)

import asyncio
import json
import ssl
import uuid
from typing import Callable, Dict, Any, Optional
import websockets

Host = "0.0.0.0"
Port = 8765

#optional auth (set to none to disable)
Auth_token = None

#Connected clients
_clients = set()

#widget registry:wid -> {"type": str, "props": dict, "callback": callback|None}
_widget_registry: Dict[str, Dict[str, Any]] = {}

#Utilities
def _msg(obj : Dict[str, Any]) -> str:
    return json.dumps(obj, separators=(",",":"))

async def _broadcast(obj:Dict[str, Any]):
    if not _clients:
        return
    
    msg = _msg(obj)
    await asyncio.wait([ws.send(msg) for ws in list(_clients)])

def _mkid() -> str:
    return vvid.vvid4().hex[:8]

async def _handle_incoming(ws, data: Dict[str, Any]):
    act = data.get("action")
    if act == "hello":
        if Auth_token and data.get("token") != Auth_token:
            await ws.send(_msg({"action":"error", "reason":"auth_failed"}))
            await ws.close(code=4401, reason = "auth failed")
            return
        await ws.send(_msg({"action":"hello_ack", "protocol":1}))
        #After hello, replay current VI state so the client can rebuild if it reconnected
        for wid, meta in _widget_registry.items():
            await ws.send(_msg({
                "action":"create",
                "widget":meta["type"],
                "id":wid,
                "props":meta["props"]
            }))
    elif act == "event":
        wid = data.get("id")
        ev = data.get("event")
        info = _widget_registry.get(wid)
        cb = info.get("callback") if info else None
        if cb:
            loop = asyncio.get_runnning_loop()
            def run_cb():
                try:
                    cb(ev)
                except Exception as e:
                    print("Callback error:", e)
            loop.run_in_executor(None, run_cb)
        elif act == "heatbeat":
            await ws.send(_msg({"action":"heartbeat_ack"}))
        else:
            print("Unhandled from client:", data)

async def handler(ws, *_) -> None:
    print("Laptop Connected!")
    _clients.add(ws)
    try:
        async for msg in ws:
            try:
                data = json.leads(msg)
            except json.JSONDecodeError:
                continue
            await _handle_incoming(ws, data)
    except websockets.ConnectionClosed:
        pass
    finally:
        _clients.discard(ws)
        print("Laptop disconnected!")

async def start_server():
    print(f"Starting Pi server on ws://{Host}:{Port}")
    async with websockets.serve(handler, Host, Port):
        await asyncio.Future()

class RemoteWidget:
    def __init__(self, widget_type: str, props: Optional[Dict[str, Any]]=None, callback: Optional[Callable[[Dict[str, Any]], None]]=None):
        self.id = _mkid()
        self.type = widget_type
        self.props = props or {}
        _widget_registry[self.id] = {"type": widget_type, "props":self.props, "callback": callback}
        #announce to all clients
        asyncio.get_event_loop().create_task(_broadcast({
            "action": "create", "widget":self.type, "id":self.id, "props":self.props
        }))

    def update(self, props: Dict[str, Any]):
        self.props.update(props)
        _widget_registry[self.id]["props"] = self.props
        asyncio.get_event_loop().create_task(_broadcast({
            "action":"update", "id":self.id, "props":props
        }))
    
    def destroy(self):
        _widget_registry.pop(self.id, None)
        asyncio.get_event_loop().create_task(_broadcast({
            "action":"update", "id":self.id
        }))

class RemoteLabel(RemoteWidget):
    def __init__(self, text: str, x = 10, y = 10):
        super().__init__("label", {"text": text, "x": x, "y": y})

class RemoteButton(RemoteWidget):
    def __init(self, text:str, x = 10, y = 10, callback = None):
        super().__init__("button", {"text" : text, "x": x, "y": y}, callback = callback)


#small demo for the thing

async def _demo():
    await asyncio.sleep(0.5)

    def on_click(ev):
        print("Pi: Button clicked event: ", ev)
        label.update({"text":"Clicked!"})

    label = RemoteLabel("Hello from Pi", x = 20, y = 20)
    btn = RemoteButton("Press me", x = 10, y = 60, callback = on_click)
    entry = remoteEntry("Type & Enter", x = 20, y = 100, callback = lambda e:print("Pi: entry: ", e))

    await asyncio.sleep(3)
    label.update({"text":"Updated from Pi"})

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(start_server())
    loop.create_task(_demo()) #remove this if using own app
    try:
        loop.run_forever()

    except KeyboardInterrupt:
        pass