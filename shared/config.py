import os
from typing import Optional



def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default

    try:
        return int(raw)
    except ValueError:
        return default



def _get_optional_str(name: str) -> Optional[str]:
    raw = os.getenv(name)
    if raw is None:
        return None

    value = raw.strip()
    return value or None


SERVER_HOST = os.getenv("REMOTE_GUI_HOST", "0.0.0.0")
SERVER_PORT = _get_int("REMOTE_GUI_PORT", 8765)
AUTH_TOKEN = _get_optional_str("REMOTE_GUI_AUTH_TOKEN")
PI_WS = os.getenv("REMOTE_GUI_PI_WS", f"ws://127.0.0.1:{SERVER_PORT}")
HEARTBEAT_INTERVAL_MS = _get_int("REMOTE_GUI_HEARTBEAT_MS", 5000)
RECONNECT_DELAY_MS = _get_int("REMOTE_GUI_RECONNECT_MS", 2000)
