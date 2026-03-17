import asyncio
import json
import threading
import tkinter as tk
from tkinter import ttk
from queue import Queue, Empty

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
)

# This is the Pi's websocket endpoint.
PI_WS = "ws://192.168.137.5:8765"
AUTH_TOKEN = None

root = tk.Tk()
root.geometry("640x420")
root.title("Pi Remote UI")

widgets = {}  # wid -> tk widget
widget_vars = {}  # wid -> tk.Variable (e.g., BooleanVar for checkbox)

inbox: Queue = Queue()  # ws -> tk thread
outbox: Queue = Queue()  # tk -> ws thread


def tk_process_inbox():
    # Called by Tk every few ms to apply messages coming from websocket.
    try:
        while True:
            data = inbox.get_nowait()
            handle_message(data)
    except Empty:
        pass

    root.after(10, tk_process_inbox)


def handle_message(data):
    act = data.get("action")

    if act == ACTION_CREATE:
        create_widget(data)
    elif act == ACTION_UPDATE:
        update_widget(data.get("id"), data.get("props", {}))
    elif act == ACTION_DESTROY:
        destroy_widget(data.get("id"))
    elif act in (ACTION_HELLO_ACK, ACTION_HEARTBEAT_ACK, ACTION_ERROR):
        print("Info:", data)
    else:
        print("Unknown message:", data)


def create_widget(data):
    wtype = data.get("widget")
    wid = data.get("id")
    props = data.get("props", {})

    x = props.get("x", 10)
    y = props.get("y", 10)
    text = props.get("text", props.get("placeholder", "")) or ""

    if wtype == "label":
        w = ttk.Label(root, text=text)
        w.place(x=x, y=y)
        widgets[wid] = w

    elif wtype == "button":
        w = ttk.Button(root, text=text)
        w.place(x=x, y=y)

        def on_click(_wid=wid):
            outbox.put({"action": ACTION_EVENT, "id": _wid, "event": {"type": "click"}})

        w.config(command=on_click)
        widgets[wid] = w

    elif wtype == "entry":
        w = ttk.Entry(root)
        if text:
            w.insert(0, text)
        w.place(x=x, y=y)

        def on_return(event, _wid=wid, _w=w):
            outbox.put(
                {
                    "action": ACTION_EVENT,
                    "id": _wid,
                    "event": {"type": "enter", "value": _w.get()},
                }
            )

        w.bind("<Return>", on_return)
        widgets[wid] = w

    elif wtype == "slider":
        w = ttk.Scale(
            root,
            from_=props.get("min", 0),
            to=props.get("max", 100),
            orient="horizontal",
        )
        w.set(props.get("value", 0))
        w.place(x=x, y=y)

        def on_slide(val, _wid=wid):
            outbox.put(
                {
                    "action": ACTION_EVENT,
                    "id": _wid,
                    "event": {"type": "slide", "value": float(val)},
                }
            )

        w.config(command=on_slide)
        widgets[wid] = w

    elif wtype == "checkbox":
        var = tk.BooleanVar(value=bool(props.get("checked", False)))
        w = ttk.Checkbutton(root, text=props.get("label", ""), variable=var)
        w.place(x=x, y=y)

        def on_check(_wid=wid, _var=var):
            outbox.put(
                {
                    "action": ACTION_EVENT,
                    "id": _wid,
                    "event": {"type": "check", "checked": _var.get()},
                }
            )

        w.config(command=on_check)
        widgets[wid] = w
        widget_vars[wid] = var


def update_widget(wid, props):
    if not wid:
        return

    w = widgets.get(wid)
    if not w:
        return

    if "text" in props:
        try:
            w.config(text=props["text"])
        except tk.TclError:
            # Entry widgets use insert/delete instead of config(text=...)
            if isinstance(w, ttk.Entry):
                w.delete(0, "end")
                w.insert(0, props["text"])

    if "value" in props and isinstance(w, ttk.Scale):
        try:
            w.set(props["value"])
        except tk.TclError:
            pass

    if "checked" in props and wid in widget_vars:
        try:
            widget_vars[wid].set(bool(props["checked"]))
        except tk.TclError:
            pass

    if "x" in props or "y" in props:
        x = props.get("x", 10)
        y = props.get("y", 10)
        w.place(x=x, y=y)


def destroy_widget(wid):
    if not wid:
        return

    w = widgets.pop(wid, None)
    widget_vars.pop(wid, None)
    if w:
        w.destroy()


async def ws_loop():
    async with websockets.connect(PI_WS) as ws:
        print("Connected to Pi")

        hello = {"action": ACTION_HELLO, "protocol": PROTOCOL_VERSION}
        if AUTH_TOKEN:
            hello["token"] = AUTH_TOKEN
        await ws.send(json.dumps(hello))

        async def reader():
            async for msg in ws:
                try:
                    data = json.loads(msg)
                except json.JSONDecodeError:
                    continue
                inbox.put(data)

        async def writer():
            loop = asyncio.get_running_loop()
            while True:
                data = await loop.run_in_executor(None, outbox.get)
                await ws.send(json.dumps(data))

        await asyncio.gather(reader(), writer())


def start_ws_thread():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(ws_loop())
    except Exception as e:
        print("WS thread error:", e)


def schedule_heartbeat():
    outbox.put({"action": ACTION_HEARTBEAT})
    root.after(5000, schedule_heartbeat)


if __name__ == "__main__":
    threading.Thread(target=start_ws_thread, daemon=True).start()
    root.after(10, tk_process_inbox)
    root.after(5000, schedule_heartbeat)
    root.mainloop()

