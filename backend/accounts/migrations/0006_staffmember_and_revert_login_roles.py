# Hand-written — corrects 0005_masseuse_and_new_staff_roles the same day:
# Masseuse/Dealer/Service were briefly added as StaffUser.Role login
# choices, then it was clarified none of the three ever actually log in.
# Reverted here, and Masseuse (the named-recipient roster) is generalized
# to StaffMember (role: MASSEUSE/DEALER/SERVICE) so the Owner has an actual
# non-login place to add all three from the Admin page. See PLAN.md's
# dated entry.
#
# Dependency note: must run AFTER gaming's last migration (0017), which
# still references 'accounts.masseuse' in its own AlterField — same
# cross-app RenameModel-ordering gotcha as 0005 hit (see that migration's
# own comment).
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_masseuse_and_new_staff_roles'),
        ('gaming', '0017_tip_category_rename_and_masseuse'),
    ]

    operations = [
        migrations.AlterField(
            model_name='staffuser',
            name='role',
            field=models.CharField(
                choices=[
                    ('CASHIER', 'Cashier'), ('ACCOUNTANT', 'Accountant'), ('OWNER', 'Owner'),
                    ('FLOOR_MANAGER', 'Floor Manager'),
                ],
                max_length=20,
            ),
        ),
        migrations.RenameModel(old_name='Masseuse', new_name='StaffMember'),
        migrations.AddField(
            model_name='staffmember',
            name='role',
            field=models.CharField(
                choices=[('MASSEUSE', 'Masseuse'), ('DEALER', 'Dealer'), ('SERVICE', 'Service')],
                default='MASSEUSE', max_length=10,
            ),
        ),
        migrations.AlterField(
            model_name='staffmember',
            name='created_by',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, related_name='staff_members_added',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
