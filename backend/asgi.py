"""Vercel entrypoint. Vercel's Python runtime routes /api/* requests to this
service with the /api prefix intact (see vercel.json services.my_backend +
top-level rewrite), so the real FastAPI app — whose routes are unprefixed,
matching local `uvicorn app.main:app` dev usage — is mounted under /api here
rather than modifying every router's paths.

Local dev is unaffected: this file is never imported by `uvicorn app.main:app`.
"""
from fastapi import FastAPI

from app.main import app as api_app

app = FastAPI()
app.mount("/api", api_app)
