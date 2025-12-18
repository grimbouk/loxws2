# Loxone Miniserver Home Assistant Integration

This repository provides:

- `loxone_api`: an asynchronous Python client for communicating with a Loxone Miniserver, handling authentication, token refresh, structure parsing, and websocket event streaming.
- `custom_components/loxone`: a Home Assistant custom component that exposes Miniserver controls as entities and uses the shared client library.
- `loxone-api-cli`: a lightweight command-line shim for exercising the client outside Home Assistant and streaming events to stdout for debugging.

## Home Assistant usage

1. Install the Python package in your Home Assistant environment:

```bash
pip install .
```

2. Copy the `custom_components/loxone` folder into your Home Assistant `custom_components` directory.
3. Restart Home Assistant and configure the integration via the UI, providing the host, credentials, and TLS options.

The integration currently creates entities for lights, sensors, binary sensors, covers, climate controllers, and scenes. Additional platforms can be added by extending the platform files and mapping further control types from the structure file.

## Command-line shim for testing

After installing the package locally you can use the shim to connect directly to a Miniserver and view live events without Home Assistant:

```bash
loxone-api-cli <host> <username> [password] --list-controls
```

- If the password is omitted you will be prompted securely.
- Use `--no-tls` to connect over HTTP/websocket and `--no-verify-ssl` to skip TLS certificate verification during testing.
- Add `--list-controls` to print the discovered controls before streaming events.
- Press `Ctrl+C` to exit; the client will close the websocket and HTTP session.
