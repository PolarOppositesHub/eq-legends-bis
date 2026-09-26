"""Combat-log parser for EverQuest Legends.

Reads ``Logs/eqlog_<character>_<server>.txt`` only. No process memory,
packet capture, or input automation.
"""

from .classify import classify_message
from .models import ParsedEvent

__all__ = ["ParsedEvent", "classify_message"]
