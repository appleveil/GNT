class AuthorizationError(Exception):
    """Raised when an actor/PIN isn't authorized to perform a gated action."""
