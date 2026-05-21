from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.routers import health, jobs, preview

app = FastAPI(title="doc-to-app", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(jobs.router)
app.include_router(preview.router)
