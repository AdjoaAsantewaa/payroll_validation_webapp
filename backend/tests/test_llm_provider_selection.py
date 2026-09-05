"""Regression tests for the provider-selection priority logic
(app/llm_providers/__init__.py's _resolve_provider_name).

PROVIDER_NAME is resolved once at import time from environment variables,
so each scenario needs a fresh Python process with its own environment --
these tests shell out rather than reload the module in-process, which is
the more faithful test of "what actually happens when the app starts up
with this env var combination."

Uses local SQLite only (DATABASE_URL is forced per subprocess). Never
touches Supabase. Run directly: `python backend/tests/test_llm_provider_selection.py`
"""
import os
import subprocess
import sys
import tempfile

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_THIS_DIR)
_DB_PATH = os.path.join(tempfile.gettempdir(), "payroll_provider_selection_test.db")

failures = []


def check(name, cond):
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        failures.append(name)


def resolved_provider(env_overrides: dict) -> str:
    env = dict(os.environ)
    # Force every provider-relevant var explicitly empty first -- NOT just
    # absent. backend/.env has a real GROQ_API_KEY for local dev use, and
    # config.py's load_dotenv() only skips a variable that's already
    # PRESENT in the environment (even set to ""); merely deleting the key
    # would leave it eligible to be silently refilled from that file, which
    # is exactly the bug that made "neither key set" resolve to "groq" the
    # first time this test was written.
    for key in ("GROQ_API_KEY", "ANTHROPIC_API_KEY", "LLM_PROVIDER"):
        env[key] = ""
    env["DATABASE_URL"] = f"sqlite:///{_DB_PATH}"
    env.update(env_overrides)
    result = subprocess.run(
        [sys.executable, "-c", "from app import llm_providers as lp; print(lp.PROVIDER_NAME)"],
        cwd=_BACKEND_DIR, env=env, capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"subprocess failed: {result.stderr}")
    return result.stdout.strip()


check("Neither key set -> no provider", resolved_provider({}) == "None")
check("GROQ_API_KEY only -> groq", resolved_provider({"GROQ_API_KEY": "fake"}) == "groq")
check("ANTHROPIC_API_KEY only -> anthropic", resolved_provider({"ANTHROPIC_API_KEY": "fake"}) == "anthropic")
check("Both keys set, no explicit LLM_PROVIDER -> groq preferred",
      resolved_provider({"GROQ_API_KEY": "fake", "ANTHROPIC_API_KEY": "fake"}) == "groq")
check("Both keys set, LLM_PROVIDER=anthropic -> explicit pin wins",
      resolved_provider({"GROQ_API_KEY": "fake", "ANTHROPIC_API_KEY": "fake", "LLM_PROVIDER": "anthropic"}) == "anthropic")
check("LLM_PROVIDER=groq explicit pin is honoured even with only that one key set",
      resolved_provider({"GROQ_API_KEY": "fake", "LLM_PROVIDER": "groq"}) == "groq")
check("LLM_PROVIDER=groq pinned but GROQ_API_KEY missing -> still resolves to groq (forced, "
      "not silently substituted) even though it will be unavailable",
      resolved_provider({"ANTHROPIC_API_KEY": "fake", "LLM_PROVIDER": "groq"}) == "groq")
check("LLM_PROVIDER set to an unrecognised value -> no provider, not a guess",
      resolved_provider({"GROQ_API_KEY": "fake", "LLM_PROVIDER": "bogus"}) == "None")

if os.path.exists(_DB_PATH):
    os.remove(_DB_PATH)

print()
if failures:
    print(f"{len(failures)} FAILURE(S): {failures}")
    sys.exit(1)
print("All provider-selection regression tests passed.")
