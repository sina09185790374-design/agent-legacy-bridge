"""agent-legacy-bridge: teach an agent to talk to a dumb legacy device."""

from .protocol import load_spec
from .reader import Client, DemoSession

__all__ = ["Client", "DemoSession", "load_spec"]
__version__ = "1.0.0"
