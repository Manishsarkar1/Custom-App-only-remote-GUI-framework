# Shared message protocol helpers.

import json
from typing import Any, Dict

PROTOCOL_VERSION = 1

ACTION_HELLO = "hello"
ACTION_HELLO_ACK = "hello_ack"
ACTION_CREATE = "create"
ACTION_UPDATE = "update"
ACTION_DESTROY = "destroy"
ACTION_EVENT = "event"
ACTION_HEARTBEAT = "heartbeat"
ACTION_HEARTBEAT_ACK = "heartbeat_ack"
ACTION_ERROR = "error"


def dumps(obj: Dict[str, Any]) -> str:
    # Compact JSON for websocket payloads.
    return json.dumps(obj, separators=(",", ":"))
