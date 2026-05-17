"""Field-name canonicalisation shared by ``pydantic-fields`` and
``dart-json-fields``.

Both extractors emit Units whose resource is a field name. To make
``isFollowed`` (Dart camelCase) cluster with ``is_followed`` (Python
snake_case), we canonicalise both to snake_case before emitting. The
canonical form is intentionally lossy: anyone reading the cluster
report still gets the original spelling in ``Unit.name`` and
``Unit.extra["raw_field"]``; only the cluster key is canonicalised.

Rules:

- Already-snake_case stays unchanged.
- ``camelCase`` / ``PascalCase`` splits on every uppercase letter
  preceded by a lowercase/digit (the standard regex pattern).
- Acronyms collapse: ``HTTPError`` → ``http_error`` (lookahead on
  next-lowercase).
- Leading underscores are preserved (``_internal`` stays
  ``_internal``).
"""

from __future__ import annotations

import re


# Splits ``HTTPError`` → ``HTTP_Error`` (acronym followed by titlecase
# word) before the second pass turns the whole thing lowercase.
_ACRONYM_THEN_WORD = re.compile(r"([A-Z]+)([A-Z][a-z])")
# Splits ``isFollowed`` → ``is_Followed`` (lower/digit followed by
# uppercase).
_LOWER_THEN_UPPER = re.compile(r"([a-z\d])([A-Z])")


def canonicalize_field(name: str) -> str:
    """Return the canonical snake_case form of a field-name token.

    >>> canonicalize_field("isFollowed")
    'is_followed'
    >>> canonicalize_field("is_followed")
    'is_followed'
    >>> canonicalize_field("HTTPError")
    'http_error'
    >>> canonicalize_field("user_id")
    'user_id'
    >>> canonicalize_field("_internal")
    '_internal'
    """
    if not name:
        return name
    s = _ACRONYM_THEN_WORD.sub(r"\1_\2", name)
    s = _LOWER_THEN_UPPER.sub(r"\1_\2", s)
    return s.lower()
