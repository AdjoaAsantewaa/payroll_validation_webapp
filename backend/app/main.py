from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import CORS_ORIGINS, IS_SQLITE
from app.seed import create_tables, run_seed
from app.routers import auth, dashboard, submissions, exceptions, queries, export

app = FastAPI(title="Payroll Validation API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    # Local/dev convenience only. Production (Postgres) schema is owned by
    # Alembic migrations (`alembic upgrade head`) and demo data by an explicit
    # `python -m app.seed` run — neither should happen implicitly on every
    # cold start against a shared database.
    if IS_SQLITE:
        create_tables()
        run_seed()


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(submissions.router)
app.include_router(exceptions.router)
app.include_router(queries.router)
app.include_router(export.router)
