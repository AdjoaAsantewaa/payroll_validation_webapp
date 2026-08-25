from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import NullPool

from app.config import DATABASE_URL, IS_SQLITE

if IS_SQLITE:
    # Local dev convenience: a single file, threaded FastAPI dev server.
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    # Serverless (Vercel): each function invocation may be a fresh, short-lived
    # process, so a warm connection pool just leaks connections across cold
    # starts instead of helping. NullPool opens a connection per request and
    # closes it immediately after — safe against Supabase's pooled ("Transaction
    # mode", port 6543) connection string, which is what DATABASE_URL should
    # point to in production. pool_pre_ping guards against the pooler closing
    # an idle connection out from under a long-lived worker in non-serverless
    # deployments (e.g. `uvicorn` on a normal host).
    engine = create_engine(DATABASE_URL, poolclass=NullPool, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
