import asyncio
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Dict

import pytest

# Ensure the project root is on the import path for tests without installation
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loxone_api.client import LoxoneApiError, LoxoneClient, TokenInfo


class FakeResponse:
    def __init__(self, status: int = 200, body: str = "", json_data: Dict | None = None):
        self.status = status
        self._body = body
        self._json_data = json_data or {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def text(self):
        if self._body:
            return self._body
        return json.dumps(self._json_data)

    async def json(self, content_type=None):
        return self._json_data


class FakeSession:
    def __init__(self, responses: Dict[str, FakeResponse]):
        self.responses = responses

    def get(self, url, **kwargs):
        return self.responses[url]

    async def close(self):
        pass


def test_base_url_scheme_switch():
    client_tls = LoxoneClient("example.com", "user", "pass")
    client_plain = LoxoneClient("example.com", "user", "pass", use_tls=False, port=8080)

    assert client_tls.base_url == "https://example.com:443"
    assert client_plain.base_url == "http://example.com:8080"


def test_authenticate_sets_token():
    key_url = "https://example.com:443/jdev/sys/getkey"
    auth_hash = hashlib.sha1("passabcd".encode("utf-8")).hexdigest()
    auth_url = f"https://example.com:443/jdev/sys/getjwt/user/{auth_hash}"
    response_body = json.dumps({"LL": {"value": "jwt-token", "controlInfo": {"validUntil": time.time() + 1000}}})
    session = FakeSession(
        {
            key_url: FakeResponse(json_data={"LL": {"value": "abcd"}}),
            auth_url: FakeResponse(status=200, body=response_body),
        }
    )
    client = LoxoneClient("example.com", "user", "pass", session=session)
    client._session = session

    asyncio.run(client._authenticate())

    assert client._token is not None
    assert client._token.token == "jwt-token"
    assert client._token.valid_until > time.time()


def test_authenticate_handles_error_status():
    key_url = "https://example.com:443/jdev/sys/getkey"
    auth_hash = hashlib.sha1("passabcd".encode("utf-8")).hexdigest()
    auth_url = f"https://example.com:443/jdev/sys/getjwt/user/{auth_hash}"
    session = FakeSession(
        {
            key_url: FakeResponse(json_data={"LL": {"value": "abcd"}}),
            auth_url: FakeResponse(status=401, body="unauthorized"),
        }
    )
    client = LoxoneClient("example.com", "user", "pass", session=session)
    client._session = session

    with pytest.raises(LoxoneApiError):
        asyncio.run(client._authenticate())


def test_load_structure_populates_controls():
    base_url = "https://example.com:443"
    structure_url = f"{base_url}/data/LoxAPP3.json"
    structure = {
        "controls": {
            "uuid-1": {
                "name": "Light", "type": "switch", "room": 1, "cat": 2, "states": {"active": True}
            }
        },
        "rooms": {"1": {"name": "Living Room"}},
        "cats": {"2": {"name": "Lighting"}},
    }
    session = FakeSession({structure_url: FakeResponse(json_data=structure)})
    client = LoxoneClient("example.com", "user", "pass", session=session)
    client._session = session
    client._token = TokenInfo(token="abc", valid_until=time.time() + 1000)

    asyncio.run(client._load_structure())

    assert "uuid-1" in client.controls
    control = client.get_control("uuid-1")
    assert control is not None
    assert control.name == "Light"
    assert control.room == "Living Room"
    assert control.category == "Lighting"
    assert control.states == {"active": True}


def test_handle_message_invokes_callback():
    client = LoxoneClient("example.com", "user", "pass")
    client._controls = {"uuid-1": None}
    received_states = []

    client.register_callback(lambda state: received_states.append(state))

    asyncio.run(client._handle_message(json.dumps({"uuid-1": 42})))

    assert len(received_states) == 1
    assert received_states[0].control_uuid == "uuid-1"
    assert received_states[0].value == 42
