import argparse
import asyncio
import logging
from argparse import Namespace
from pathlib import Path
import sys

# Ensure the project root is on the import path for tests without installation
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import loxone_api.cli as cli


def test_build_parser_includes_expected_arguments():
    parser = cli._build_parser()

    args = parser.parse_args([
        "example.com",
        "user",
        "secret",
        "--port",
        "8443",
        "--no-verify-ssl",
        "--permission",
        "4",
        "--uuid",
        "custom",
        "--info",
        "test",
        "--verbose",
    ])

    assert isinstance(args, argparse.Namespace)
    assert args.host == "example.com"
    assert args.port == 8443
    assert args.no_verify_ssl is True
    assert args.permission == 4
    assert args.uuid == "custom"
    assert args.info == "test"
    assert args.verbose is True


def test_get_password_prefers_provided_value(monkeypatch):
    # Provided value should be used as-is
    assert cli._get_password("provided") == "provided"

    # When missing, getpass.getpass should be invoked
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: "from-prompt")
    assert cli._get_password(None) == "from-prompt"


def test_configure_logging_sets_level():
    # Reset logging configuration so basicConfig applies
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(logging.NOTSET)

    cli._configure_logging(verbose=False)
    assert logging.getLogger().getEffectiveLevel() == logging.INFO

    # Ensure we can elevate to DEBUG
    cli._configure_logging(verbose=True)
    assert logging.getLogger().getEffectiveLevel() == logging.DEBUG


def test_run_loads_structure(capsys, monkeypatch):
    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def authenticate(self, **kwargs):
            return "jwt-token-value"

        async def load_structure(self):
            return {
                "controls": {"test-id": {"name": "Test Control", "type": "Switch"}},
                "rooms": {},
                "categories": {},
            }

    # Replace the real client with the fake
    monkeypatch.setattr(cli, "LoxoneClient", FakeClient)

    args = Namespace(
        host="example.com",
        port=443,
        user="user",
        password="pass",
        no_verify_ssl=False,
        permission=2,
        uuid="",
        info="loxone_api",
        verbose=False,
    )

    rc = asyncio.run(cli._run(args))
    assert rc == 0
