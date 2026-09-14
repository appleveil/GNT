class AuthorizationError(Exception):
    """Raised when an actor/PIN isn't authorized to perform a gated action."""


class InvalidStateError(Exception):
    """Raised when an action is attempted against an object in the wrong state
    (e.g. recording a transaction against an already-closed game-day)."""


class TableFullError(InvalidStateError):
    """
    Raised by gaming.services.seat_player when a game-day already has
    MAX_ACTIVE_PLAYERS_PER_GAME_DAY active players and this player isn't
    already one of them. Still an InvalidStateError (maps to 400 via the
    global exception handler unchanged), but carries `.player` so the view
    can attach registered_not_seated/player_id to the response — the
    frontend needs to tell "seat capacity full" apart from any other 400
    without string-matching the message. See CONCEPT.md's "leave the table"
    note and PLAN.md's Phase A entry.
    """

    def __init__(self, message, player):
        super().__init__(message)
        self.player = player
