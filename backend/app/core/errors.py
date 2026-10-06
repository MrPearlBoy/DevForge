"""Shared error types."""
from __future__ import annotations


class DevForgeError(Exception):
    """Base error for the DevForge platform."""


class AgentOutputError(DevForgeError):
    """Raised when an agent's LLM output cannot be parsed/validated even
    after a corrective re-prompt."""


class WorkflowError(DevForgeError):
    """Raised when the workflow state machine cannot proceed."""
