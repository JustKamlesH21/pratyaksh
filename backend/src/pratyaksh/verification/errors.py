class VerificationError(Exception):
    pass


class CallNotFound(VerificationError):
    pass


class ConsentNotFound(VerificationError):
    pass


class UnknownCustomer(VerificationError):
    pass


class NotAllowed(VerificationError):
    """The action does not fit the Call's state or the Customer."""


class DeviceNotPaired(VerificationError):
    """The request did not come from the Customer's paired Registered Device."""
