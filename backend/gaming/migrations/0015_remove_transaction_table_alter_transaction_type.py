# Schema half of the two-step chip-custody revert — see 0014's comment and
# PLAN.md's dated revert entry. Split into its own migration so this
# ALTER TABLE doesn't land in the same transaction as 0014's bulk DELETE
# against the same table (Postgres: "pending trigger events").
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('gaming', '0014_delete_table_custody_transactions'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='transaction',
            name='table',
        ),
        migrations.AlterField(
            model_name='transaction',
            name='type',
            field=models.CharField(choices=[('CHIPS_OUT', 'Chips out'), ('CHIPS_IN', 'Chips in'), ('PAYMENT_CASH', 'Cash payment'), ('PAYMENT_TRANSFER', 'Transfer payment'), ('PAYMENT_POS', 'POS payment'), ('PAYMENT_DEAL', 'Deal'), ('PAYOUT', 'Payout to player'), ('WRITE_OFF', 'Write-off / credit'), ('RAKE', 'Rake'), ('TIP', 'Tip'), ('DEAL_TRANSFER_OUT', 'Deal transfer (out)'), ('DEAL_TRANSFER_IN', 'Deal transfer (in)'), ('PROFIT_SPLIT_STAKE', 'Profit split — house stake')], max_length=25),
        ),
    ]
