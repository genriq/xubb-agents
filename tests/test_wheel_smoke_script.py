"""The clean-wheel smoke script (tools/wheel_smoke.py) must run, from OUTSIDE
the repository directory, against the current environment.

This proves the script and the runtime it exercises; the clean-wheel evidence
itself (built wheel, fresh venv, no source tree importable) is the CI job
``wheel-smoke`` in .github/workflows/contract-gate.yml, which runs the same
script WITHOUT ``--allow-source``.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "tools" / "wheel_smoke.py"


def test_smoke_script_passes_outside_the_checkout():
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    with tempfile.TemporaryDirectory() as cwd:
        proc = subprocess.run([sys.executable, str(SCRIPT), "--allow-source"], cwd=cwd, env=env,
                              capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "wheel smoke OK" in proc.stdout


def test_smoke_script_refuses_a_source_tree_import_without_the_flag():
    """NEGATIVE CONTROL: without --allow-source an editable/source import fails
    the distribution check (exit 2) — the CI job relies on this."""
    import xubb_agents
    location = Path(xubb_agents.__file__).resolve()
    if "site-packages" in str(location).replace("\\", "/"):
        return   # already a real install here: the control is exercised in CI
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    with tempfile.TemporaryDirectory() as cwd:
        proc = subprocess.run([sys.executable, str(SCRIPT)], cwd=cwd, env=env, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 2 and "not an installed distribution" in proc.stdout


def test_ci_runs_the_clean_wheel_job():
    workflow = (REPO / ".github" / "workflows" / "contract-gate.yml").read_text(encoding="utf-8")
    assert "wheel-smoke:" in workflow and "pip wheel" in workflow and "tools/wheel_smoke.py" in workflow
    assert "--allow-source" not in workflow.split("wheel-smoke:", 1)[1]
