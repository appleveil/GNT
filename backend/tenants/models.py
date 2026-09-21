from django.db import models
from django_tenants.models import DomainMixin, TenantMixin


class Client(TenantMixin):
    """
    One row per club — this IS the tenant. `django_tenants` creates and
    migrates a real Postgres schema for each row on save() (see
    `auto_create_schema` below), and every TENANT_APPS table (accounts,
    gaming, payments, ...) then lives entirely inside that schema: a
    club's players, transactions, staff logins, etc. are physically
    separate from every other club's, not just filtered by a foreign key.

    This model itself lives in the `public` schema (it's in SHARED_APPS),
    since a club has to be identifiable before its own schema can be
    switched into.
    """

    name = models.CharField(max_length=200)
    created_on = models.DateField(auto_now_add=True)
    # A simple on/off switch for suspending a club without deleting its
    # schema/data — not wired into any request-blocking logic yet (no
    # billing flow exists to drive it), just here so it doesn't need a
    # migration later.
    is_active = models.BooleanField(default=True)

    # django_tenants' default — spelled out because it's the whole point:
    # saving a new Client automatically creates and migrates its schema.
    auto_create_schema = True

    def __str__(self):
        return self.name


class Domain(DomainMixin):
    """
    Maps a hostname to a Client — e.g. `acme-club.yourapp.com` -> the
    "Acme Club" tenant. `TenantMainMiddleware` reads the request's Host
    header and looks it up here to decide which schema to run the request
    against. A Client can have more than one Domain row (useful later for
    a custom domain alongside the default one); `is_primary` marks which
    one is canonical.
    """
