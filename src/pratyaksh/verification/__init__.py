"""Verification: the deep module that runs a Call from greeting to close.

Interface (commands; each returns the Step the Voice Agent must do next):
    start_call(customer_id, room)          -> Step
    respond(call_id, response)             -> Step
    current_step(call_id)                  -> Step   (poll while App Approval is pending)
    app_approval(call_id, customer_id, device_token, ok) -> Step   (from the Bank App)
    review(call_id, approve, reviewer)     -> dict   (Agent Review, from the Console)
    hang_up(call_id)                       -> None
Reads:
    call(call_id), calls(limit), inbox(customer_id, device_token), customers()
    pairing(customer_id) -> device token (shown only on the operator's machine)

Errors: CallNotFound, UnknownCustomer, NotAllowed, DeviceNotPaired.
Hidden inside: the Call state machine, Request understanding, Challenge planning and phrases,
Possession Codes and the Device Inbox, Policy decisions, the Audit Trail and live events.
"""

from .errors import CallNotFound, DeviceNotPaired, NotAllowed, UnknownCustomer
from .events import EventHub
from .requests import OllamaChat, RequestClassifier
from .store import Database
from .verifier import Verifier

__all__ = [
    "CallNotFound",
    "DeviceNotPaired",
    "Database",
    "EventHub",
    "NotAllowed",
    "OllamaChat",
    "RequestClassifier",
    "UnknownCustomer",
    "Verifier",
]
