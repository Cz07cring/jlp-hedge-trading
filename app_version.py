"""Executor build/version metadata."""

from __future__ import annotations

import os


APP_VERSION = os.getenv("APP_VERSION", "dev")
GIT_COMMIT = os.getenv("GIT_COMMIT", "unknown")
DOCKER_IMAGE = os.getenv("DOCKER_IMAGE", "ring07c/jlphedge:latest")
AUTO_UPDATE = os.getenv("AUTO_UPDATE", "true").lower() == "true"


def get_version_info() -> dict[str, str | bool]:
    """Return metadata sent to the SaaS API and printed at startup."""
    return {
        "version": APP_VERSION,
        "commit": GIT_COMMIT,
        "docker_image": DOCKER_IMAGE,
        "auto_update": AUTO_UPDATE,
    }
