"""
Repo-root conftest: make ``import xubb_agents`` resolve regardless of the
checkout directory's name.

The repo root *is* the ``xubb_agents`` package (see ``[tool.setuptools.package-dir]``
in pyproject.toml, which maps ``xubb_agents = "."``). For ``import xubb_agents``
to succeed without ``pip install -e .``, the *parent* of this directory must be
on ``sys.path`` AND this directory must be named ``xubb_agents``.

To avoid depending on the checkout being literally named ``xubb_agents``, we
expose the package under that name explicitly: we add this directory's parent to
``sys.path`` and, if the directory has a different name, register it as the
``xubb_agents`` package so submodule imports (``xubb_agents.core.*``) resolve.
"""

import os
import sys
import importlib
import importlib.util

_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
_PARENT = os.path.dirname(_REPO_ROOT)

# Ensure the parent dir is importable (covers the dir-named-xubb_agents case).
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

# If the checkout dir isn't named "xubb_agents", bind the package name directly
# to this directory so that ``import xubb_agents`` and its submodules resolve.
if "xubb_agents" not in sys.modules:
    try:
        importlib.import_module("xubb_agents")
    except ModuleNotFoundError:
        spec = importlib.util.spec_from_file_location(
            "xubb_agents",
            os.path.join(_REPO_ROOT, "__init__.py"),
            submodule_search_locations=[_REPO_ROOT],
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules["xubb_agents"] = module
        spec.loader.exec_module(module)
