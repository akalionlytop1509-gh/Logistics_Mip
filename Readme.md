# Pro Hub Logistics Optimizer

Enterprise Logistics Optimizer system with FastAPI backend and Streamlit frontend.

## Deployment Architecture

- **Backend**: FastAPI Web Service (Ready for Render)
- **Frontend**: Streamlit Community Cloud

### Local Development

1. Install dependencies:
   ```bash
   pip install -r backend/requirements.txt
   pip install -r frontend/requirements.txt
   ```
2. Run the application:
   ```bash
   python run.py
   ```
   This will start both the backend API (port 8000) and frontend dashboard (port 8501).

### Production Deployment

#### Backend (Render)
Connect this repository to Render as a Web Service.
- Root directory: `backend`
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Environment Variables:
  - `FRONTEND_URL`: Your Streamlit app URL
  - `MAX_UPLOAD_MB`: 20
  - `PYTHONUNBUFFERED`: 1

#### Frontend (Streamlit Community Cloud)
Connect this repository to Streamlit Community Cloud.
- Main file path: `frontend/app.py`
- Setup Secrets (App Settings > Secrets):
  ```toml
  API_BASE_URL = "https://<your-render-backend-url>/api/v1"
  API_TIMEOUT_SECONDS = "300"
  ```
