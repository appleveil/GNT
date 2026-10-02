"""
Backfill for the 2026-09-28 Profit-Split stake redesign (commit be30320).

Before it, a stake-covered CHIPS_OUT was recorded at the player's discounted
share and its PROFIT_SPLIT_STAKE row was balance-neutral and unlinked. After
it, CHIPS_OUT records the full physical amount and PROFIT_SPLIT_STAKE is a
real credit linked to its CHIPS_OUT. Rows created the old way would now be
discounted twice (the reduced CHIPS_OUT plus the new credit), so each
unlinked stake row's CHIPS_OUT is raised back to the full amount and the
pair is linked. Net player balances are unchanged by this; chips_out_total
becomes correct.

Irreversible by design: once linked, a backfilled pair is indistinguishable
from one created under the new code.
"""

from django.db import migrations


def backfill(apps, schema_editor):
    Transaction = apps.get_model('gaming', 'Transaction')
    stakes = Transaction.objects.filter(
        type='PROFIT_SPLIT_STAKE', linked_transaction__isnull=True,
    ).order_by('created_at', 'id')
    for stake in stakes:
        chips_out = (
            Transaction.objects.filter(
                type='CHIPS_OUT', player_id=stake.player_id, game_day_id=stake.game_day_id,
                profit_split_arrangement_id=stake.profit_split_arrangement_id,
                linked_transaction__isnull=True, created_at__lte=stake.created_at,
            )
            .order_by('-created_at', '-id')
            .first()
        )
        if chips_out is None:
            continue
        chips_out.amount = chips_out.amount + stake.amount
        chips_out.linked_transaction_id = stake.pk
        chips_out.save(update_fields=['amount', 'linked_transaction'])
        stake.linked_transaction_id = chips_out.pk
        fields = ['linked_transaction']
        # Old code never cascaded voids to the (then balance-neutral) stake
        # row; now that it's a credit, a voided buy-in's stake must be voided too.
        if chips_out.is_voided and not stake.is_voided:
            stake.is_voided = True
            stake.voided_by_id = chips_out.voided_by_id
            stake.voided_at = chips_out.voided_at
            stake.void_reason = chips_out.void_reason
            fields += ['is_voided', 'voided_by', 'voided_at', 'void_reason']
        stake.save(update_fields=fields)


class Migration(migrations.Migration):

    dependencies = [
        ('gaming', '0025_clubsettings_away_max_minutes_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
