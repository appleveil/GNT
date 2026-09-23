# Hand-written — companion to accounts.0006_staffmember_and_revert_login_roles.
# Transaction.masseuse's target model was renamed accounts.Masseuse ->
# accounts.StaffMember; the field itself (name, nullability, related_name)
# is unchanged. See PLAN.md's dated entry.
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_staffmember_and_revert_login_roles'),
        ('gaming', '0017_tip_category_rename_and_masseuse'),
    ]

    operations = [
        migrations.AlterField(
            model_name='transaction',
            name='masseuse',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name='tips_received', to='accounts.staffmember',
            ),
        ),
    ]
