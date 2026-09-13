class AuthorizationError(Exception):
    """Raised when an actor/PIN isn't authorized to perform a gated action."""


class InvalidStateError(Exception):
    """Raised when an action is attempted against an object in the wrong state
    (e.g. recording a transaction against an already-closed game-day)."""
