"""Async client for the Loxone Miniserver websocket API."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin
import contextlib

import aiohttp

from .const import (
    DEFAULT_PORT,
    DEFAULT_STRUCT_PATH,
    DEFAULT_TLS_PORT,
    DEFAULT_WS_PATH,
    PING_INTERVAL,
    RECONNECT_DELAY,
    TOKEN_REFRESH_THRESHOLD,
)
from .models import CallbackType, LoxoneControl, LoxoneState
from .auth import build_getjwt_path, JwtRequestParams

_LOGGER = logging.getLogger(__name__)


@dataclass
class TokenInfo:
    """Authentication token and expiry information."""

    token: str
    valid_until: float


class LoxoneApiError(Exception):
    """Base error for the Loxone API."""


class LoxoneClient:
    """Handle connectivity and subscription to a Loxone Miniserver."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        *,
        port: int | None = None,
        use_tls: bool = True,
        verify_ssl: bool = True,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        self.host = host
        self.username = username
        self.password = password
        # Enforce TLS/WSS-only operation for security
        if not use_tls:
            raise ValueError("Only TLS/WSS (HTTPS/WSS) is supported")
        self.port = port if port is not None else DEFAULT_TLS_PORT
        self.use_tls = True
        self.verify_ssl = verify_ssl
        self._external_session = session
        self._session: aiohttp.ClientSession | None = None
        self._token: TokenInfo | None = None
        self._controls: Dict[str, LoxoneControl] = {}
        self._state_callbacks: List[CallbackType] = []
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._listen_task: asyncio.Task | None = None
        self._closing = False

    @property
    def base_url(self) -> str:
        scheme = "https" if self.use_tls else "http"
        return f"{scheme}://{self.host}:{self.port}"

    async def async_start(self) -> Dict[str, LoxoneControl]:
        """Start the connection to the miniserver and return controls."""

        await self._ensure_session()
        await self._ensure_token()
        await self._load_structure()
        await self._ensure_websocket()
        return self._controls

    async def async_stop(self) -> None:
        """Close the websocket and session."""

        self._closing = True
        if self._listen_task:
            self._listen_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._listen_task
        if self._ws and not self._ws.closed:
            await self._ws.close()
        if self._session and not self._external_session:
            await self._session.close()

    async def _ensure_session(self) -> None:
        if self._session is None:
            self._session = aiohttp.ClientSession()

    async def _ensure_token(self) -> None:
        if self._token and self._token.valid_until - TOKEN_REFRESH_THRESHOLD > time.time():
            return
        await self._authenticate()

    async def _authenticate(self) -> None:
        """Authenticate with the miniserver to obtain a token.

        The Miniserver exposes a token endpoint that accepts basic authentication and
        returns a JSON payload containing the JWT and expiry timestamp. The endpoint
        is documented in the vendor guides bundled with this repository.
        """

        _LOGGER.debug("Authenticating using encrypted getjwt flow")

        assert self._session
        # Use getkey2 and HMAC-based getjwt path for encrypted-command compatible Miniserver
        key = await self._fetch_key()
        print("key for auth:", key)
        
        path, dbg = build_getjwt_path(self.username, self.password, key, JwtRequestParams())
        _LOGGER.debug("JWT build debug: %s", {k: dbg[k] for k in ("user", "permission", "uuid", "info_enc", "pw_hash", "key_bytes_len", "key_bytes_hex", "hmac_hex", "path")})
        url = urljoin(self.base_url, path)
        _LOGGER.debug("Auth URL: %s", url)
        async with self._session.get(url, ssl=self.verify_ssl) as resp:
            body = await resp.text()

        if resp.status != 200:
            _LOGGER.error("Authentication failed with status %s: %s", resp.status, body)
            raise LoxoneApiError(f"Failed to authenticate: {resp.status}")

        print("Authentication successful")

        try:
            payload = json.loads(body)
        except json.JSONDecodeError as err:
            _LOGGER.error("Authentication response was not valid JSON: %s", body)
            raise LoxoneApiError("Invalid authentication response") from err

        # getjwt typically returns LL.value with token and optional controlInfo.validUntil
        token_value = payload.get("LL", {}).get("value") or payload.get("token")
        valid_until = (
            payload.get("LL", {}).get("controlInfo", {}).get("validUntil")
            or payload.get("validUntil", 0)
        )
        if not token_value:
            _LOGGER.error("Authentication response missing token; payload: %s", payload)
            raise LoxoneApiError("No token returned from Miniserver")
        if not valid_until:
            # default validity to 30 minutes if the payload does not advertise it
            valid_until = time.time() + 1800
        self._token = TokenInfo(token=token_value, valid_until=float(valid_until))
        _LOGGER.debug("Authenticated with token expiring at %s", self._token.valid_until)

    async def _fetch_key(self) -> str:
        """Fetch the temporary key required to hash credentials."""

        print("Fetching key from miniserver...")

        assert self._session
        # Prefer the newer getkey2 endpoint which returns keys suitable for encrypted-command flows
        url = urljoin(self.base_url, f"/jdev/sys/getkey2/{self.username}")
        async with self._session.get(url, ssl=self.verify_ssl) as resp:
            body = await resp.text()

        if resp.status != 200:
            _LOGGER.error("Key retrieval failed with status %s: %s", resp.status, body)
            raise LoxoneApiError(f"Failed to fetch key: {resp.status}")

        print("Key fetched successfully")

        try:
            payload = json.loads(body)
            print("Payload:", payload)
        except json.JSONDecodeError as err:
            _LOGGER.error("Key response was not valid JSON: %s", body)
            raise LoxoneApiError("Invalid key response") from err

        val = payload.get("LL", {}).get("value")
        # Newer Miniservers return an object with the actual key under 'key'
        if isinstance(val, dict):
            key = val.get("key") or val.get("value")
            _LOGGER.debug("Parsed getkey2 value object, extracted key present: %s", bool(key))
        else:
            key = val

        if not key:
            _LOGGER.error("Key response missing value; payload: %s", payload)
            raise LoxoneApiError("No key returned from Miniserver")

        _LOGGER.debug("Key retrieved (length=%s)", len(str(key)))
        return str(key)

    async def _load_structure(self) -> None:
        """Load the structure file describing controls."""

        assert self._session
        await self._ensure_token()
        headers = {"Authorization": f"Bearer {self._token.token}"} if self._token else None
        url = urljoin(self.base_url, DEFAULT_STRUCT_PATH)
        async with self._session.get(url, headers=headers, auth=None, ssl=self.verify_ssl) as resp:
            if resp.status != 200:
                raise LoxoneApiError(f"Failed to download structure file: {resp.status}")
            structure = await resp.json(content_type=None)

        controls: Dict[str, LoxoneControl] = {}
        for uuid, control in structure.get("controls", {}).items():
            controls[uuid] = LoxoneControl(
                uuid=uuid,
                name=control.get("name", uuid),
                type=control.get("type", ""),
                room=structure.get("rooms", {}).get(str(control.get("room")), {}).get("name"),
                category=structure.get("cats", {}).get(str(control.get("cat")), {}).get("name"),
                states=control.get("states", {}),
                details=control,
            )
        self._controls = controls
        _LOGGER.debug("Loaded %s controls from structure", len(self._controls))

    async def _ensure_websocket(self) -> None:
        if self._ws and not self._ws.closed:
            return
        assert self._session
        await self._ensure_token()
        url = f"{'wss' if self.use_tls else 'ws'}://{self.host}:{self.port}{DEFAULT_WS_PATH}?auth={self._token.token}"
        self._ws = await self._session.ws_connect(url, heartbeat=PING_INTERVAL, ssl=self.verify_ssl)
        self._listen_task = asyncio.create_task(self._listen())

    def register_callback(self, callback: CallbackType) -> None:
        """Register a callback for state updates."""

        self._state_callbacks.append(callback)

    async def send_control_command(self, uuid: str, command: str, value: Any | None = None) -> None:
        """Send a control command to the miniserver."""

        await self._ensure_websocket()
        payload = {"control": uuid, "command": command, "value": value}
        assert self._ws
        await self._ws.send_json(payload)

    async def _listen(self) -> None:
        """Listen for websocket messages and dispatch callbacks."""

        assert self._ws
        while not self._ws.closed and not self._closing:
            try:
                msg = await self._ws.receive()
            except aiohttp.ClientError as err:
                _LOGGER.warning("Websocket error: %s", err)
                break

            if msg.type == aiohttp.WSMsgType.TEXT:
                await self._handle_message(msg.data)
            elif msg.type == aiohttp.WSMsgType.BINARY:
                await self._handle_binary(msg.data)
            elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                _LOGGER.warning("Websocket closed: %s", msg.type)
                break

        if not self._closing:
            await asyncio.sleep(RECONNECT_DELAY)
            await self._ensure_websocket()

    async def _handle_message(self, data: str) -> None:
        """Parse incoming JSON messages."""

        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            _LOGGER.debug("Received non JSON message: %s", data)
            return

        # State updates arrive as key/value pairs where key is the uuid
        for key, value in payload.items():
            if key in self._controls:
                state = LoxoneState(control_uuid=key, state="value", value=value)
                for cb in self._state_callbacks:
                    cb(state)

    async def _handle_binary(self, data: bytes) -> None:
        """Handle binary messages.

        Binary payloads are small frames carrying state updates. They follow the
        documented event format and include the control UUID and the updated
        value. For simplicity we treat the payload as a UTF-8 string and try to
        decode it.
        """

        try:
            decoded = data.decode("utf-8")
        except UnicodeDecodeError:
            _LOGGER.debug("Dropped non UTF-8 binary payload")
            return
        await self._handle_message(decoded)

    def get_control(self, uuid: str) -> Optional[LoxoneControl]:
        """Return a control from the structure."""

        return self._controls.get(uuid)

    @property
    def controls(self) -> Dict[str, LoxoneControl]:
        return self._controls
