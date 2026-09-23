# Hand-written — companion to accounts.0005_masseuse_and_new_staff_roles.
# Transaction.TipCategory's two values are renamed (DEALER -> SERVICE_STAFF,
# SERVICE -> MASSEUSE) and Transaction.service_staff (FK to what's now
# accounts.Masseuse) is renamed to Transaction.masseuse — behavior of each
# side is unchanged, only the label. See PLAN.md's dated entry.
#
# Order matters: RenameField first (so no existing row is ever briefly
# pointed at a field name that doesn't exist), then the max_length/choices
# AlterField widening tip_category to fit 'SERVICE_STAFF' (13 chars > the
# old 10), THEN the data migration remapping its stored values — doing the
# rename before the widen makes Postgres reject the UPDATE outright
# ("value too long for type character varying(10)"). Runs per-tenant-schema
# automatically, same as every other migration in this project.
import django.db.models.deletion
from django.db import migrations, models


def rename_tip_category_values(apps, schema_editor):
    Transaction = apps.get_model('gaming', 'Transaction')
    Transaction.objects.filter(tip_category='DEALER').update(tip_category='SERVICE_STAFF')
    Transaction.objects.filter(tip_category='SERVICE').update(tip_category='MASSEUSE')


def rename_tip_category_values_reverse(apps, schema_editor):
    Transaction = apps.get_model('gaming', 'Transaction')
    Transaction.objects.filter(tip_category='SERVICE_STAFF').update(tip_category='DEALER')
    Transaction.objects.filter(tip_category='MASSEUSE').update(tip_category='SERVICE')


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_masseuse_and_new_staff_roles'),
        ('gaming', '0016_gamedaysummary_chip_discrepancy_reason'),
    ]

    operations = [
        migrations.RenameField(model_name='transaction', old_name='service_staff', new_name='masseuse'),
        migrations.AlterField(
            model_name='transaction',
            name='tip_category',
            field=models.CharField(
                blank=True, choices=[('SERVICE_STAFF', 'Service staff'), ('MASSEUSE', 'Masseuse')],
                max_length=15, null=True,
            ),
        ),
        migrations.RunPython(rename_tip_category_values, rename_tip_category_values_reverse),
        migrations.AlterField(
            model_name='transaction',
            name='masseuse',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name='tips_received', to='accounts.masseuse',
            ),
        ),
    ]
