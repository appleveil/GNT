from django.db import migrations

# Two fixes requested together (2026-09-21):
#   1. The seed migration (0011) already spells the name "Texas Hold'em" —
#      but if this environment's DB was migrated before that spelling
#      landed, the live row can still read plain "Texas". Rename
#      defensively rather than assuming the seed migration's own wording
#      is what's actually in the table.
#   2. Per-game seat caps: Texas Hold'em seats 9 (unchanged, matches the
#      field's own default — see Game.max_players), Omaha seats 8. Was one
#      constant shared by every game (gaming.services.MAX_ACTIVE_PLAYERS_
#      PER_GAME_DAY); see gaming.selectors.max_active_players for the
#      per-game-day resolution this now feeds.
MAX_PLAYERS = {
    'Texas Hold\'em': 9,
    'Omaha': 8,
}


def rename_and_set_max_players(apps, schema_editor):
    Game = apps.get_model('gaming', 'Game')
    texas = Game.objects.filter(name='Texas').first()
    if texas is not None:
        texas.name = 'Texas Hold\'em'
        texas.save(update_fields=['name'])
    for name, max_players in MAX_PLAYERS.items():
        Game.objects.filter(name=name).update(max_players=max_players)


def reverse(apps, schema_editor):
    # Not reversible in a meaningful way (we can't tell "Texas" apart from
    # a deliberately-renamed row after the fact) — no-op back.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('gaming', '0012_game_max_players'),
    ]

    operations = [
        migrations.RunPython(rename_and_set_max_players, reverse),
    ]
