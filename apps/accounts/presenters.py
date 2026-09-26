"""Response shapes for users, built as plain dicts (faster than model
serializers and field-for-field with the contract)."""

from apps.common.formatting import iso


def avatar_url(user, request=None) -> str | None:
    if not user.avatar:
        return None
    url = user.avatar.url
    return request.build_absolute_uri(url) if request is not None else url


def user_dict(user, request=None) -> dict:
    """The User shape (contract 3.3; unchanged in 4.1 and 4.2)."""
    return {
        "id": str(user.id),
        "phone": user.phone_number,
        "country_code": user.country_code,
        "full_name": user.full_name.strip() or None,
        "first_name": user.display_first_name,
        "initials": user.initials,
        "email": user.email or None,
        "avatar_url": avatar_url(user, request),
        "role": user.role,
        "language": user.language,
        "is_profile_complete": user.is_profile_complete,
        "created_at": iso(user.created_at),
    }


def display_name(user) -> str:
    """Name shown to the other side of a pickup."""
    return user.full_name.strip() or user.display_first_name or user.phone_masked
