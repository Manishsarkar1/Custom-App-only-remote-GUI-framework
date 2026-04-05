# Shared message protocol helpers.

import json
from typing import Any, Dict, Iterable, Optional

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
ACTION_BATCH = "batch"

VALID_WIDGET_TYPES = {
    "label",
    "button",
    "entry",
    "slider",
    "checkbox",
    "dropdown",
    "progress",
    "textarea",
    "row",
    "column",
    "card",
    "scroll_column",
    "separator",
    "spinner",
    "radio_group",
}
VALID_ACTIONS = {
    ACTION_HELLO,
    ACTION_HELLO_ACK,
    ACTION_CREATE,
    ACTION_UPDATE,
    ACTION_DESTROY,
    ACTION_EVENT,
    ACTION_HEARTBEAT,
    ACTION_HEARTBEAT_ACK,
    ACTION_ERROR,
    ACTION_BATCH,
}


class ProtocolError(ValueError):
    pass



def dumps(obj: Dict[str, Any]) -> str:
    return json.dumps(obj, separators=(",", ":"))



def loads(raw: str) -> Dict[str, Any]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProtocolError(f"invalid_json: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ProtocolError("message_must_be_object")
    return data



def validate_message(data: Dict[str, Any]) -> Dict[str, Any]:
    action = data.get("action")
    if action not in VALID_ACTIONS:
        raise ProtocolError(f"invalid_action: {action}")

    if action in {ACTION_HELLO, ACTION_HELLO_ACK}:
        _require_keys(data, ("protocol",))
        if not isinstance(data["protocol"], int):
            raise ProtocolError("protocol_must_be_int")
    elif action == ACTION_CREATE:
        _require_keys(data, ("id", "widget", "props"))
        if data["widget"] not in VALID_WIDGET_TYPES:
            raise ProtocolError(f"invalid_widget: {data['widget']}")
        _validate_id(data["id"])
        _validate_props(data["props"])
    elif action == ACTION_UPDATE:
        _require_keys(data, ("id", "props"))
        _validate_id(data["id"])
        _validate_props(data["props"])
    elif action == ACTION_DESTROY:
        _require_keys(data, ("id",))
        _validate_id(data["id"])
    elif action == ACTION_EVENT:
        _require_keys(data, ("id", "event"))
        _validate_id(data["id"])
        if not isinstance(data["event"], dict):
            raise ProtocolError("event_must_be_object")
    elif action == ACTION_ERROR:
        _require_keys(data, ("reason",))
        if not isinstance(data["reason"], str):
            raise ProtocolError("reason_must_be_string")
    elif action == ACTION_BATCH:
        _require_keys(data, ("messages",))
        messages = data["messages"]
        if not isinstance(messages, list) or not messages:
            raise ProtocolError("messages_must_be_non_empty_list")
        for item in messages:
            if not isinstance(item, dict):
                raise ProtocolError("batch_item_must_be_object")
            validate_message(item)

    return data



def _require_keys(data: Dict[str, Any], keys: Iterable[str]) -> None:
    for key in keys:
        if key not in data:
            raise ProtocolError(f"missing_key: {key}")



def _validate_id(value: Any) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ProtocolError("id_must_be_non_empty_string")



def _validate_props(props: Optional[Any]) -> None:
    if not isinstance(props, dict):
        raise ProtocolError("props_must_be_object")
