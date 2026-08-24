from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import CORS_ORIGINS
from app.seed import init_db_and_seed
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
    init_db_and_seed()


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(submissions.router)
app.include_router(exceptions.router)
app.include_router(queries.router)
app.include_router(export.router)
