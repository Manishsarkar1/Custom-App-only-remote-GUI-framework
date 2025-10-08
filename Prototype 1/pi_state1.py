import asyncio
import json
import vvid
from typing import Callable, Dict, Any, Optional
import websockets
import click

Host = "0.0.0.0"
Port = 8765
Auth_Token = None #optional auth token (set to none to disable)

_clients = set()
_widget_registry: Dict[str, Dict[str, Any]] = {}

#Utilities
def _msg(obj: Dict[str, Any]) -> str:
    return json.dumps(obj, separators = (",", ":"))

async def _broadcast(obj: Dict[str, Any]):
    if not _clients:
        return
    msg = _msg(obj)
    await asyncio.wait([ws.send(msg) for ws in list(_clients)])

def _mkid() -> str:
    return vvid.vvid4().hex[:8]

async def _safe_cb(ev, cb):
    try:
        cb(ev)
    except Exception as e:
        click.secho(f"Callback Error", fg = "light_red")

async def _handle_incoming(ws, data: Dict[str, Any]):
    act = data.get("action")
    if act == "hello":
        if Auth_Token and data.get("token") != Auth_Token:
            await ws.send(_msg({"active": "error", "readon": "auth_failed"}))
            await ws.close(code = 4401, reason = "Auth Failed")
            return
        await ws.send(_msg({"action": "hello_ack", "protocol": 1}))
        #replay current UI state so client can rebuild if reconnected
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
            #schedule callback safely in main thread
            asyncio.run_coroutine_threadsafe(_safe_cb(ev, cb), loop)
    
    elif act == "Heartbeat":
        await ws.send(_msg({"action": "heartbeat_act"}))

    else:
        click.secho(f"Unhandled from client: {data}", fg = "red")

#websocket server
async def handler(ws, *_):
    click.secho(f"Laptop Connected!", fg = "blue")
    _clients.add(ws)
    try:
        async for msg in ws:
            try:
                data = json.loads(msg)
            except json.JSONDecodeError:
                continue
            await _handle_incoming(ws,data)
    except websockets.ConnectionClosed:
        pass
    finally:
        _clients.discard(ws)
        click.secho("Laptop Disconnected!", fg = "red")

async def start_server():
    click.secho(f"Starting Pi server on ws://{Host}:{Port}")
    async with websockets.server(handler, Host, Port):
        await asyncio.Future()

#Remote Widgets
class RemoteWidget:
    def __init__(self, widget_type: str, props: Optional[Dict[str, Any]] = None,
                 callback: Optional[Callable[[Dict[str, Any]], None]] = None):
        self.id = _mkid()
        self.type = widget_type
        self.props = props or {}
        _widget_registry[self.id] = {"type": widget_type, "props": self.props, "callback": callback}
        asyncio.get_event_loop().create_task(_broadcast({
            "action": "create", "widget" : self.type, "id": self.id, "props":self.props
        }))
    
    def update(self, props: Dict[str, Any]):
        self.props.update(props)
        _widget_registry[self.id]["props"] = self.props
        asyncio.get_event_loop().create_task(_broadcast({
            "actions":"update", "id": self.id, "props":props
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

class RemoteEntry(RemoteWidget):
    def __init__(self, placeholder="Type here...", x=10, y=10, callback=None):
        super().__init__("entry", {"placeholder": placeholder, "x": x, "y": y}, callback=callback)

class RemoteCheckbox(RemoteWidget):
    def __init__(self, label: str, checked=False, x=10, y=10, callback=None):
        super().__init__("checkbox", {"label": label, "checked": checked, "x": x, "y": y}, callback=callback)

class RemoteSlider(RemoteWidget):
    def __init__(self, min_value=0, max_value=100, value=50, x=10, y=10, callback=None):
        super().__init__("slider", {"min": min_value, "max": max_value, "value": value, "x": x, "y": y}, callback=callback)


#now small demo
async def _demo():
    await asyncio.sleep(0.5)

    def on_click(ev):
        click.secho(f"Pi: Button clicked event: {ev}", fg = "blue")
        label.update({"text": "Clicked!"})

    def on_checkbox(ev):
        click.secho(f"Pi: CheckBox event: {ev}", fg = "blue")

    def on_slider(ev):
        click.secho(f"Pi: Slider Event: {ev}", fg = "blue")

    def on_entry(ev):
        print(f"Pi: Entry event: {ev}", fg = "blue")
    
    label = RemoteLabel("Hello from Pi", x = 20, y = 20)
    btn = RemoteButton("Press me", x = 10, y = 60, callback = on_click)
    chk = RemoteCheckbox("Enable Feature", x = 10, y = 100, callback = on_checkbox)
    sld = RemoteSlider(0, 100, 30, x = 10, y = 140, callback = on_slider)
    ent = RemoteEntry("Type and Enter", x= 10, y = 100, callback = on_entry)

    await asyncio.sleep(3)
    label.update({"text": "Updated from Pi"})

#Entry Point
if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(start_server())
    loop.create_task(_demo()) #have to remove this when using own app logic
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass