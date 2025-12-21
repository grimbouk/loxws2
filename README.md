# Loxone Miniserver Home Assistant Integration

This repository provides:

- `loxone_api`: an asynchronous Python client library for communicating with a Loxone Miniserver, handling authentication via getkey2/getjwt flow, loading the LoxAPP3.json structure file, and providing methods to fetch/send control states.
- `custom_components/loxone`: a Home Assistant custom component that uses the shared client library to expose Miniserver controls as Home Assistant entities (lights, sensors, binary sensors, covers, climate controllers, scenes).
- `loxone-api-cli`: a lightweight command-line utility for testing the client library outside Home Assistant.

## Installation and setup

### As a Home Assistant integration

1. Copy the `custom_components/loxone` folder into your Home Assistant `custom_components` directory.
2. Restart Home Assistant and configure the integration via the UI, providing the host, credentials, and TLS options.

The integration creates entities for lights, sensors, binary sensors, covers, climate controllers, and scenes based on control types from the structure file. Additional platforms can be added by extending the platform files.

### As a standalone library

Install the `loxone_api` package:

```bash
pip install .
```

Then use it in your Python code:

```python
from loxone_api import LoxoneClient

async with LoxoneClient(host="192.168.1.110", user="admin", password="pass") as client:
    # Authenticate
    token = await client.authenticate()
    
    # Load structure
    structure = await client.load_structure()
    controls = structure["controls"]
    
    # Fetch/send control state
    state = await client.jdev_get("sps/io/<uuid>")
```

## Command-line testing

After installing locally, you can test the client with:

```bash
python3 -m loxone_api.cli <host> <username> [password] --no-verify-ssl --verbose
```

- If the password is omitted you will be prompted securely.
- Use `--no-verify-ssl` to skip TLS certificate verification during testing.
- Use `--verbose` to enable debug logging to see the full authentication flow.
