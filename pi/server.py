import asyncio
import logging
import uuid
from typing import Any, Callable, Dict, List, Optional

import websockets

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from shared.config import AUTH_TOKEN, SERVER_HOST, SERVER_PORT
from shared.protocol import (
    ACTION_BATCH,
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
    ProtocolError,
    dumps,
    loads,
    validate_message,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("remote_gui.server")

_clients = set()
_widget_registry: Dict[str, Dict[str, Any]] = {}


def _mkid() -> str:
    return uuid.uuid4().hex[:8]


def _error(reason: str) -> Dict[str, Any]:
    return {"action": ACTION_ERROR, "reason": reason}


def _create_message(widget_id: str, widget_type: str, props: Dict[str, Any]) -> Dict[str, Any]:
    return {"action": ACTION_CREATE, "widget": widget_type, "id": widget_id, "props": props}


async def _send(ws, obj: Dict[str, Any]) -> None:
    await ws.send(dumps(validate_message(obj)))


async def _broadcast(obj: Dict[str, Any]):
    if not _clients:
        return
    msg = dumps(validate_message(obj))
    clients = list(_clients)
    results = await asyncio.gather(*(ws.send(msg) for ws in clients), return_exceptions=True)
    for ws, res in zip(clients, results):
        if isinstance(res, Exception):
            logger.warning("Dropping client after send failure: %s", res)
            _clients.discard(ws)


async def _broadcast_many(messages: List[Dict[str, Any]]) -> None:
    if messages:
        await _broadcast({"action": ACTION_BATCH, "messages": messages})


def _safe_cb(ev: Dict[str, Any], cb: Callable[[Dict[str, Any]], None]):
    try:
        cb(ev)
    except Exception:
        logger.exception("Callback error")


async def _replay_ui_state(ws) -> None:
    messages = [_create_message(wid, meta["type"], meta["props"]) for wid, meta in _widget_registry.items()]
    if messages:
        await _send(ws, {"action": ACTION_BATCH, "messages": messages})


async def _handle_incoming(ws, data: Dict[str, Any]):
    act = data.get("action")
    if act == ACTION_BATCH:
        for message in data.get("messages", []):
            await _handle_incoming(ws, message)
        return
    if act == ACTION_HELLO:
        if data.get("protocol") != PROTOCOL_VERSION:
            await _send(ws, _error("protocol_mismatch"))
            await ws.close(code=4400, reason="Protocol Mismatch")
            return
        if AUTH_TOKEN and data.get("token") != AUTH_TOKEN:
            await _send(ws, _error("auth_failed"))
            await ws.close(code=4401, reason="Auth Failed")
            return
        await _send(ws, {"action": ACTION_HELLO_ACK, "protocol": PROTOCOL_VERSION})
        await _replay_ui_state(ws)
    elif act == ACTION_EVENT:
        wid = data.get("id")
        ev = data.get("event")
        info = _widget_registry.get(wid)
        cb = info.get("callback") if info else None
        if cb and isinstance(ev, dict):
            _safe_cb(ev, cb)
    elif act == ACTION_HEARTBEAT:
        await _send(ws, {"action": ACTION_HEARTBEAT_ACK})
    else:
        logger.warning("Unhandled client message: %s", data)


async def handler(ws, *_):
    logger.info("Desktop connected")
    _clients.add(ws)
    try:
        async for raw in ws:
            try:
                data = validate_message(loads(raw))
            except ProtocolError as exc:
                logger.warning("Rejected client message: %s", exc)
                await _send(ws, _error(str(exc)))
                continue
            await _handle_incoming(ws, data)
    except websockets.ConnectionClosed:
        logger.info("Desktop disconnected")
    finally:
        _clients.discard(ws)


async def start_server():
    logger.info("Starting Pi server on ws://%s:%s", SERVER_HOST, SERVER_PORT)
    async with websockets.serve(handler, SERVER_HOST, SERVER_PORT, ping_interval=20, ping_timeout=20):
        await asyncio.Future()


class RemoteWidget:
    def __init__(self, widget_type: str, props: Optional[Dict[str, Any]] = None, callback: Optional[Callable[[Dict[str, Any]], None]] = None, widget_id: Optional[str] = None):
        self.id = widget_id or _mkid()
        self.type = widget_type
        self.props = props or {}
        _widget_registry[self.id] = {"type": widget_type, "props": dict(self.props), "callback": callback}
        asyncio.get_running_loop().create_task(_broadcast(_create_message(self.id, self.type, self.props)))

    def update(self, props: Dict[str, Any]):
        self.props.update(props)
        _widget_registry[self.id]["props"] = dict(self.props)
        asyncio.get_running_loop().create_task(_broadcast({"action": ACTION_UPDATE, "id": self.id, "props": props}))

    def destroy(self):
        child_ids = [wid for wid, meta in _widget_registry.items() if meta["props"].get("parent") == self.id]
        for child_id in child_ids:
            _widget_registry.pop(child_id, None)
        _widget_registry.pop(self.id, None)
        messages = [{"action": ACTION_DESTROY, "id": child_id} for child_id in child_ids]
        messages.append({"action": ACTION_DESTROY, "id": self.id})
        asyncio.get_running_loop().create_task(_broadcast_many(messages))


def _base_props(x=10, y=10, parent=None, layout=None, **props):
    payload = {"x": x, "y": y}
    if parent:
        payload["parent"] = parent.id if isinstance(parent, RemoteWidget) else parent
    if layout:
        payload["layout"] = layout
    payload.update(props)
    return payload


class RemoteRow(RemoteWidget):
    def __init__(self, x=10, y=10, parent=None, layout=None, **props):
        super().__init__("row", _base_props(x, y, parent, layout, **props))


class RemoteColumn(RemoteWidget):
    def __init__(self, x=10, y=10, parent=None, layout=None, **props):
        super().__init__("column", _base_props(x, y, parent, layout, **props))


class RemoteCard(RemoteWidget):
    def __init__(self, title="", x=10, y=10, parent=None, layout=None, **props):
        super().__init__("card", _base_props(x, y, parent, layout, title=title, **props))


class RemoteScrollColumn(RemoteWidget):
    def __init__(self, x=10, y=10, parent=None, layout=None, **props):
        super().__init__("scroll_column", _base_props(x, y, parent, layout, **props))


class RemoteLabel(RemoteWidget):
    def __init__(self, text: str, x=10, y=10, parent=None, layout=None, **props):
        super().__init__("label", _base_props(x, y, parent, layout, text=text, **props))


class RemoteButton(RemoteWidget):
    def __init__(self, text: str, x=10, y=10, callback=None, parent=None, layout=None, **props):
        super().__init__("button", _base_props(x, y, parent, layout, text=text, **props), callback=callback)


class RemoteEntry(RemoteWidget):
    def __init__(self, text="", x=10, y=10, callback=None, parent=None, layout=None, **props):
        super().__init__("entry", _base_props(x, y, parent, layout, text=text, **props), callback=callback)


class RemoteCheckbox(RemoteWidget):
    def __init__(self, label: str, checked=False, x=10, y=10, callback=None, parent=None, layout=None, **props):
        super().__init__("checkbox", _base_props(x, y, parent, layout, label=label, checked=checked, **props), callback=callback)


class RemoteSlider(RemoteWidget):
    def __init__(self, min_value=0, max_value=100, value=50, x=10, y=10, callback=None, parent=None, layout=None, **props):
        super().__init__("slider", _base_props(x, y, parent, layout, min=min_value, max=max_value, value=value, **props), callback=callback)


class RemoteDropdown(RemoteWidget):
    def __init__(self, options, value=None, x=10, y=10, callback=None, parent=None, layout=None, **props):
        super().__init__("dropdown", _base_props(x, y, parent, layout, options=list(options), value=value, **props), callback=callback)


class RemoteProgress(RemoteWidget):
    def __init__(self, value=0, maximum=100, x=10, y=10, parent=None, layout=None, **props):
        super().__init__("progress", _base_props(x, y, parent, layout, value=value, max=maximum, **props))


class RemoteTextArea(RemoteWidget):
    def __init__(self, text="", x=10, y=10, callback=None, parent=None, layout=None, **props):
        super().__init__("textarea", _base_props(x, y, parent, layout, text=text, **props), callback=callback)


class RemoteSeparator(RemoteWidget):
    def __init__(self, x=10, y=10, parent=None, layout=None, **props):
        super().__init__("separator", _base_props(x, y, parent, layout, **props))


class RemoteSpinner(RemoteWidget):
    def __init__(self, x=10, y=10, parent=None, layout=None, **props):
        super().__init__("spinner", _base_props(x, y, parent, layout, **props))


class RemoteRadioGroup(RemoteWidget):
    def __init__(self, options, value=None, x=10, y=10, callback=None, parent=None, layout=None, **props):
        super().__init__("radio_group", _base_props(x, y, parent, layout, options=list(options), value=value, **props), callback=callback)


async def _demo():
    await asyncio.sleep(0.5)

    page = RemoteScrollColumn(x=20, y=20, width=900, height=640)
    hero = RemoteCard("Remote Control Center", parent=page, layout={"fill": "x", "padx": 16, "pady": 14})
    stats = RemoteRow(parent=page, layout={"fill": "x", "padx": 16, "pady": 6})
    controls = RemoteCard("Interactive Controls", parent=page, layout={"fill": "x", "padx": 16, "pady": 10})
    notes = RemoteCard("Notes And Activity", parent=page, layout={"fill": "x", "padx": 16, "pady": 10})

    title = RemoteLabel("Edge UI Demo", parent=hero, layout={"padx": 12, "pady": 6}, font_role="hero")
    RemoteLabel("A more polished remote-rendered dashboard with themed cards, tooltips, scroll areas, and richer widgets.", parent=hero, layout={"padx": 12, "pady": 2}, font_role="subtitle", wrap=720)
    progress = RemoteProgress(value=42, maximum=100, parent=hero, layout={"fill": "x", "padx": 12, "pady": 10}, variant="accent")

    cpu = RemoteCard("CPU", parent=stats, layout={"padx": 8, "pady": 6}, width=220)
    mem = RemoteCard("Memory", parent=stats, layout={"padx": 8, "pady": 6}, width=220)
    mode_card = RemoteCard("Mode", parent=stats, layout={"padx": 8, "pady": 6}, width=220)

    cpu_value = RemoteLabel("37%", parent=cpu, layout={"padx": 10, "pady": 10}, font_role="metric")
    mem_value = RemoteLabel("61%", parent=mem, layout={"padx": 10, "pady": 10}, font_role="metric")
    RemoteLabel("Balanced", parent=mode_card, layout={"padx": 10, "pady": 10}, font_role="metric")

    RemoteLabel("Pick a performance profile", parent=controls, layout={"padx": 12, "pady": 8}, font_role="section")

    def on_mode(ev):
        value = ev.get("value", "Balanced")
        title.update({"text": f"Edge UI Demo - {value}"})

    RemoteRadioGroup(["Quiet", "Balanced", "Turbo"], value="Balanced", parent=controls, layout={"padx": 12, "pady": 4}, callback=on_mode, tooltip="Choose how aggressively the edge device should run.")
    RemoteSeparator(parent=controls, layout={"fill": "x", "padx": 12, "pady": 10})

    def on_click(_ev):
        progress.update({"value": 78})
        cpu_value.update({"text": "52%"})
        mem_value.update({"text": "68%"})

    def on_slider(ev):
        progress.update({"value": int(ev.get("value", 0))})

    def on_dropdown(ev):
        logger.info("Dropdown: %s", ev)

    def on_entry(ev):
        logger.info("Entry: %s", ev)

    def on_textarea(ev):
        logger.info("Text area: %s", ev)

    action_row = RemoteRow(parent=controls, layout={"padx": 12, "pady": 4})
    RemoteButton("Deploy Update", parent=action_row, layout={"padx": 6, "pady": 6}, callback=on_click, variant="primary", tooltip="Trigger a simulated deploy.")
    RemoteButton("Run Diagnostics", parent=action_row, layout={"padx": 6, "pady": 6}, callback=lambda ev: logger.info("Diagnostics: %s", ev), variant="secondary")
    RemoteSlider(0, 100, 42, parent=controls, layout={"fill": "x", "padx": 12, "pady": 8}, callback=on_slider, tooltip="Adjust target utilization.")
    RemoteDropdown(["North Wing", "Lab Bench", "Greenhouse"], value="Lab Bench", parent=controls, layout={"padx": 12, "pady": 8}, callback=on_dropdown, tooltip="Pick a device group.")
    RemoteEntry("operator@example.com", parent=controls, layout={"padx": 12, "pady": 8}, callback=on_entry, tooltip="Press Enter to submit.")
    RemoteCheckbox("Enable verbose telemetry", checked=True, parent=controls, layout={"padx": 12, "pady": 6}, callback=lambda ev: logger.info("Checkbox: %s", ev))
    RemoteSpinner(parent=controls, layout={"fill": "x", "padx": 12, "pady": 8})

    RemoteLabel("Operator Notes", parent=notes, layout={"padx": 12, "pady": 8}, font_role="section")
    RemoteTextArea("System stable. Waiting for next sync window.", parent=notes, layout={"fill": "x", "padx": 12, "pady": 8}, callback=on_textarea, height=7, tooltip="Press Ctrl+Enter to submit notes.")

    await asyncio.sleep(3)
    title.update({"text": "Edge UI Demo - Live"})
    progress.update({"value": 58})


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(start_server())
    loop.create_task(_demo())
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        logger.info("Server stopped")



