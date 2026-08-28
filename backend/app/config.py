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
