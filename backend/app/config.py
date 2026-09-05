import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _normalize_database_url(url: str) -> str:
    """SQLAlchemy 2.x rejects the legacy 'postgres://' scheme that Supabase/Heroku-style
    providers hand out — rewrite it to 'postgresql://' so DATABASE_URL can be pasted
    in verbatim. Also route to psycopg2 explicitly so no other driver gets guessed."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://") and "+psycopg2" not in url:
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


DATABASE_URL = _normalize_database_url(
    os.getenv("DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'payroll.db')}")
)
IS_SQLITE = DATABASE_URL.startswith("sqlite")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
AI_MODEL = os.getenv("AI_MODEL", "claude-sonnet-4-5")

# Groq is an alternative live LLM provider for the Payroll Assistant's
# tool-calling path (app/llm_providers/). openai/gpt-oss-20b is an
# open-weight model built with function-calling as a first-class feature,
# and was confirmed (via a live smoke test against Groq's actual API) to
# both be available and to correctly select tools for this assistant's
# questions -- Meta's Llama 3.x line, an earlier default choice, returned
# "model not found" against Groq's current catalog. Picked over
# openai/gpt-oss-120b (the larger sibling) because a 20B model is plenty
# for narrow tool selection over this assistant's small fixed toolset --
# there's no reasoning-depth need here that would justify the larger model.
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")

# Explicit provider pin: "groq" or "anthropic". Empty/unset means automatic
# selection (see app/llm_providers/__init__.py): Groq if GROQ_API_KEY is set,
# else Anthropic if ANTHROPIC_API_KEY is set, else the deterministic
# fallback. An explicit value is authoritative -- if it's set but that
# provider's key is missing, the assistant falls back to the mock rather
# than silently substituting the other provider.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "").strip().lower()

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")

# SMTP is optional: if unset, app.email logs the message to console instead of
# sending, mirroring the ANTHROPIC_API_KEY mock-fallback convention above so
# local dev works with zero mail setup.
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "Payroll Validation <no-reply@company.com>")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
