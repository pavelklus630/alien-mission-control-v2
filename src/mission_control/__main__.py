"""Entry point: python -m mission_control

In dev mode, runs the pytest suite (fast tests only, -m "not slow") before
starting the Tkinter launcher. If any test fails, startup is aborted with a
clear message — the four services are never started. This is the pre-launch
test gate (Phase 3 requirement).

In a frozen .app bundle, pytest is not available so the gate is bypassed
automatically. The build.sh script runs the full test suite as a separate step
before PyInstaller, providing equivalent protection during the build.
"""

from __future__ import annotations

import os
import subprocess
import sys

_FROZEN = getattr(sys, "frozen", False)
_SKIP_ENV = "MC_SKIP_TESTS"


def _run_gate() -> None:
    """Run the fast pre-launch test suite. Aborts the process on failure."""
    if _FROZEN:
        return  # pytest not bundled; build.sh tests guard the build instead
    if os.environ.get(_SKIP_ENV):
        return  # MC_SKIP_TESTS=1 lets you bypass during rapid dev iteration

    print("── pre-launch tests ──────────────────────────────────────────")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-m", "not slow", "-q", "--tb=short"],
        capture_output=False,
    )
    if result.returncode != 0:
        print(
            "\n[ABORT] Pre-launch tests FAILED — services not started.\n"
            f"        Fix the failures above, then run again.\n"
            f"        To bypass once (not recommended): {_SKIP_ENV}=1 python -m mission_control\n"
        )
        sys.exit(result.returncode)
    print("── all tests passed — starting Mission Control ───────────────\n")


def main() -> None:
    _run_gate()
    from .launcher.app import run
    run()


if __name__ == "__main__":
    main()
