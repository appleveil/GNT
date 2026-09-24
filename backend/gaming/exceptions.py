class AuthorizationError(Exception):
    """Raised when an actor/PIN isn't authorized to perform a gated action."""


class MinimumPlayerTimeNotMetError(AuthorizationError):
    """
    Raised by gaming.services.record_transaction's minimum-player-time gate
    (added 2026-09-27, ClubSettings.observe_min_player_time) — a subclass
    of AuthorizationError, not a new status code (still maps to 403 via the
    global exception handler), but distinguishable so the response can
    carry requires_floor_manager_pin=True. The frontend needs to tell "this
    specific action needs a PIN override" apart from any other 403 without
    string-matching the message (same reasoning as TableFullError's own
    extra response fields) — see TransactionEntryModal.vue's onSubmit,
    which escalates from its plain-confirm attempt straight to the real
    Floor-Manager PIN sheet on this signal, instead of just showing the
    error with no way to actually provide one.
    """


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
