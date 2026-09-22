from decimal import Decimal

from django.db import migrations

# Owner-managed CRUD for games/tables/buy-ins is explicitly parked for
# later (see PLAN.md's "Game/Table selection + two-step chip custody"
# entry) — for now, the two games and their one table each are seeded here.
# "One table per game, for now" is a convention, not a constraint: adding a
# second table later is just a new row via the admin/shell, no migration.
SEED = [
    ('Texas Hold\'em', 'Main Table', Decimal('500000')),
    ('Omaha', 'Main Table', Decimal('100000')),
]


def seed_games_and_tables(apps, schema_editor):
    Game = apps.get_model('gaming', 'Game')
    Table = apps.get_model('gaming', 'Table')
    for game_name, table_name, default_buy_in in SEED:
        game, _ = Game.objects.get_or_create(name=game_name)
        Table.objects.get_or_create(game=game, name=table_name, defaults={'default_buy_in': default_buy_in})


def remove_seeded_games_and_tables(apps, schema_editor):
    Game = apps.get_model('gaming', 'Game')
    Table = apps.get_model('gaming', 'Table')
    games = Game.objects.filter(name__in=[name for name, _, _ in SEED])
    Table.objects.filter(game__in=games).delete()  # game=PROTECT — delete tables before their game
    games.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('gaming', '0010_game_gameday_buy_in_amount_alter_transaction_type_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_games_and_tables, remove_seeded_games_and_tables),
    ]
