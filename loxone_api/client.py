"""
loxone_api/client.py

Async client for a Loxone Miniserver focusing on:
- getkey2/<user>
- getjwt/{hash}/{user}/{permission}/{uuid}/{info}

Notes:
- This implements the *HTTP JSON* flow using /jdev/ endpoints.
- Some Miniservers require the *encrypted websocket* flow for getjwt; if yours returns 400,
  you will need to implement keyexchange + encrypted commands via websocket (/ws/rfc6455).
"""

from __future__ import annotations

import asyncio
import json
import logging
import ssl
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urljoin

import aiohttp

from .auth import JwtRequestParams, build_getjwt_path_from_getkey2

log = logging.getLogger(__name__)


class LoxoneAuthError(RuntimeError):
    pass


class LoxoneRequestError(RuntimeError):
    pass


@dataclass(frozen=True)
class GetKey2Result:
    key: str
    salt: str
    hashAlg: str


class LoxoneClient:
    """
    Minimal async client for Loxone Miniserver authentication and basic requests.
    """

    def __init__(
        self,
        *,
        host: str,
        user: str,
        password: str,
        port: int = 443,
        verify_tls: bool = True,
        timeout_s: float = 120.0,
        session: Optional[aiohttp.ClientSession] = None,
    ):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.verify_tls = verify_tls
        self.timeout_s = timeout_s

        self.base_url = f"https://{self.host}:{self.port}/"
        self._session_external = session is not None
        self._session: Optional[aiohttp.ClientSession] = session

        self._jwt: Optional[str] = None

    async def __aenter__(self) -> "LoxoneClient":
        await self._ensure_session()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def close(self) -> None:
        if self._session and not self._session_external:
            await self._session.close()
        self._session = None

    async def _ensure_session(self) -> None:
        if self._session and not self._session.closed:
            return

        # Close any existing dead session
        if self._session:
            try:
                await self._session.close()
            except Exception:
                pass
            self._session = None

        # Use separate timeouts: sock_read for waiting on data, total for entire request
        timeout = aiohttp.ClientTimeout(
            sock_read=self.timeout_s,
            total=None  # No total timeout - let server control connection lifetime
        )

        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        if self.verify_tls:
            await asyncio.to_thread(
                ssl_context.load_default_certs, ssl.Purpose.SERVER_AUTH
            )
        else:
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

        connector = aiohttp.TCPConnector(ssl=ssl_context)
        self._session = aiohttp.ClientSession(timeout=timeout, connector=connector)

    def _full_url(self, path: str) -> str:
        return urljoin(self.base_url, path.lstrip("/"))

    async def _get_text(self, path: str) -> Tuple[int, str]:
        await self._ensure_session()
        assert self._session is not None

        url = self._full_url(path)
        log.debug("GET %s", url)

        headers = {}
        if self._jwt:
            headers["Authorization"] = f"Bearer {self._jwt}"

        async with self._session.get(url, headers=headers if headers else None) as resp:
            text = await resp.text()
            return resp.status, text

    @staticmethod
    def _parse_json_text(text: str) -> Dict[str, Any]:
        try:
            return json.loads(text)
        except Exception:
            sanitized = text.lstrip("\ufeff").strip("\x00")
            try:
                return json.loads(sanitized)
            except Exception:
                start = sanitized.find("{")
                end = sanitized.rfind("}")
                if start != -1 and end != -1 and end > start:
                    return json.loads(sanitized[start : end + 1])
                raise

    async def _get_json(self, path: str) -> Tuple[int, Dict[str, Any]]:
        status, text = await self._get_text(path)
        try:
            data = self._parse_json_text(text)
        except Exception:
            # Not JSON (often HTML errors)
            raise LoxoneRequestError(f"Non-JSON response (status {status}): {text}")

        return status, data

    @staticmethod
    def _extract_ll_value(payload: Dict[str, Any]) -> Any:
        """
        Loxone typically responds with: {"LL": {"control": "...", "code": "200", "value": ...}}
        """
        ll = payload.get("LL") or {}
        return ll.get("value")

    @staticmethod
    def _extract_ll_code(payload: Dict[str, Any]) -> Optional[str]:
        ll = payload.get("LL") or {}
        # some firmwares use 'Code', some use 'code'
        return ll.get("Code") or ll.get("code")

    async def getkey2(self) -> GetKey2Result:
        """
        Calls /jdev/sys/getkey2/<user> and returns key/salt/hashAlg.
        """
        path = f"/jdev/sys/getkey2/{self.user}"
        status, payload = await self._get_json(path)

        if status != 200:
            raise LoxoneRequestError(f"getkey2 failed with HTTP {status}: {payload}")

        code = self._extract_ll_code(payload)
        value = self._extract_ll_value(payload)

        log.debug("getkey2 payload: %s", payload)

        if code not in ("200", 200, None):
            raise LoxoneRequestError(f"getkey2 returned code={code}: {payload}")

        if not isinstance(value, dict):
            raise LoxoneRequestError(f"getkey2 unexpected value type: {type(value)} {value}")

        key = (value.get("key") or "").strip()
        salt = (value.get("salt") or "").strip()
        hash_alg = (value.get("hashAlg") or "SHA1").strip()

        if not key or not salt:
            raise LoxoneRequestError(f"getkey2 missing key/salt: {value}")

        return GetKey2Result(key=key, salt=salt, hashAlg=hash_alg)

    async def authenticate(
        self,
        *,
        permission: int = 2,
        uuid: str = "",
        info: str = "loxone_api",
    ) -> str:
        """
        Authenticates via:
          1) getkey2/<user>
          2) getjwt/{hash}/{user}/{permission}/{uuid}/{info}

        Returns JWT token string.
        """
        log.debug("Authenticating using getkey2/getjwt flow")

        try:
            key2 = await self.getkey2()
        except Exception:
            await self.close()
            raise

        # Build path using correct salt + hashAlg + key decoding
        key_payload = {"key": key2.key, "salt": key2.salt, "hashAlg": key2.hashAlg}
        params = JwtRequestParams(permission=permission, uuid=uuid, info=info)
        jwt_path, dbg = build_getjwt_path_from_getkey2(
            user=self.user,
            password=self.password,
            getkey2_value=key_payload,
            params=params,
        )

        # Debug without leaking password
        log.debug("JWT build debug: %s", dbg)
        log.debug("Auth URL: %s", self._full_url(jwt_path))

        status, text = await self._get_text(jwt_path)

        if status == 401:
            await self.close()
            raise LoxoneAuthError(f"Authentication failed with status 401: {text}")
        if status == 400:
            # Common when Miniserver expects encrypted getjwt; keep message actionable.
            await self.close()
            raise LoxoneAuthError(
                "Authentication failed with status 400 (Bad Request). "
                "Your Miniserver likely requires encrypted JWT requests via websocket keyexchange "
                "(encrypted command flow). Raw response: "
                + text
            )
        if status != 200:
            await self.close()
            raise LoxoneAuthError(f"Authentication failed with status {status}: {text}")

        try:
            payload = json.loads(text)
        except Exception:
            raise LoxoneAuthError(f"Authentication response was not JSON: {text}")

        ll_value = self._extract_ll_value(payload)

        # Some Miniserver firmwares return an object under LL.value with token and metadata:
        #   LL.value == { 'token': '...', 'validUntil': ..., 'tokenRights': ..., ... }
        if isinstance(ll_value, dict):
            token = ll_value.get("token") or ll_value.get("Token")
            if token is None:
                token = ll_value.get("value") or ll_value.get("Value")
            if isinstance(token, dict):
                token = (
                    token.get("token")
                    or token.get("Token")
                    or token.get("value")
                    or token.get("Value")
                )
        else:
            token = ll_value

        if not token or not isinstance(token, str):
            raise LoxoneAuthError(f"getjwt returned no token: {payload}")

        self._jwt = token
        return token

    @property
    def jwt(self) -> Optional[str]:
        return self._jwt

    async def jdev_get(self, control_path: str) -> Dict[str, Any]:
        """
        Convenience: call an arbitrary /jdev/... endpoint and return parsed JSON.
        Example:
          await client.jdev_get("sps/io/SomeControl")
        """
        if not control_path.startswith("/"):
            control_path = "/" + control_path
        if not control_path.startswith("/jdev/"):
            control_path = "/jdev/" + control_path.lstrip("/")

        status, payload = await self._get_json(control_path)
        if status != 200:
            raise LoxoneRequestError(f"Request failed HTTP {status}: {payload}")
        return payload

    async def load_structure(self) -> Dict[str, Any]:
        """Load the LoxAPP3.json structure file. Requires prior authentication."""
        if not self._jwt:
            raise LoxoneAuthError("Not authenticated. Call authenticate() first.")

        log.debug("Loading structure with JWT: %s...", self._jwt[:24])

        try:
            status, payload = await self._get_json("/data/LoxAPP3.json")
            if status != 200:
                raise LoxoneRequestError(f"Failed to load structure (HTTP {status})")

            # Try to extract structure from LL.value first, then fall back to top-level payload
            structure = self._extract_ll_value(payload)
            if structure is None:
                structure = payload

            if not isinstance(structure, dict):
                raise LoxoneRequestError(f"Unexpected structure type: {type(structure)}")

            return structure
        except Exception as err:
            log.error("Error loading structure: %s", err)
            raise


# Simple manual test helper:
async def _demo():
    import getpass

    host = "192.168.1.110"
    user = "loxws2"
    password = getpass.getpass("Password: ")

    logging.basicConfig(level=logging.DEBUG)

    async with LoxoneClient(host=host, user=user, password=password, verify_tls=False) as c:
        token = await c.authenticate(permission=2, info="loxone_api_demo")
        print("JWT:", token[:20] + "...")


if __name__ == "__main__":
    asyncio.run(_demo())
