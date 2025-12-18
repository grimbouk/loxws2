"""Data models for the Loxone library."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional


@dataclass
class LoxoneControl:
    """Representation of a Loxone control entry."""

    uuid: str
    name: str
    type: str
    room: Optional[str] = None
    category: Optional[str] = None
    states: Dict[str, Any] = field(default_factory=dict)
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LoxoneState:
    """Representation of a state update from the Miniserver."""

    control_uuid: str
    state: str
    value: Any


CallbackType = Callable[[LoxoneState], None]
