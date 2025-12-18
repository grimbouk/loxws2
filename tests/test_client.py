import asyncio
import json
import sys
from pathlib import Path

import pytest

# Ensure the project root is on the import path for tests without installation
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loxone_api.client import GetKey2Result, LoxoneAuthError, LoxoneClient, LoxoneRequestError


def test_getkey2_parses_success(monkeypatch):
    client = LoxoneClient(host="example.com", user="user", password="pass")

    async def fake_get_json(self, path):
        assert path == "/jdev/sys/getkey2/user"
        return 200, {"LL": {"code": 200, "value": {"key": "abcd", "salt": "ef", "hashAlg": "SHA256"}}}

    monkeypatch.setattr(LoxoneClient, "_get_json", fake_get_json)

    result = asyncio.run(client.getkey2())
    assert isinstance(result, GetKey2Result)
    assert result.key == "abcd"
    assert result.salt == "ef"
    assert result.hashAlg == "SHA256"


def test_getkey2_invalid_response_raises(monkeypatch):
    client = LoxoneClient(host="example.com", user="user", password="pass")

    async def fake_get_json(self, path):
        return 200, {"LL": {"code": 200, "value": {"key": "", "salt": ""}}}

    monkeypatch.setattr(LoxoneClient, "_get_json", fake_get_json)

    with pytest.raises(LoxoneRequestError):
        asyncio.run(client.getkey2())


def test_authenticate_sets_jwt(monkeypatch):
    client = LoxoneClient(host="example.com", user="user", password="pass")

    async def fake_getkey2(self):
        return GetKey2Result(key="aa", salt="bb", hashAlg="SHA1")

    async def fake_get_text(self, path):
        token_response = {"LL": {"value": "jwt-token"}}
        return 200, json.dumps(token_response)

    monkeypatch.setattr(LoxoneClient, "getkey2", fake_getkey2)
    monkeypatch.setattr(LoxoneClient, "_get_text", fake_get_text)

    token = asyncio.run(client.authenticate())

    assert token == "jwt-token"
    assert client.jwt == "jwt-token"


def test_authenticate_handles_auth_errors(monkeypatch):
    client = LoxoneClient(host="example.com", user="user", password="pass")

    async def fake_getkey2(self):
        return GetKey2Result(key="aa", salt="bb", hashAlg="SHA1")

    async def fake_get_text(self, path):
        return 401, "unauthorized"

    monkeypatch.setattr(LoxoneClient, "getkey2", fake_getkey2)
    monkeypatch.setattr(LoxoneClient, "_get_text", fake_get_text)

    with pytest.raises(LoxoneAuthError):
        asyncio.run(client.authenticate())


def test_jdev_get_prefixes_path(monkeypatch):
    client = LoxoneClient(host="example.com", user="user", password="pass")

    async def fake_get_json(self, path):
        return 200, {"LL": {"value": {"result": True}}}

    monkeypatch.setattr(LoxoneClient, "_get_json", fake_get_json)

    response = asyncio.run(client.jdev_get("sps/io/Control"))
    assert response == {"LL": {"value": {"result": True}}}
