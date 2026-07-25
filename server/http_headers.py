"""Case-insensitive HTTP header mapping for the API handlers.

RFC 9110 makes header field names case-insensitive, and HTTP/2 requires them to
be lowercase on the wire. Vercel's edge normalises accordingly, so a deployed
function sees ``authorization`` and ``stripe-signature`` no matter what the
client sent. Locally, ``BaseHTTPRequestHandler`` preserves the sender's casing.

``api/index.py`` used to hand handlers a plain ``dict`` built from
``self.headers.items()``, which threw away the case-insensitivity that
``email.message.Message`` provides. Every ``headers.get("Authorization")`` then
missed in production while passing locally and in tests -- silently 401-ing all
authenticated traffic and 400-ing every Stripe webhook.

Handlers should not have to remember this. ``Headers`` folds case on lookup so
both spellings resolve, while remaining a real ``dict`` so existing type hints,
``.items()`` iteration, and exact-case test fixtures keep working unchanged.
"""
from __future__ import annotations

_MISSING = object()


class Headers(dict):
    """A ``dict`` whose lookups ignore header-name case.

    Exact matches win, so behaviour is unchanged when the caller already uses
    the same spelling the sender did; otherwise the keys are compared folded.
    Lookup stays correct after mutation because nothing is cached -- header
    counts are small enough that the scan is irrelevant next to a network hop.
    """

    def _find(self, key, default=_MISSING):
        if dict.__contains__(self, key):
            return dict.__getitem__(self, key)
        if isinstance(key, str):
            folded = key.lower()
            for name, value in self.items():
                if isinstance(name, str) and name.lower() == folded:
                    return value
        if default is _MISSING:
            raise KeyError(key)
        return default

    def get(self, key, default=None):
        return self._find(key, default)

    def __getitem__(self, key):
        return self._find(key)

    def __contains__(self, key):
        return self._find(key, None) is not None
