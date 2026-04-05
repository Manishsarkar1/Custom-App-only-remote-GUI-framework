import asyncio
import threading
import tkinter as tk
from queue import Empty, Queue
from tkinter import ttk

import websockets

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from shared.config import AUTH_TOKEN, HEARTBEAT_INTERVAL_MS, PI_WS, RECONNECT_DELAY_MS, THEME_MODE
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

INTERNAL_STATUS = "__status__"
INTERNAL_RESET = "__reset__"
SLIDER_THROTTLE_MS = 75

PALETTES = {
    "dark": {
        "bg": "#0f172a",
        "surface": "#162033",
        "surface_alt": "#1d2a42",
        "card": "#14233a",
        "text": "#eef4ff",
        "muted": "#97abc8",
        "accent": "#4cc9f0",
        "accent_soft": "#17354d",
        "success": "#59c88f",
        "warning": "#f2c14e",
        "danger": "#f26d6d",
        "border": "#2f466a",
        "input": "#0f1c30",
    },
    "light": {
        "bg": "#eef3fb",
        "surface": "#ffffff",
        "surface_alt": "#dde8f7",
        "card": "#ffffff",
        "text": "#132238",
        "muted": "#5c6f89",
        "accent": "#1f7ae0",
        "accent_soft": "#d8e8fb",
        "success": "#2f8f56",
        "warning": "#b8860b",
        "danger": "#c84b4b",
        "border": "#bdd0e6",
        "input": "#f8fbff",
    },
}

root = tk.Tk()
root.geometry("1040x760")
root.minsize(880, 620)
root.title("Pi Remote UI")

palette = PALETTES.get(THEME_MODE, PALETTES["dark"])
style = ttk.Style()
fonts = {
    "hero": ("Segoe UI", 22, "bold"),
    "title": ("Segoe UI", 16, "bold"),
    "section": ("Segoe UI", 13, "bold"),
    "subtitle": ("Segoe UI", 10),
    "body": ("Segoe UI", 10),
    "metric": ("Segoe UI", 20, "bold"),
    "caption": ("Segoe UI", 9),
}

root.configure(bg=palette["bg"])
style.theme_use("clam")
style.configure("App.TFrame", background=palette["bg"])
style.configure("Surface.TFrame", background=palette["surface"])
style.configure("SurfaceAlt.TFrame", background=palette["surface_alt"])
style.configure("Card.TFrame", background=palette["card"], borderwidth=1, relief="solid")
style.configure("App.TLabel", background=palette["bg"], foreground=palette["text"], font=fonts["body"])
style.configure("Surface.TLabel", background=palette["surface"], foreground=palette["text"], font=fonts["body"])
style.configure("Muted.TLabel", background=palette["surface"], foreground=palette["muted"], font=fonts["caption"])
style.configure("Hero.TLabel", background=palette["surface"], foreground=palette["text"], font=fonts["hero"])
style.configure("Title.TLabel", background=palette["surface"], foreground=palette["text"], font=fonts["title"])
style.configure("Section.TLabel", background=palette["surface"], foreground=palette["text"], font=fonts["section"])
style.configure("Subtitle.TLabel", background=palette["surface"], foreground=palette["muted"], font=fonts["subtitle"])
style.configure("Metric.TLabel", background=palette["surface"], foreground=palette["accent"], font=fonts["metric"])
style.configure("Status.TLabel", background=palette["bg"], foreground=palette["muted"], font=fonts["caption"])
style.configure("TButton", font=fonts["body"], padding=(12, 8))
style.configure("Primary.TButton", font=fonts["body"], padding=(14, 9))
style.map("Primary.TButton", background=[("!disabled", palette["accent"])], foreground=[("!disabled", palette["bg"])])
style.configure("Secondary.TButton", font=fonts["body"], padding=(12, 8))
style.map("Secondary.TButton", background=[("!disabled", palette["surface_alt"])], foreground=[("!disabled", palette["text"])])
style.configure("TCheckbutton", background=palette["surface"], foreground=palette["text"], font=fonts["body"])
style.configure("TRadiobutton", background=palette["surface"], foreground=palette["text"], font=fonts["body"])
style.configure("TEntry", fieldbackground=palette["input"], foreground=palette["text"], insertcolor=palette["text"])
style.configure("TCombobox", fieldbackground=palette["input"], foreground=palette["text"])
style.configure("Accent.Horizontal.TProgressbar", troughcolor=palette["surface_alt"], background=palette["accent"], bordercolor=palette["surface_alt"], lightcolor=palette["accent"], darkcolor=palette["accent"])
style.configure("Muted.Horizontal.TProgressbar", troughcolor=palette["surface_alt"], background=palette["success"], bordercolor=palette["surface_alt"], lightcolor=palette["success"], darkcolor=palette["success"])

content = ttk.Frame(root, style="App.TFrame")
content.pack(fill="both", expand=True)
status_var = tk.StringVar(value=f"Status: Connecting to {PI_WS}")
status_label = ttk.Label(root, textvariable=status_var, anchor="w", style="Status.TLabel")
status_label.pack(fill="x", side="bottom", padx=10, pady=8)

widgets = {}
widget_vars = {}
widget_meta = {}
widget_hosts = {}
slider_jobs = {}
slider_values = {}
tooltips = {}
connected = threading.Event()

inbox: Queue = Queue()
outbox: Queue = Queue()


def set_status(text: str) -> None:
    status_var.set(f"Status: {text}")


def _show_tooltip(event, text):
    if not text:
        return
    _hide_tooltip(event)
    tooltip = tk.Toplevel(root)
    tooltip.wm_overrideredirect(True)
    tooltip.configure(bg=palette["surface_alt"])
    label = tk.Label(tooltip, text=text, bg=palette["surface_alt"], fg=palette["text"], font=fonts["caption"], padx=8, pady=5)
    label.pack()
    tooltip.wm_geometry(f"+{event.x_root + 12}+{event.y_root + 12}")
    tooltips[event.widget] = tooltip


def _hide_tooltip(event):
    tooltip = tooltips.pop(event.widget, None)
    if tooltip:
        tooltip.destroy()


def _bind_tooltip(widget, text):
    widget.unbind("<Enter>")
    widget.unbind("<Leave>")
    if text:
        widget.bind("<Enter>", lambda event, _text=text: _show_tooltip(event, _text))
        widget.bind("<Leave>", _hide_tooltip)


def clear_widgets() -> None:
    for widget in list(widgets.values()):
        try:
            widget.destroy()
        except tk.TclError:
            pass
    widgets.clear()
    widget_vars.clear()
    widget_meta.clear()
    widget_hosts.clear()
    slider_jobs.clear()
    slider_values.clear()
    for tooltip in tooltips.values():
        try:
            tooltip.destroy()
        except tk.TclError:
            pass
    tooltips.clear()


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
    elif act == ACTION_BATCH:
        for message in data.get("messages", []):
            handle_message(message)
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
    else:
        print("Unknown message:", data)


def _resolve_parent(props):
    parent_id = props.get("parent")
    if parent_id and parent_id in widget_hosts:
        return widget_hosts[parent_id]
    return content


def _is_container(widget_id):
    return widget_meta.get(widget_id, {}).get("widget") in {"row", "column", "card", "scroll_column"}


def _configure_dimensions(widget, props):
    width = props.get("width")
    height = props.get("height")
    if isinstance(width, int):
        try:
            widget.configure(width=width)
        except tk.TclError:
            pass
    if isinstance(height, int):
        try:
            widget.configure(height=height)
        except tk.TclError:
            pass


def _apply_layout(widget, wid, props):
    parent_id = props.get("parent")
    if parent_id and _is_container(parent_id):
        layout = props.get("layout", {})
        parent_kind = widget_meta[parent_id]["widget"]
        side = layout.get("side") or ("left" if parent_kind == "row" else "top")
        fill = layout.get("fill", "none")
        expand = bool(layout.get("expand", fill in {"x", "both"}))
        padx = layout.get("padx", 0)
        pady = layout.get("pady", 0)
        anchor = layout.get("anchor", "w")
        try:
            widget.place_forget()
        except tk.TclError:
            pass
        widget.pack(side=side, fill=fill, expand=expand, padx=padx, pady=pady, anchor=anchor)
        return

    x = props.get("x", 10)
    y = props.get("y", 10)
    place_kwargs = {"x": x, "y": y}
    if isinstance(props.get("width"), int):
        place_kwargs["width"] = props["width"]
    if isinstance(props.get("height"), int):
        place_kwargs["height"] = props["height"]
    try:
        widget.pack_forget()
    except tk.TclError:
        pass
    widget.place(**place_kwargs)


def _label_style(props):
    role = props.get("font_role", "body")
    return {
        "hero": "Hero.TLabel",
        "title": "Title.TLabel",
        "section": "Section.TLabel",
        "subtitle": "Subtitle.TLabel",
        "metric": "Metric.TLabel",
        "caption": "Muted.TLabel",
    }.get(role, "Surface.TLabel")


def _button_style(props):
    variant = props.get("variant", "secondary")
    return {"primary": "Primary.TButton", "secondary": "Secondary.TButton"}.get(variant, "TButton")


def _progress_style(props):
    return "Accent.Horizontal.TProgressbar" if props.get("variant") == "accent" else "Muted.Horizontal.TProgressbar"


def _apply_common_props(widget, wid, props):
    current = widget_meta.get(wid, {}).get("props", {}).copy()
    current.update(props)
    widget_meta.setdefault(wid, {})["props"] = current
    visible = current.get("visible", True)
    if not visible:
        try:
            widget.place_forget()
        except tk.TclError:
            pass
        try:
            widget.pack_forget()
        except tk.TclError:
            pass
        return
    disabled = current.get("disabled")
    if disabled is not None:
        state = "disabled" if disabled else "normal"
        try:
            widget.configure(state=state)
        except tk.TclError:
            pass
    _configure_dimensions(widget, current)
    _bind_tooltip(widget, current.get("tooltip"))
    _apply_layout(widget, wid, current)


def _set_text_like(widget, value):
    if isinstance(widget, ttk.Entry):
        widget.delete(0, "end")
        widget.insert(0, value)
    elif isinstance(widget, tk.Text):
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
    else:
        widget.config(text=value)


def _queue_slider_event(wid, value):
    slider_values[wid] = float(value)
    old_job = slider_jobs.get(wid)
    if old_job:
        root.after_cancel(old_job)

    def send_event(_wid=wid):
        outbox.put({"action": ACTION_EVENT, "id": _wid, "event": {"type": "slide", "value": slider_values[_wid]}})
        slider_jobs.pop(_wid, None)

    slider_jobs[wid] = root.after(SLIDER_THROTTLE_MS, send_event)


def _create_card(parent, props):
    outer = tk.Frame(parent, bg=palette["card"], highlightbackground=palette["border"], highlightthickness=1, bd=0)
    inner = tk.Frame(outer, bg=palette["card"])
    inner.pack(fill="both", expand=True, padx=12, pady=12)
    title = props.get("title")
    if title:
        tk.Label(inner, text=title, bg=palette["card"], fg=palette["text"], font=fonts["title"], anchor="w").pack(fill="x", pady=(0, 8))
    return outer, inner


def _create_scroll_column(parent, props):
    outer = tk.Frame(parent, bg=palette["surface"], highlightbackground=palette["border"], highlightthickness=1, bd=0)
    canvas = tk.Canvas(outer, bg=palette["surface"], highlightthickness=0, bd=0)
    scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
    viewport = ttk.Frame(canvas, style="Surface.TFrame")
    window_id = canvas.create_window((0, 0), window=viewport, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    viewport.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window_id, width=event.width))
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")
    return outer, viewport


def create_widget(data):
    wtype = data.get("widget")
    wid = data.get("id")
    props = dict(data.get("props", {}))
    if not wid:
        return
    destroy_widget(wid)
    parent = _resolve_parent(props)
    widget_meta[wid] = {"widget": wtype, "props": dict(props)}
    text = props.get("text", "") or ""

    if wtype == "label":
        w = ttk.Label(parent, text=text, style=_label_style(props), wraplength=props.get("wrap", 0))
        widget_hosts[wid] = w
    elif wtype == "button":
        w = ttk.Button(parent, text=text, style=_button_style(props))
        w.config(command=lambda _wid=wid: outbox.put({"action": ACTION_EVENT, "id": _wid, "event": {"type": "click"}}))
        widget_hosts[wid] = w
    elif wtype == "entry":
        w = ttk.Entry(parent)
        if text:
            w.insert(0, text)
        w.bind("<Return>", lambda _event, _wid=wid, _w=w: outbox.put({"action": ACTION_EVENT, "id": _wid, "event": {"type": "enter", "value": _w.get()}}))
        widget_hosts[wid] = w
    elif wtype == "slider":
        w = ttk.Scale(parent, from_=props.get("min", 0), to=props.get("max", 100), orient="horizontal")
        w.set(props.get("value", 0))
        w.config(command=lambda value, _wid=wid: _queue_slider_event(_wid, value))
        widget_hosts[wid] = w
    elif wtype == "checkbox":
        var = tk.BooleanVar(value=bool(props.get("checked", False)))
        w = ttk.Checkbutton(parent, text=props.get("label", ""), variable=var)
        w.config(command=lambda _wid=wid, _var=var: outbox.put({"action": ACTION_EVENT, "id": _wid, "event": {"type": "check", "checked": _var.get()}}))
        widget_vars[wid] = var
        widget_hosts[wid] = w
    elif wtype == "dropdown":
        var = tk.StringVar(value=props.get("value") or "")
        w = ttk.Combobox(parent, textvariable=var, values=props.get("options", []), state="readonly")
        w.bind("<<ComboboxSelected>>", lambda _event, _wid=wid, _var=var: outbox.put({"action": ACTION_EVENT, "id": _wid, "event": {"type": "select", "value": _var.get()}}))
        widget_vars[wid] = var
        widget_hosts[wid] = w
    elif wtype == "progress":
        w = ttk.Progressbar(parent, orient="horizontal", mode="determinate", maximum=props.get("max", 100), style=_progress_style(props))
        w["value"] = props.get("value", 0)
        widget_hosts[wid] = w
    elif wtype == "textarea":
        w = tk.Text(parent, wrap="word", bg=palette["input"], fg=palette["text"], insertbackground=palette["text"], relief="flat", font=fonts["body"], padx=10, pady=10)
        if text:
            w.insert("1.0", text)
        if isinstance(props.get("height"), int):
            w.configure(height=props["height"])
        if isinstance(props.get("width"), int):
            w.configure(width=props["width"])
        w.bind("<Control-Return>", lambda _event, _wid=wid, _w=w: outbox.put({"action": ACTION_EVENT, "id": _wid, "event": {"type": "submit", "value": _w.get("1.0", "end-1c")}}))
        widget_hosts[wid] = w
    elif wtype == "row":
        w = ttk.Frame(parent, style="Surface.TFrame")
        widget_hosts[wid] = w
    elif wtype == "column":
        w = ttk.Frame(parent, style="Surface.TFrame")
        widget_hosts[wid] = w
    elif wtype == "card":
        w, host = _create_card(parent, props)
        widget_hosts[wid] = host
    elif wtype == "scroll_column":
        w, host = _create_scroll_column(parent, props)
        widget_hosts[wid] = host
    elif wtype == "separator":
        w = ttk.Separator(parent, orient=props.get("orient", "horizontal"))
        widget_hosts[wid] = w
    elif wtype == "spinner":
        w = ttk.Progressbar(parent, orient="horizontal", mode="indeterminate", style="Accent.Horizontal.TProgressbar")
        w.start(12)
        widget_hosts[wid] = w
    elif wtype == "radio_group":
        w = ttk.Frame(parent, style="Surface.TFrame")
        var = tk.StringVar(value=props.get("value") or "")
        options = props.get("options", [])
        for option in options:
            radio = ttk.Radiobutton(w, text=str(option), value=str(option), variable=var)
            radio.pack(side="left", padx=8, pady=2)
        var.trace_add("write", lambda *_args, _wid=wid, _var=var: outbox.put({"action": ACTION_EVENT, "id": _wid, "event": {"type": "select", "value": _var.get()}}))
        widget_vars[wid] = var
        widget_hosts[wid] = w
    else:
        widget_meta.pop(wid, None)
        return

    widgets[wid] = w
    _apply_common_props(w, wid, props)


def update_widget(wid, props):
    if not wid or wid not in widgets:
        return
    w = widgets[wid]
    merged = widget_meta.get(wid, {}).get("props", {}).copy()
    merged.update(props)
    widget_meta[wid]["props"] = merged
    wtype = widget_meta[wid]["widget"]

    if wtype == "label":
        if "text" in props:
            w.config(text=props["text"])
        w.configure(style=_label_style(merged), wraplength=merged.get("wrap", 0))
    elif wtype == "button":
        if "text" in props:
            w.config(text=props["text"])
        w.configure(style=_button_style(merged))
    elif wtype == "entry" and "text" in props:
        _set_text_like(w, props["text"])
    elif wtype == "textarea" and "text" in props:
        _set_text_like(w, props["text"])
    elif wtype == "slider":
        if "min" in props or "max" in props:
            w.configure(from_=merged.get("min", 0), to=merged.get("max", 100))
        if "value" in props:
            w.set(props["value"])
    elif wtype == "checkbox" and "checked" in props and wid in widget_vars:
        widget_vars[wid].set(bool(props["checked"]))
    elif wtype == "dropdown":
        if "options" in props:
            w.configure(values=props["options"])
        if "value" in props and wid in widget_vars:
            widget_vars[wid].set(props["value"] or "")
    elif wtype == "progress":
        if "max" in props:
            w.configure(maximum=props["max"])
        if "value" in props:
            w["value"] = props["value"]
        w.configure(style=_progress_style(merged))
    elif wtype == "radio_group":
        if "value" in props and wid in widget_vars:
            widget_vars[wid].set(props["value"] or "")
    _apply_common_props(w, wid, props)


def destroy_widget(wid):
    if not wid:
        return
    child_ids = [child_id for child_id, meta in widget_meta.items() if meta.get("props", {}).get("parent") == wid]
    for child_id in child_ids:
        destroy_widget(child_id)
    job = slider_jobs.pop(wid, None)
    if job:
        try:
            root.after_cancel(job)
        except tk.TclError:
            pass
    slider_values.pop(wid, None)
    meta = widget_meta.pop(wid, None)
    widget_hosts.pop(wid, None)
    widget_vars.pop(wid, None)
    w = widgets.pop(wid, None)
    if w:
        try:
            if meta and meta.get("widget") == "spinner":
                w.stop()
        except Exception:
            pass
        w.destroy()


async def ws_session():
    async with websockets.connect(PI_WS, ping_interval=20, ping_timeout=20) as ws:
        connected.set()
        inbox.put({"action": INTERNAL_RESET})
        inbox.put({"action": INTERNAL_STATUS, "text": f"Connected to {PI_WS}"})
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




