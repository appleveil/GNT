from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from tenants.models import Client, Domain


class Command(BaseCommand):
    help = (
        'Provisions a new club as a tenant: creates the Client (which auto-creates '
        'and migrates its Postgres schema), registers one or more Domains for it, '
        'and optionally seeds demo data into it. This is the whole "onboard a new '
        'client" operation — everything else (accounts, gaming, payments) is the '
        'same shared codebase, just running against this schema from now on.'
    )

    def add_arguments(self, parser):
        parser.add_argument('schema_name', help='Postgres schema name — lowercase, no spaces/hyphens, e.g. "acme_club".')
        parser.add_argument('name', help='Display name for the club, e.g. "Acme Club".')
        parser.add_argument(
            'domains',
            nargs='+',
            help='One or more hostnames that should resolve to this club (no port), '
            'e.g. acme-club.yourapp.com, or a dev IP/hostname like 127.0.0.1.',
        )
        parser.add_argument(
            '--seed',
            action='store_true',
            help="Also run accounts' seed_demo_data inside the new tenant's schema, for a quick working demo club.",
        )

    def handle(self, *args, **options):
        schema_name = options['schema_name']
        if Client.objects.filter(schema_name=schema_name).exists():
            raise CommandError(f'A tenant with schema_name "{schema_name}" already exists.')

        client = Client(schema_name=schema_name, name=options['name'])
        client.save()  # auto_create_schema=True — this line alone creates and migrates the schema.
        self.stdout.write(self.style.SUCCESS(f'Created tenant "{client.name}" (schema: {schema_name})'))

        for domain in options['domains']:
            Domain.objects.create(domain=domain, tenant=client, is_primary=(domain == options['domains'][0]))
            self.stdout.write(f'  domain: {domain}')

        if options['seed']:
            call_command('tenant_command', 'seed_demo_data', schema_name=schema_name)
