"""Command line shim for testing Loxone Miniserver authentication and structure loading."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import logging
import sys
from typing import Optional

from .client import LoxoneClient, LoxoneAuthError, LoxoneRequestError

_LOGGER = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m loxone_api.cli",
        description="Test Loxone Miniserver authentication and load structure.",
    )

    p.add_argument("host", help="Miniserver host or IP (e.g. 192.168.1.110)")
    p.add_argument("user", help="Loxone username")
    p.add_argument(
        "password",
        nargs="?",
        default=None,
        help="Password (optional). If omitted, you will be prompted securely.",
    )

    p.add_argument(
        "--port",
        type=int,
        default=443,
        help="Miniserver HTTPS port (default: 443)",
    )
    p.add_argument(
        "--no-verify-ssl",
        action="store_true",
        help="Disable TLS certificate verification (useful for self-signed certs).",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )

    # JWT params
    p.add_argument(
        "--permission",
        type=int,
        default=2,
        help="JWT permission (commonly 2=Web, 4=App). Default: 2",
    )
    p.add_argument(
        "--uuid",
        default="",
        help="Client UUID to include in getjwt. Default: random generated",
    )
    p.add_argument(
        "--info",
        default="loxone_api",
        help="Client info string to include in getjwt. Default: loxone_api",
    )

    return p


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)


def _get_password(provided: Optional[str]) -> str:
    if provided is not None and provided != "":
        return provided
    return getpass.getpass("Password: ")


async def _run(args: argparse.Namespace) -> int:
    password = _get_password(args.password)
    verify_tls = not args.no_verify_ssl

    try:
        async with LoxoneClient(
            host=args.host,
            port=args.port,
            user=args.user,
            password=password,
            verify_tls=verify_tls,
        ) as client:
            _LOGGER.info("Authenticating...")
            token = await client.authenticate(
                permission=args.permission,
                uuid=args.uuid,
                info=args.info,
            )

            preview = token[:24] + "..." if len(token) > 24 else token
            _LOGGER.info("Authentication successful, JWT: %s", preview)

            _LOGGER.info("Loading structure...")
            structure = await client.load_structure()

            controls = structure.get("controls", {})
            _LOGGER.info("Loaded %d controls from LoxAPP3.json", len(controls))

            # Print sample of loaded controls
            print("\nSample controls:")
            for uuid, control in list(controls.items())[:5]:
                name = control.get("name", uuid)
                ctype = control.get("type", "")
                room = control.get("room")
                room_name = structure.get("rooms", {}).get(str(room), {}).get("name") if room else None
                location = f" ({room_name})" if room_name else ""
                print(f"  - {name}{location} [type={ctype}]")

            return 0

    except (LoxoneAuthError, LoxoneRequestError) as e:
        _LOGGER.error(str(e))
        return 2
    except KeyboardInterrupt:
        return 130


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    _configure_logging(args.verbose)

    # Run async entrypoint
    rc = asyncio.run(_run(args))
    raise SystemExit(rc)


if __name__ == "__main__":
    main()

# End of code