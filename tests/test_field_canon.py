"""Field-name canonicalisation tests."""

from __future__ import annotations

import pytest

from parallax.extractors._field_canon import canonicalize_field


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("isFollowed", "is_followed"),
        ("is_followed", "is_followed"),
        ("user_id", "user_id"),
        ("userId", "user_id"),
        ("userID", "user_id"),
        ("HTTPError", "http_error"),
        ("HTTPResponseCode", "http_response_code"),
        ("avatarUrl", "avatar_url"),
        ("AvatarUrl", "avatar_url"),
        ("_internal", "_internal"),
        ("ALLCAPS", "allcaps"),
        ("a", "a"),
        ("", ""),
        ("id", "id"),
        ("createdAt", "created_at"),
        ("from_user", "from_user"),
    ],
)
def test_canonicalize(raw: str, expected: str) -> None:
    assert canonicalize_field(raw) == expected
