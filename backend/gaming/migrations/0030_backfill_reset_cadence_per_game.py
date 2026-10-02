"""
Backfill for the 2026-10-02 stake-cap redesign (see ProfitSplitArrangement.
ResetCadence's own comment): DAILY/WEEKLY/MONTHLY refilled on a wall clock
measured from the arrangement's creation time, replaced by PER_GAME, which
refills when a new game-day opens and counts resets by games actually
played. Any existing row using one of the three removed values is rewritten
to PER_GAME — the closest equivalent, and the only recurring option left.
Irreversible by design (the original cadence distinction is gone).
"""
from django.db import migrations


def backfill(apps, schema_editor):
    ProfitSplitArrangement = apps.get_model('gaming', 'ProfitSplitArrangement')
    ProfitSplitArrangement.objects.filter(reset_cadence__in=['DAILY', 'WEEKLY', 'MONTHLY']).update(
        reset_cadence='PER_GAME',
    )


class Migration(migrations.Migration):

    dependencies = [
        ('gaming', '0029_alter_profitsplitarrangement_reset_cadence'),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
