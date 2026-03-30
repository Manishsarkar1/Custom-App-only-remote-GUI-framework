import asyncio
import threading
import tkinter as tk
from queue import Empty, Queue
from tkinter import ttk

import websockets

import os
import sys

# Allow running this script from its folder or repo root.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from shared.config import AUTH_TOKEN, HEARTBEAT_INTERVAL_MS, PI_WS, RECONNECT_DELAY_MS
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
    ProtocolError,
    dumps,
    loads,
    validate_message,
)

INTERNAL_STATUS = "__status__"
INTERNAL_RESET = "__reset__"

root = tk.Tk()
root.geometry("640x420")
root.title("Pi Remote UI")

content = ttk.Frame(root)
content.pack(fill="both", expand=True)

status_var = tk.StringVar(value=f"Status: Connecting to {PI_WS}")
status_label = ttk.Label(root, textvariable=status_var, anchor="w")
status_label.pack(fill="x", side="bottom", padx=8, pady=6)

widgets = {}
widget_vars = {}
connected = threading.Event()

inbox: Queue = Queue()
outbox: Queue = Queue()



def set_status(text: str) -> None:
    status_var.set(f"Status: {text}")



def clear_widgets() -> None:
    for widget in widgets.values():
        widget.destroy()
    widgets.clear()
    widget_vars.clear()



def tk_process_inbox():
    try:
        while True:
            data = inbox.get_nowait()
            handle_message(data)
    except Empty:
        pass

    root.after(10, tk_process_inbox)



def handle_message(data):
    act = data.get("action")

    if act == INTERNAL_STATUS:
        set_status(data.get("text", "Unknown"))
    elif act == INTERNAL_RESET:
        clear_widgets()
    elif act == ACTION_CREATE:
        create_widget(data)
    elif act == ACTION_UPDATE:
        update_widget(data.get("id"), data.get("props", {}))
    elif act == ACTION_DESTROY:
        destroy_widget(data.get("id"))
    elif act in (ACTION_HELLO_ACK, ACTION_HEARTBEAT_ACK):
        set_status(f"Connected to {PI_WS}")
    elif act == ACTION_ERROR:
        set_status(f"Server error: {data.get('reason', 'unknown')}")
        print("Server error:", data)
    else:
        print("Unknown message:", data)



def create_widget(data):
    wtype = data.get("widget")
    wid = data.get("id")
    props = data.get("props", {})

    if not wid:
        return

    destroy_widget(wid)

    x = props.get("x", 10)
    y = props.get("y", 10)
    text = props.get("text", props.get("placeholder", "")) or ""

    if wtype == "label":
        w = ttk.Label(content, text=text)
        w.place(x=x, y=y)
        widgets[wid] = w

    elif wtype == "button":
        w = ttk.Button(content, text=text)
        w.place(x=x, y=y)

        def on_click(_wid=wid):
            outbox.put({"action": ACTION_EVENT, "id": _wid, "event": {"type": "click"}})

        w.config(command=on_click)
        widgets[wid] = w

    elif wtype == "entry":
        w = ttk.Entry(content)
        if text:
            w.insert(0, text)
        w.place(x=x, y=y)

        def on_return(_event, _wid=wid, _w=w):
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
            content,
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
        w = ttk.Checkbutton(content, text=props.get("label", ""), variable=var)
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



async def ws_session():
    async with websockets.connect(PI_WS, ping_interval=20, ping_timeout=20) as ws:
        connected.set()
        inbox.put({"action": INTERNAL_RESET})
        inbox.put({"action": INTERNAL_STATUS, "text": f"Connected to {PI_WS}"})
        print("Connected to Pi")

        hello = {"action": ACTION_HELLO, "protocol": PROTOCOL_VERSION}
        if AUTH_TOKEN:
            hello["token"] = AUTH_TOKEN
        await ws.send(dumps(validate_message(hello)))

        async def reader():
            async for raw in ws:
                try:
                    data = validate_message(loads(raw))
                except ProtocolError as exc:
                    inbox.put({"action": INTERNAL_STATUS, "text": f"Bad server message: {exc}"})
                    continue
                inbox.put(data)

        async def writer():
            loop = asyncio.get_running_loop()
            while True:
                data = await loop.run_in_executor(None, outbox.get)
                await ws.send(dumps(validate_message(data)))

        await asyncio.gather(reader(), writer())



async def ws_loop_forever():
    while True:
        try:
            inbox.put({"action": INTERNAL_STATUS, "text": f"Connecting to {PI_WS}"})
            await ws_session()
        except Exception as exc:
            print("WS thread error:", exc)
            inbox.put({"action": INTERNAL_RESET})
            inbox.put({"action": INTERNAL_STATUS, "text": f"Reconnecting in {RECONNECT_DELAY_MS} ms"})
            connected.clear()
            await asyncio.sleep(RECONNECT_DELAY_MS / 1000)
        else:
            connected.clear()
            inbox.put({"action": INTERNAL_RESET})
            inbox.put({"action": INTERNAL_STATUS, "text": f"Disconnected from {PI_WS}"})
            await asyncio.sleep(RECONNECT_DELAY_MS / 1000)



def start_ws_thread():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(ws_loop_forever())



def schedule_heartbeat():
    if connected.is_set():
        outbox.put({"action": ACTION_HEARTBEAT})
    root.after(HEARTBEAT_INTERVAL_MS, schedule_heartbeat)


if __name__ == "__main__":
    threading.Thread(target=start_ws_thread, daemon=True).start()
    root.after(10, tk_process_inbox)
    root.after(HEARTBEAT_INTERVAL_MS, schedule_heartbeat)
    root.mainloop()

