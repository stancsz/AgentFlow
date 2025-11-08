"""
Minimal shim for python-dotenv used during tests.

This project normally depends on `python-dotenv`. To keep the test run
lightweight in the dev container we provide a tiny local shim that exposes
the `load_dotenv` function used by `agentflow.config`. It is intentionally
minimal and safe (no file I/O) — in a real environment prefer installing
`python-dotenv` from pip.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional


def load_dotenv(dotenv_path: Optional[Path | str] = None, override: bool = False) -> None:
    """No-op loader used in tests.

    If a real `.env` file needs to be read in CI or development, install
    `python-dotenv` and remove this shim.
    """
    return None
