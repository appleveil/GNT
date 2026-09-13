from rest_framework.permissions import BasePermission

from .models import StaffUser


def _has_role(request, roles):
    return bool(request.user and request.user.is_authenticated and request.user.role in roles)


class IsCashier(BasePermission):
    def has_permission(self, request, view):
        return _has_role(request, {StaffUser.Role.CASHIER})


class IsAccountant(BasePermission):
    def has_permission(self, request, view):
        return _has_role(request, {StaffUser.Role.ACCOUNTANT})


class IsOwner(BasePermission):
    def has_permission(self, request, view):
        return _has_role(request, {StaffUser.Role.OWNER})


class IsCashierOrOwner(BasePermission):
    def has_permission(self, request, view):
        return _has_role(request, {StaffUser.Role.CASHIER, StaffUser.Role.OWNER})


class IsOwnerOrAccountant(BasePermission):
    def has_permission(self, request, view):
        return _has_role(request, {StaffUser.Role.OWNER, StaffUser.Role.ACCOUNTANT})
