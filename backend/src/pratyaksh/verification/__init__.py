"""Verification: the deep module that runs a Call from greeting to close.

Interface (commands; each returns the Step the Voice Agent must do next):
    start_call(customer_id, room)          -> Step
    respond(call_id, response)             -> Step
    current_step(call_id)                  -> Step   (poll while App Approval is pending)
    app_approval(call_id, customer_id, device_token, ok) -> Step   (from the Bank App)
    review(call_id, approve, reviewer)     -> dict   (Agent Review, from the Console)
    dismiss_alerts(customer_id, device_token) -> int (Security Alerts, from the Bank App; lifts the voice pause)
    hang_up(call_id)                       -> None
Reads:
    call(call_id), calls(limit), inbox(customer_id, device_token), customers()
    audit_check(call_id) -> {intact, events, broken_at, head}   (recomputes the Audit Trail's hash chain)
    receipt(call_id) -> {receipt, claims}   (signed Verification Receipt of a closed Call)
    verify_receipt(receipt) -> {valid, reason, claims}, receipt_key() -> public JWK
    stats() -> {calls, by_outcome, blocked, avg_added_seconds}   (live numbers for the Console)
    pairing(customer_id) -> device token (shown only on the operator's machine)

Errors: CallNotFound, UnknownCustomer, NotAllowed, DeviceNotPaired.
Hidden inside: the Call state machine, understanding any utterance (Requests, Questions answered
to fit the moment, small talk, "repeat", "hold on", "a person please"), Challenge planning and phrases,
Possession Codes and the Device Inbox, Policy decisions, the Audit Trail and live events.
"""

from .consent import ConsentedClips, VoiceConsents
from .errors import CallNotFound, ConsentNotFound, DeviceNotPaired, NotAllowed, UnknownCustomer
from .events import EventHub
from .interpreter import Faq, Interpreter, OllamaChat
from .receipts import ReceiptSigner
from .store import Database
from .verifier import Verifier

__all__ = [
    "CallNotFound",
    "ConsentNotFound",
    "ConsentedClips",
    "DeviceNotPaired",
    "Database",
    "EventHub",
    "Faq",
    "Interpreter",
    "NotAllowed",
    "OllamaChat",
    "ReceiptSigner",
    "UnknownCustomer",
    "Verifier",
    "VoiceConsents",
]
