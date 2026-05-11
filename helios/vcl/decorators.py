"""@gated_by decorator and ContextVar manifest management."""

from __future__ import annotations

import functools
from collections.abc import Callable
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, TypeVar

from .registry import VCLFlag

if TYPE_CHECKING:
    from .config import VCLManifest

_current_manifest: ContextVar[VCLManifest | None] = ContextVar(
    "vcl_current_manifest", default=None
)

F = TypeVar("F", bound=Callable[..., Any])


class GatedComponentInactiveError(RuntimeError):
    """Raised when a @gated_by component is called under an inactive flag.

    The orchestrator catches this and routes the event to the exclusion ledger
    (§6.4 metric integrity gate, Stage 1+).
    """


def gated_by(flag: VCLFlag) -> Callable[[F], F]:
    """Decorator: register a component against a VCL flag and enforce runtime gating.

    Raises TypeError at *decoration time* if the flag is not boolean — prevents
    accidental gating on INGEST_MODE (a string flag).

    The decorated function gains a ``__gated_by__`` attribute used by the static
    CI disjointness audit (§3.9.1).
    """
    if flag not in VCLFlag.bool_flags():
        raise TypeError(
            f"VCLFlag.{flag.name} is not a boolean flag and cannot be used with "
            f"@gated_by. Use ingest_mode checks directly."
        )

    def decorator(func: F) -> F:
        func.__gated_by__ = flag.value  # type: ignore[attr-defined]

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            manifest = _current_manifest.get()
            if manifest is None:
                raise RuntimeError(
                    "VCLManifest not set in context — call set_current_manifest() "
                    "before invoking any @gated_by component."
                )
            if not getattr(manifest, flag.value):
                raise GatedComponentInactiveError(
                    f"Component '{func.__name__}' is gated by inactive flag "
                    f"'{flag.value}' "
                    f"(variant_config_hash={manifest.compute_variant_config_hash()})"
                )
            return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def set_current_manifest(manifest: VCLManifest) -> None:
    """Inject the active VCLManifest into the current async/thread context."""
    _current_manifest.set(manifest)


def get_current_manifest() -> VCLManifest | None:
    """Return the active VCLManifest, or None if not yet set."""
    return _current_manifest.get()
