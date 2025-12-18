from __future__ import annotations

import hashlib
import hmac
import logging
import re
import uuid as uuidlib
from dataclasses import dataclass
from urllib.parse import quote

log = logging.getLogger(__name__)

_HEX_RE = re.compile(r"^[0-9a-fA-F]+$")


def sha1_hex(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def _looks_like_hex(s: str) -> bool:
    return bool(s) and (len(s) % 2 == 0) and bool(_HEX_RE.match(s))


def decode_key_to_bytes(key_str: str) -> bytes:
    """
    Loxone 'getkey2' sometimes comes back as:
      - hex bytes (e.g. 'A1B2...')
      - hex of ASCII that itself is hex (double-encoded)
    This function tries to decode both safely.
    """
    k = key_str.strip()

    # Case 1: not hex at all -> treat as UTF-8 bytes
    if not _looks_like_hex(k):
        return k.encode("utf-8")

    b1 = bytes.fromhex(k)

    # If b1 is ASCII text and that ASCII text is also hex, decode again.
    try:
        as_text = b1.decode("ascii").strip()
        if _looks_like_hex(as_text):
            return bytes.fromhex(as_text)
    except UnicodeDecodeError:
        pass

    return b1


@dataclass(frozen=True)
class JwtRequestParams:
    permission: int = 2  # 2=Web is typical; some setups use 4=App
    uuid: str = ""
    info: str = "loxone_api"

    def with_defaults(self) -> "JwtRequestParams":
        uid = self.uuid or str(uuidlib.uuid4())
        return JwtRequestParams(permission=self.permission, uuid=uid, info=self.info)


def build_getjwt_path(user: str, password: str, key_str: str, params: JwtRequestParams) -> tuple[str, dict]:
    """
    Returns (path, debug_dict)
    """
    user_clean = user.strip()
    # Avoid accidental whitespace/newlines from env vars etc.
    password_clean = password.rstrip("\r\n")

    key_bytes = decode_key_to_bytes(key_str)
    pw_hash = sha1_hex(password_clean.encode("utf-8"))

    msg = f"{user_clean}:{pw_hash}".encode("utf-8")
    hmac_hex = hmac.new(key_bytes, msg, hashlib.sha1).hexdigest()

    p = params.with_defaults()

    # info must be URL-encoded
    info_enc = quote(p.info, safe="")

    path = f"/jdev/sys/getjwt/{hmac_hex}/{user_clean}/{p.permission}/{p.uuid}/{info_enc}"

    debug = {
        "user": user_clean,
        "permission": p.permission,
        "uuid": p.uuid,
        "info": p.info,
        "info_enc": info_enc,
        "pw_hash": pw_hash,
        "msg_utf8_hex": msg.hex(),
        "key_str": key_str,
        "key_bytes_hex": key_bytes.hex(),
        "key_bytes_len": len(key_bytes),
        "hmac_hex": hmac_hex,
        "path": path,
    }
    return path, debug