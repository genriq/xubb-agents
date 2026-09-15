#!/usr/bin/env python3
"""The public API surface, derived from the shipped code.

This module is the *facts* half of the hybrid API reference (docs/PROCESS.md and
the 2026-09-15 documentation design review). It derives what can be derived
reliably — qualified member names, signatures, defaults, requiredness, enum
values, serialization exclusions — and nothing else. Meaning is written by hand
in ``docs/API_REFERENCE.md``; a generated fact never explains ownership,
lifecycle, units or failure behaviour, and must not pretend to.

Two consumers:

* ``tools/gen_api_facts.py`` writes the generated tables into the reference.
* ``tools/check_api_docs.py`` fails the build when the code, the declared
  inventory and the reference disagree.

The declared inventory (``docs/api/inventory.yaml``) is a hand-maintained list of
the *supported* surface. That is an enumeration, which this repository has been
burned by before (3.1.2) — the difference is that it is compared against reality
in BOTH directions on every build, so it cannot silently go stale: a new
parameter fails the gate until someone declares it, and a declared name that no
longer exists fails too.
"""
from __future__ import annotations

import enum
import inspect
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(ROOT, "src") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "src"))

import pydantic  # noqa: E402

INVENTORY = os.path.join(ROOT, "docs", "api", "inventory.yaml")
REFERENCE = os.path.join(ROOT, "docs", "API_REFERENCE.md")

#: Names inherited from pydantic/enum machinery. They are not this project's API.
_INHERITED = set(dir(pydantic.BaseModel)) | set(dir(enum.Enum)) | set(dir(str)) | set(dir(object))

_MISSING = object()


def _own(cls, name):
    """True when ``name`` is defined somewhere in ``cls``'s own xubb_agents MRO."""
    for base in cls.__mro__:
        if name in vars(base):
            return getattr(base, "__module__", "").startswith("xubb_agents")
    return False


def _fmt(value):
    if value is inspect.Parameter.empty or value is _MISSING:
        return None
    if isinstance(value, enum.Enum):
        return f"{type(value).__name__}.{value.name}"
    if callable(value) and not isinstance(value, type):
        return "<factory>"
    if isinstance(value, (list, dict, set)) and not value:
        return type(value).__name__ + "()"
    return repr(value)


def tidy(text):
    """Drop the noise that makes a generated table unreadable: module paths the
    reader already has from context, and enum reprs."""
    if text is None:
        return None
    text = str(text)
    for prefix in ("xubb_agents.core.models.", "xubb_agents.core.agent.",
                   "xubb_agents.core.insight_validation.", "xubb_agents.core.blackboard.",
                   "xubb_agents.core.", "xubb_agents.library.dynamic.", "typing."):
        text = text.replace(prefix, "")
    # <TriggerType.TURN_BASED: 'turn_based'>  ->  TriggerType.TURN_BASED
    text = re.sub(r"<(\w+)\.(\w+): [^>]+>",
                  lambda m: m.group(1) + "." + m.group(2), text)
    return text.replace("<class '", "").replace("'>", "").replace("ForwardRef", "").strip()


def _annotation(a):
    if a is inspect.Parameter.empty:
        return None
    # A typing construct has no useful __name__ ("Optional" loses its argument),
    # so only take __name__ for a plain class.
    text = a.__name__ if isinstance(a, type) else str(a)
    return tidy(text)


def members_of(cls, name):
    """Every supported qualified member of ``cls``, with its derived facts.

    Returns an ordered list of ``(qualified_name, facts)``. The rules are the
    whole point of this function, so they are stated rather than implied:

    * an **enum** contributes its members and their wire values, nothing else;
    * a **pydantic model** contributes its declared fields (type, requiredness,
      default, and whether it is excluded from serialization) plus any method
      the project defines on it;
    * a **plain class** contributes its ``__init__`` parameters and its own
      public methods.

    Inherited machinery is excluded throughout: ``model_dump`` is pydantic's API,
    not ours.
    """
    out = []
    if isinstance(cls, type) and issubclass(cls, enum.Enum):
        seen = set()
        for member in cls:
            if member.name in seen:
                continue
            seen.add(member.name)
            out.append((f"{name}.{member.name}", {"kind": "enum_member", "value": member.value}))
        return out

    if isinstance(cls, type) and issubclass(cls, pydantic.BaseModel):
        for field, info in cls.model_fields.items():
            facts = {
                "kind": "field",
                "type": _annotation(info.annotation),
                "required": info.is_required(),
                "default": None if info.is_required() else _fmt(
                    info.default if info.default is not pydantic.fields.PydanticUndefined else _MISSING),
            }
            if getattr(info, "exclude", False):
                # A field that exists in Python but never reaches a serialized
                # payload. A flat dump conceals this; the reference must not.
                facts["excluded_from_serialization"] = True
            out.append((f"{name}.{field}", facts))
    else:
        init = getattr(cls, "__init__", None)
        if init is not None and init is not object.__init__:
            try:
                for pname, p in inspect.signature(init).parameters.items():
                    if pname == "self" or p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
                        continue
                    out.append((f"{name}.__init__.{pname}", {
                        "kind": "parameter",
                        "type": _annotation(p.annotation),
                        "required": p.default is inspect.Parameter.empty,
                        "default": _fmt(p.default),
                    }))
            except (ValueError, TypeError):      # pragma: no cover - C-level callables
                pass

    for mname, value in inspect.getmembers(cls):
        if mname.startswith("_") or mname in _INHERITED or not callable(value):
            continue
        if not _own(cls, mname):
            continue
        try:
            sig = tidy(str(inspect.signature(value))).replace("(self, ", "(").replace("(self)", "()")
        except (ValueError, TypeError):          # pragma: no cover
            sig = "(...)"
        out.append((f"{name}.{mname}", {
            "kind": "coroutine" if inspect.iscoroutinefunction(value) else "method",
            "signature": sig,
        }))
    return out


def load_roots():
    """The declared classes, resolved to live objects. Import errors are fatal:
    a reference that cannot resolve its own subject is worthless."""
    import yaml
    with open(INVENTORY, "r", encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    import importlib
    roots = {}
    for name, entry in doc["classes"].items():
        module = importlib.import_module(entry["module"])
        roots[name] = (getattr(module, name), entry)
    return doc, roots


def derive():
    """``{class name: {"entry": inventory entry, "members": [(qname, facts)]}}``."""
    doc, roots = load_roots()
    surface = {}
    for name, (cls, entry) in roots.items():
        surface[name] = {"entry": entry, "members": members_of(cls, name)}
    return doc, surface
