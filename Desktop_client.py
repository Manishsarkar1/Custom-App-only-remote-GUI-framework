import asyncio
import websockets
import json
import click
import threading
import tkinter as tk
from tkinter import ttk

PI_WS = "ws://192.168.137.5:8765"

widgets = {}

async def ws_handler():
    async with websockets.connect(PI_WS) as ws:
        click.secho("Connected to Pi server", fg = "blue")
        #receive messages
        async for msg in ws:
            data = json.loads(msg)
            #schedule handling in tkinter mainloop
            root.after(0, handle_message, ws, data)

def handle_message(ws, data):
    action = data.get("action")
    if action == "create":
        create_widget(ws, data)
    elif action == "ack":
        click.secho(f"Pi ack {data.get("detail")}", fg = "blue")
    else:
        click.secho(f"Unknown message:{data}", fg = "red")

def create_widget(ws, data):
    wtype = data.get("widget")
    wid = data.get("id")
    props = data.get("props", {})
    x = props.get("x", 10)
    y = props.get("y", 10)
    text = props.get("text", "")

    if wtype == "button":
        btn = ttk.Button(root, text= text)
        btn.place(x = x, y = y)
        def on_click(_wid = wid):
            payload = {"action": "event", "id" : _wid, "event":{"type":"click"}}
            asyncio.run_coroutine_threadsafe(ws.send(json.dumps(payload)), loop)
        btn.config(command = on_click)
        widgets[wid] = btn

def start_ws_loop():
    global loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(ws_handler())

if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("400x300")
    root.title("Pi remote UI (client)")

    #start websocket client thread
    t = threading.Thread(target = start_ws_loop, daemon = True)
    t.start()

    root.mainloop()
