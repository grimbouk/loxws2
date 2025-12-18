# Loxone Miniserver Home Assistant Integration

This repository provides:

- `loxone_api`: an asynchronous Python client for communicating with a Loxone Miniserver, handling authentication, token refresh, structure parsing, and websocket event streaming.
- `custom_components/loxone`: a Home Assistant custom component that exposes Miniserver controls as entities and uses the shared client library.

## Usage

1. Install the Python package in your Home Assistant environment:

```bash
pip install .
```

2. Copy the `custom_components/loxone` folder into your Home Assistant `custom_components` directory.
3. Restart Home Assistant and configure the integration via the UI, providing the host, credentials, and TLS options.

The integration currently creates entities for lights, sensors, binary sensors, covers, climate controllers, and scenes. Additional platforms can be added by extending the platform files and mapping further control types from the structure file.

Test