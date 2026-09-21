"""
Tenant-aware drop-in replacements for `django.test.TestCase` and DRF's
`rest_framework.test.APITestCase`.

Every TENANT_APPS model (Player, Transaction, StaffUser, ...) only exists
inside a tenant's own Postgres schema — the plain versions of these base
classes run against the `public` schema, where none of those tables exist
at all, so every test using them fails with "relation does not exist".
`django_tenants.test.cases.TenantTestCase` creates a real throwaway tenant
(schema `test`, domain `tenant.test.com`) once per test class and points
the connection at it — these just add the DRF test client on top, exactly
as `rest_framework.test.APITestCase` does for plain `TestCase`.

Import these instead of the originals in any app's tests.py — nothing else
about how the tests are written changes.
"""

from django.test import override_settings
from django_tenants.test.cases import TenantTestCase
from rest_framework.test import APIClient

__all__ = ['TestCase', 'APITestCase']


class _TenantTestFixupMixin:
    """
    Two things `TenantTestCase.setUpClass` gets wrong for this project's
    tests, both fixed here rather than in every test file:

    1. Django's test client defaults to `Host: testserver` on every
       request (`SERVER_NAME`) — TenantMainMiddleware resolves the tenant
       from that Host header, so unless the throwaway test tenant's Domain
       matches it exactly, every request made through self.client 404s
       before it even reaches a view. TenantTestCase's own default domain
       ('tenant.test.com') doesn't match.

    2. TenantTestCase.setUpClass() never calls super().setUpClass(), which
       silently skips SimpleTestCase's own handling of a class-level
       `@override_settings(...)` decorator — the override just never
       activates, and affected tests run against real settings instead
       (see payments/tests.py's PAYSTACK_SECRET_KEY tests, which is what
       surfaced this). Re-applied explicitly here, the same way
       SimpleTestCase itself does it.
    """

    @classmethod
    def get_test_tenant_domain(cls):
        return 'testserver'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if cls._overridden_settings:
            cls.enterClassContext(override_settings(**cls._overridden_settings))


class TestCase(_TenantTestFixupMixin, TenantTestCase):
    pass


class APITestCase(_TenantTestFixupMixin, TenantTestCase):
    client_class = APIClient
