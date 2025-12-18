"""Command line shim for streaming events from a Loxone Miniserver."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import logging
import sys
import signal
import time
from typing import Iterable

from .client import LoxoneClient
from .models import LoxoneState

_LOGGER = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Connect to a Loxone Miniserver and stream events to stdout.",
    )
    parser.add_argument("host", help="Hostname or IP of the Miniserver")
    parser.add_argument("username", help="Username for authentication")
    parser.add_argument("password", nargs="?", help="Password for authentication (will prompt if omitted)")
    parser.add_argument("--port", type=int, help="Port of the Miniserver (defaults to 443)")
    parser.add_argument("--no-verify-ssl", action="store_true", help="Skip TLS certificate verification")
    parser.add_argument(
        "--list-controls",
        action="store_true",
        help="Print discovered controls when connecting",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging for troubleshooting",
    )
    return parser


def _format_control_listing(controls: Iterable) -> str:
    lines = ["Discovered controls:"]
    for control in sorted(controls, key=lambda c: c.name.lower()):
        label = control.name
        if control.room:
            label += f" ({control.room})"
        lines.append(f"- {label} [{control.uuid}] type={control.type}")
    return "\n".join(lines)


def _format_state(state: LoxoneState, client: LoxoneClient) -> str:
    control = client.get_control(state.control_uuid)
    label = control.name if control else state.control_uuid
    return f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {label}: {state.value}"


async def _run(args: argparse.Namespace) -> None:
    password = args.password or getpass.getpass("Password: ")
    print(password)
    client = LoxoneClient(
        args.host,
        args.username,
        password,
        port=args.port,
        use_tls=True,
        verify_ssl=not args.no_verify_ssl,
    )

    def _on_state(state: LoxoneState) -> None:
        print(_format_state(state, client))

    client.register_callback(_on_state)

    controls = await client.async_start()
    print("Connected to Loxone Miniserver")
    if args.list_controls:
        print(_format_control_listing(controls.values()))

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    try:
        await stop_event.wait()
    finally:
        await client.async_stop()


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    # Configure logging to print to stdout and respect --verbose
    level = logging.DEBUG if args.verbose else logging.INFO
    root = logging.getLogger()
    # Ensure there's a stream handler to stdout with a readable formatter
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    # Replace existing handlers so output is predictable in CLI
    root.handlers[:] = [handler]
    root.setLevel(level)

    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        _LOGGER.info("Shutting down...")


if __name__ == "__main__":
    main()
