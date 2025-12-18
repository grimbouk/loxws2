import re
import sys
from pathlib import Path

# Ensure the project root is on the import path for tests without installation
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loxone_api.cli import _format_control_listing, _format_state
from loxone_api.client import LoxoneClient
from loxone_api.models import LoxoneControl, LoxoneState


def test_format_control_listing_orders_and_labels_controls():
    controls = [
        LoxoneControl(uuid="2", name="Kitchen Light", type="light", room="Kitchen"),
        LoxoneControl(uuid="1", name="bath fan", type="fan", room="Bathroom"),
    ]

    listing = _format_control_listing(controls)

    # Ordered alphabetically (case-insensitive) and includes uuid/type/room
    assert "Discovered controls:" in listing
    assert listing.splitlines()[1] == "- bath fan (Bathroom) [1] type=fan"
    assert listing.splitlines()[2] == "- Kitchen Light (Kitchen) [2] type=light"


def test_format_state_prefers_control_name():
    client = LoxoneClient("host", "user", "password")
    client._controls = {
        "abc": LoxoneControl(uuid="abc", name="Window Sensor", type="sensor"),
    }

    state = LoxoneState(control_uuid="abc", state="value", value=0)

    formatted = _format_state(state, client)

    # Timestamp prefix followed by label and value
    assert re.match(r"^\[\d{4}-\d{2}-\d{2} ", formatted)
    assert "Window Sensor: 0" in formatted
