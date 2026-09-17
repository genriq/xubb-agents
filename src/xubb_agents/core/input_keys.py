"""Unknown-key detection for the engine's closed input surfaces.

`SPEC_CONFIG_KEY_OWNERSHIP` states the rule: every input block the engine reads
is either **closed** (an unknown key is refused) or **open** (unknown keys are
the caller's business and pass through untouched), and which one it is must be
*declared* rather than left to whichever default a model happened to get.

`SPEC_AGENT_CONTEXT_CLOSURE` applies that rule to `AgentContext`. Both specs
stage the change the same way: **warn in 3.2.0, refuse in 4.0.0**, so a caller
gets one release of notice before a misspelt key becomes an error.

This module is the detection half, shared so that neither spec grows its own
copy. Two rules it exists to keep:

* **Derivation, not enumeration.** Callers pass the set of names the model
  itself declares. Nothing here keeps a hand-written list of field names. That
  is the lesson of the 3.1.1 -> 3.1.2 repair: the first fix enumerated the keys
  it policed, and the enumeration *was* the bug — a key nobody listed was a key
  nobody checked.
* **A hint never repairs.** `closest_name` suggests; it never selects. Guessing
  what a caller meant would silently grant a capability they did not
  successfully declare, which is a strictly worse failure than the silence being
  fixed.

The value a caller supplied is never read, logged or interpolated into a
message. These surfaces carry principal identity and host capability
declarations.
"""

from __future__ import annotations

import difflib
import warnings
from typing import Iterable, List, Optional, Sequence

#: How close a name must be before it is offered as a hint. Deliberately strict:
#: a bad guess is worse than no guess, because a reader who acts on it edits the
#: wrong key and the original mistake survives.
_HINT_CUTOFF = 0.75


def closest_name(unknown: str, known: Iterable[str]) -> Optional[str]:
    """The nearest declared name to `unknown`, or None when nothing is close.

    A hint only. It never selects behaviour: the unknown key stays unknown and
    the field it resembles keeps its default.
    """
    matches = difflib.get_close_matches(unknown, sorted(known), n=1, cutoff=_HINT_CUTOFF)
    return matches[0] if matches else None


def unknown_keys(supplied: Iterable[str], known: Iterable[str]) -> List[str]:
    """Names in `supplied` that the model does not declare, in a stable order.

    Sorted so a caller who misspells two keys gets the same two warnings in the
    same order on every run, which is what makes the behaviour testable.
    """
    known_set = set(known)
    return sorted(name for name in supplied if name not in known_set)


def warn_unknown_keys(
    surface: str,
    supplied: Iterable[str],
    known: Iterable[str],
    *,
    removal_release: str,
    reference: str,
    stacklevel: int = 2,
) -> Sequence[str]:
    """Warn once per unknown key, and return the keys warned about.

    `surface` names what the caller was building (``"AgentContext"``, or
    ``"Agent 'x': model_config"``) so the message is actionable without the
    caller reading a traceback. Returns the keys so a caller can assert on them
    without parsing warning text.
    """
    found = unknown_keys(supplied, known)
    for name in found:
        hint = closest_name(name, known)
        suggestion = (
            f" Did you mean '{hint}'? The key is not repaired: '{hint}' keeps its default."
            if hint else ""
        )
        warnings.warn(
            f"{surface}: unknown key '{name}' is ignored and will be refused in "
            f"{removal_release}.{suggestion} See {reference}.",
            DeprecationWarning,
            stacklevel=stacklevel,
        )
    return found
