from __future__ import annotations


class UtCoverError(Exception):
    """Base error for user-facing CLI failures."""


class ToolUnavailableError(UtCoverError):
    """Raised when an external tool such as git is missing."""


class CommandFailedError(UtCoverError):
    """Raised when an external command fails and the caller requested strict mode."""
