"""Environment validation shared by serverless endpoints."""
from __future__ import annotations

import os


def is_production() -> bool:
    return os.environ.get("ENTENSER_ENV") == "production"


def required_secret(name: str, development_default: str = "") -> str:
    value = os.environ.get(name)
    if value:
        return value
    if is_production():
        raise RuntimeError(f"{name} is required in production")
    return development_default


def access_token_secret() -> str:
    return required_secret("ACCESS_TOKEN_SECRET", "dev-only-insecure-secret")


def stripe_webhook_secret() -> str:
    return required_secret("STRIPE_WEBHOOK_SECRET", "")


def intelligence_root() -> str:
    return os.environ.get("INTELLIGENCE_ARTIFACT_ROOT", "data/team_intelligence")
