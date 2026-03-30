import unittest

from shared.protocol import (
    ACTION_CREATE,
    ACTION_ERROR,
    ACTION_HELLO,
    PROTOCOL_VERSION,
    ProtocolError,
    loads,
    validate_message,
)


class ProtocolTests(unittest.TestCase):
    def test_loads_rejects_non_object_messages(self):
        with self.assertRaises(ProtocolError):
            loads('[1, 2, 3]')

    def test_validate_create_accepts_known_widget(self):
        message = {
            "action": ACTION_CREATE,
            "id": "abc123",
            "widget": "label",
            "props": {"text": "Hello"},
        }
        self.assertEqual(validate_message(message), message)

    def test_validate_hello_requires_protocol(self):
        with self.assertRaises(ProtocolError):
            validate_message({"action": ACTION_HELLO})

    def test_validate_rejects_unknown_widget(self):
        with self.assertRaises(ProtocolError):
            validate_message(
                {
                    "action": ACTION_CREATE,
                    "id": "abc123",
                    "widget": "canvas",
                    "props": {},
                }
            )

    def test_validate_error_requires_reason(self):
        with self.assertRaises(ProtocolError):
            validate_message({"action": ACTION_ERROR})

    def test_validate_hello_accepts_protocol(self):
        message = {"action": ACTION_HELLO, "protocol": PROTOCOL_VERSION}
        self.assertEqual(validate_message(message), message)


if __name__ == "__main__":
    unittest.main()
