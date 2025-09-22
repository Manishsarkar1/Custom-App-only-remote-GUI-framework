import asyncio
import json
import threading
import tkinter as tk
from tkinter import ttk
from queue import Queue, Empty
import websockets

PI_WS = "ws://192.168.137.4:8765" #this is pi's ip address
AUTH_TOKEN = None

root = tk.Tk()
root.geometry("640x420")
root.title("Pi Remote UI")

widgets = {} #wid = tk widget
inbox: Queue = Queue() #ws = tk thread
outbox: Queue = Queue() # tk = ws thread

def tk_process_inbox():
    #Called by Tk every few ms to apply messages coming from websocket.
    try:
        while True:
            data = inbox.get_nowait()
            handle_message(data)

    except Empty:
        pass
    root.after(10, tk_process_inbox)

def handle_message(data):
    act = data.get("action")
    if act == "create":
        create_widget(data)
    elif act == "update":
        update_widget(data.get("id"), data.get("props", {}))
    elif act == "destroy":
        destroy_widget(data.get("id"))
    elif act in ("hello_ack", "hearbeat_ack", "error", "ack"):
        print("Info:", data)
    else:
        print("Unknown message: ", data)

def create_widget(data):
    wtype = data.get("widget")
    wid = data.get("id")
    props = data.get("props", {})
    x = props.get("x", 10)
    y = props.get("y", 10)
    text = props.get("text", "")

    if wtype == "label":
        w = ttk.Label(root, text = text)
        w.place(x = x, y = y)
        widgets[wid] = w

    elif wtype == "button":
        w = ttk.Button(root, text = text)
        w.place(x = x, y = y)
        def on_click(_wid = wid):
            outbox.put({"action" : "event", "id" : _wid, "event":{"type":"click"}})
        w.config(command = on_click)
        widgets[wid] = w

    elif wtype == "entry":
        w = ttk.Entry(root)
        w.insert(0, text)
        w.place(x = x, y = y)
        def on_return(event, _wid = wid, _w = w):
            outbox.put({"action":"event", "id": _wid, "event" : {"type":"enter", "value": _w.get()}})
        w.bind("<Return>", on_return)
        widgets[wid] = w

def update_widget(wid, props):
    w = widgets.get(wid)
    if not w: return
    if "text" in props:
        try:
            w.config(text = props["text"])
        except tk.TclError:
            #entry
            if isinstance(w, ttk.Entry):
                w.delete(0, "end"); w.insert(0, props["text"])
    if "x" in props or "y" in props:
        x = props.get("x", 10); y = props.get("y", 10)
        w.place(x = x, y = y)

def destroy_widget(wid):
    w = widgets.pop(wid, None)
    if w: w.destroy()

async def ws_loop():
    async with websockets.connect(PI_WS) as ws:
        print("Connected to Pi")
        #hello/path
        hello = {"action":"hello","protocol":1}
        if AUTH_TOKEN: hello["token"] = AUTH_TOKEN
        await ws.send(json.dumps(hello))

        async def reader():
            async for msg in ws:
                try:
                    data = json.loads(msg)
                except json.JSONDecodeError:
                    continue
                inbox.put(data)

        async def writer():
            while True:
                data = await asyncio.get_event_loop().run_in_executor(None, outbox.get)
                await ws.send(json.dumps(data))

        await asyncio.gather(reader(), writer())

def start_ws_thread():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(ws_loop())
    except Exception as e:
        print("WS thread error:", e)

if __name__ == "__main__":
    threading.Thread(target = start_ws_thread, daemon = True).start()
    root.after(10, tk_process_inbox)
    root.mainloop()