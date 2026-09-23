from rest_framework.permissions import BasePermission


class IsSeller(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == request.user.Role.SELLER)


class IsCollector(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == request.user.Role.COLLECTOR)


class IsOwner(BasePermission):
    """Object-level permission: object must have a `user` attribute."""

    def has_object_permission(self, request, view, obj):
        return getattr(obj, "user_id", None) == request.user.id
