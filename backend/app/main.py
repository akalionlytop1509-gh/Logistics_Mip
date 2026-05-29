import os
import sys

# Thêm thư mục backend vào sys.path để Render có thể hiểu được module 'app'
# khi chạy lệnh uvicorn backend.app.main:app từ thư mục gốc
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router as api_router

app = FastAPI(
    title="Pro Hub API",
    description="Backend API for Logistics Optimizer",
    version="1.0.0"
)

# Get frontend URL from environment variable, default to localhost/127.0.0.1 for development
frontend_url = os.getenv("FRONTEND_URL", "http://localhost:8501,http://127.0.0.1:8501")
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
