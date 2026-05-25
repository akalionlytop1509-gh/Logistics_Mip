from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router as api_router
import os

app = FastAPI(
    title="Pro Hub API",
    description="Backend API for Logistics Optimizer",
    version="1.0.0"
)

# Get frontend URL from environment variable, default to localhost for development
frontend_url = os.getenv("FRONTEND_URL", "http://localhost:8501")
allowed_origins = [url.strip() for url in frontend_url.split(",") if url.strip()]
allow_credentials = "*" not in allowed_origins

# CORS middleware to allow requests from Streamlit frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=allow_credentials,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")

@app.get("/")
def read_root():
    return {"message": "Welcome to Pro Hub API"}
