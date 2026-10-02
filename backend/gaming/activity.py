"""
The one place that writes an ActivityLog row — see that model's own
docstring. Every caller (gaming.services, gaming.views, accounts.views)
imports log_activity rather than creating ActivityLog rows directly, so
there's a single, consistent shape for every entry regardless of which
action wrote it.
"""
from django.db import connection
from django_tenants.utils import get_public_schema_name

from .models import ActivityLog


def log_activity(actor, action, summary, *, player=None, game_day=None, transaction=None, details=None):
    # gaming is tenant-only (see ActivityLog's own docstring) — the public
    # schema has no gaming_activitylog table at all. A handful of callers
    # in accounts.views (login, PIN reset, ...) are reachable from a
    # public-schema request (the site-wide Django admin login), so this
    # guard has to live here, not at each call site.
    if connection.schema_name == get_public_schema_name():
        return
    ActivityLog.objects.create(
        actor=actor,
        actor_role=getattr(actor, 'role', ''),
        action=action,
        summary=summary,
        player=player,
        game_day=game_day,
        transaction=transaction,
        details=details or {},
    )
