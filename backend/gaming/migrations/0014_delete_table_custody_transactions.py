# Reverts the two-step chip-custody model (2026-09-21) — see PLAN.md's
# dated revert entry. TABLE_BUY_IN/TABLE_CASH_OUT read as confusing in the
# Cashier's ledger (a duplicate-looking row for every buy-in) and
# TABLE_CASH_OUT's only creation path (leave_table's HOLD/CASH_OUT
# dispositions) was never reachable from the frontend, so nothing real is
# lost by removing both.
#
# Data cleanup only — split from the schema changes (0015) because Postgres
# refuses an ALTER TABLE on gaming_transaction in the same transaction as a
# bulk DELETE against it ("pending trigger events").
from django.db import migrations


def delete_table_custody_transactions(apps, schema_editor):
    Transaction = apps.get_model('gaming', 'Transaction')
    Transaction.objects.filter(type__in=['TABLE_BUY_IN', 'TABLE_CASH_OUT']).delete()


def reverse(apps, schema_editor):
    # Not reversible — the deleted rows are gone. Re-running the forward
    # feature migration (0010-0013) would restore the SCHEMA, not this data.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('gaming', '0013_texas_holdem_rename_and_max_players'),
    ]

    operations = [
        migrations.RunPython(delete_table_custody_transactions, reverse),
    ]
