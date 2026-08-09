"""Core execution adapter for bridge-backed Mari skill wrappers."""

from __future__ import annotations

from typing import Any, Callable


class MariBridgeDispatcher:
    """Run wrappers inline; the Mari plugin owns the actual UI-thread hop."""

    def dispatch_callable(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        for key in (
            "affinity",
            "context",
            "action_name",
            "skill_name",
            "execution",
            "timeout_hint_secs",
            "thread_affinity",
        ):
            kwargs.pop(key, None)
        return func(*args, **kwargs)
