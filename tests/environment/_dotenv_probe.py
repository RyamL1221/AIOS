"""Run only by ``test_dotenv_isolation.py``, in a pytest of its own (the
name keeps it out of the suite's collection): after LiteLLM's import, no
name of the checkout's .env is in the environment."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_no_name_of_dotenv_after_importing_litellm():
    import litellm  # noqa: F401
    from dotenv import dotenv_values

    loaded = sorted(name for name in dotenv_values(ROOT / ".env")
                    if name in os.environ)
    assert loaded == [], f"names loaded from .env: {loaded}"
