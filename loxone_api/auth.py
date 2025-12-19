from __future__ import annotations

import hashlib
import hmac
import logging
import re
import uuid as uuidlib
from dataclasses import dataclass
from typing import Any, Dict, Tuple
from urllib.parse import quote

log = logging.getLogger(__name__)
_HEX_RE = re.compile(r"^[0-9a-fA-F]+$")


def _looks_like_hex(s: str) -> bool:
    return bool(s) and (len(s) % 2 == 0) and bool(_HEX_RE.match(s))


def _hash_hex(hash_alg: str, s: str) -> str:
    b = s.encode("utf-8")
    alg = hash_alg.upper()
    if alg == "SHA256":
        return hashlib.sha256(b).hexdigest()
    if alg == "SHA1":
        return hashlib.sha1(b).hexdigest()
    raise ValueError(f"Unsupported hashAlg: {hash_alg}")


def _hmac_hex(hash_alg: str, key_bytes: bytes, msg: str) -> str:
    m = msg.encode("utf-8")
    alg = hash_alg.upper()
    if alg == "SHA256":
        return hmac.new(key_bytes, m, hashlib.sha256).hexdigest()
    if alg == "SHA1":
        return hmac.new(key_bytes, m, hashlib.sha1).hexdigest()
    raise ValueError(f"Unsupported hashAlg: {hash_alg}")


def decode_getkey2_key_to_hmac_key_bytes(key_hex: str) -> Tuple[bytes, str]:
    """
    Loxone getkey2 returns 'key' as a hex string.
    For many miniservers, that hex decodes to ASCII characters (also hex-like),
    and Loxone expects you to use the ASCII string as the HMAC key.

    Returns: (key_bytes_for_hmac, key_ascii_for_debug)
    """
    k = (key_hex or "").strip()
    if not _looks_like_hex(k):
        # Unexpected, but handle gracefully
        return k.encode("utf-8"), k

    # First decode the response hex to bytes
    b1 = bytes.fromhex(k)

    # Try interpret as ASCII (most common)
    try:
        key_ascii = b1.decode("ascii").strip()
        # Use the ASCII characters as key material
        return key_ascii.encode("ascii"), key_ascii
    except UnicodeDecodeError:
        # Fallback to raw bytes
        return b1, b1.hex()


@dataclass(frozen=True)
class JwtRequestParams:
    permission: int = 4  # 2=Web, 4=App (depending on your use-case)
    uuid: str = ""
    info: str = "loxone_api"

    def with_defaults(self) -> "JwtRequestParams":
        uid = self.uuid or str(uuidlib.uuid4())
        return JwtRequestParams(permission=self.permission, uuid=uid, info=self.info)


def build_getjwt_path_from_getkey2(
    user: str,
    password: str,
    getkey2_value: Dict[str, Any],
    params: JwtRequestParams,
) -> Tuple[str, Dict[str, Any]]:
    """
    getkey2_value is the dict under LL.value, e.g.
    {
      "key": "...",
      "salt": "...",
      "hashAlg": "SHA256"
    }
    """
    user_clean = user.strip()
    password_clean = password.rstrip("\r\n")

    key_hex = (getkey2_value.get("key") or "").strip()
    salt = (getkey2_value.get("salt") or "").strip()
    hash_alg = (getkey2_value.get("hashAlg") or "SHA1").strip()

    if not key_hex or not salt:
        raise ValueError(f"Invalid getkey2 value (missing key/salt): {getkey2_value}")

    # pwHash = UPPER( HASH("{password}:{userSalt}") with hashAlg )
    pw_hash = _hash_hex(hash_alg, f"{password_clean}:{salt}").upper()

    # hash = HMAC(hashAlg, key, "{user}:{pwHash}")
    hmac_key_bytes, key_ascii_dbg = decode_getkey2_key_to_hmac_key_bytes(key_hex)
    msg = f"{user_clean}:{pw_hash}"
    auth_hmac = _hmac_hex(hash_alg, hmac_key_bytes, msg)

    p = params.with_defaults()
    info_enc = quote(p.info, safe="")

    path = f"/jdev/sys/getjwt/{auth_hmac}/{user_clean}/{p.permission}/{p.uuid}/{info_enc}"

    debug = {
        "user": user_clean,
        "permission": p.permission,
        "uuid": p.uuid,
        "info": p.info,
        "info_enc": info_enc,
        "hash_alg": hash_alg,
        "salt": salt,
        "pw_hash": pw_hash,
        "pw_hash_len": len(pw_hash),
        "key_hex": key_hex,
        "key_ascii_dbg": key_ascii_dbg[:24] + ("..." if len(key_ascii_dbg) > 24 else ""),
        "hmac_key_len": len(hmac_key_bytes),
        "auth_hmac": auth_hmac,
        "auth_hmac_len": len(auth_hmac),
        "msg": msg,
        "path": path,
    }
    return path, debug