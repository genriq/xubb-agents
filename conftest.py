"""
Repo-root conftest: make ``import xubb_agents`` resolve when running the tests
from a source checkout without ``pip install -e .``.

The repo root *is* the ``xubb_agents`` package (see ``[tool.setuptools.package-dir]``
in pyproject.toml, which maps ``xubb_agents = "."``). For ``import xubb_agents`` to
succeed, the *parent* of this directory must be on ``sys.path`` and this directory
must be named ``xubb_agents``. pytest also names the root package after the
directory, so a differently-named checkout (e.g. a default ``xubb-agents`` clone)
breaks collection with "attempted relative import with no known parent package".
Clone into ``xubb_agents`` (or ``pip install -e .``) — which is what CI does.

The best-effort fallback below only helps when the package can still be imported
under its own name; it is not a substitute for the directory-name requirement.
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
