import os
import sys
from pathlib import Path
import requests
import streamlit as st

# Thêm thư mục backend vào sys.path để có thể import trực tiếp khi chạy All-in-One trên Cloud
_CURRENT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _CURRENT_DIR.parent
_BACKEND_DIR = _PROJECT_ROOT / "backend"

if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Support both env vars (local) and Streamlit Secrets (cloud)
def _get_config(key, default=None):
    """Get config from env vars first, then Streamlit Secrets."""
    val = os.getenv(key)
    if val is not None:
        return val
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return default

API_TIMEOUT_SECONDS = int(_get_config("API_TIMEOUT_SECONDS", "300"))

def _run_optimization_direct(file_bytes, k_road, solve_mode, use_hub_capacity, use_co2=False):
    """
    Runs the optimizer directly in-process without any HTTP request.
    Ideal for single-platform deployments (Streamlit Cloud).
    """
    from app.services.solver_service import run_optimization
    return run_optimization(
        file_bytes=file_bytes,
        k_road=k_road,
        solve_mode=solve_mode,
        use_hub_capacity=use_hub_capacity,
        use_co2=use_co2,
    )

def optimize_network(file_bytes, k_road, solve_mode, use_hub_capacity, use_co2=False):
    """
    Executes optimization.
    - If API_BASE_URL is explicitly set to an external URL (e.g. Render/VPS), sends HTTP request.
    - Otherwise (or on Streamlit Cloud standalone), runs in-process directly for best performance and zero downtime.
    """
    api_base_url = _get_config("API_BASE_URL", "")

    # If no external API_BASE_URL is provided or explicitly set to 'direct', run in-process directly
    if not api_base_url or api_base_url.strip().lower() in ("direct", "local", "in-process"):
        return _run_optimization_direct(
            file_bytes=file_bytes,
            k_road=k_road,
            solve_mode=solve_mode,
            use_hub_capacity=use_hub_capacity,
            use_co2=use_co2,
        )

    # Otherwise call via HTTP API
    url = f"{api_base_url.rstrip('/')}/optimize"
    files = {
        "file": ("data.xlsx", file_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    }
    data = {
        "k_road": k_road,
        "solve_mode": solve_mode,
        "use_hub_capacity": use_hub_capacity,
        "use_co2": use_co2,
    }

    try:
        session = requests.Session()
        session.trust_env = False
        response = session.post(url, files=files, data=data, timeout=API_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()

    except requests.exceptions.Timeout:
        raise Exception(
            f"Backend request timed out after {API_TIMEOUT_SECONDS} seconds. "
            "Please try a smaller workbook or increase API_TIMEOUT_SECONDS."
        )
    except requests.exceptions.HTTPError as e:
        try:
            error_details = response.text if 'response' in locals() else e.response.text
        except Exception:
            error_details = str(e)
        raise Exception(f"Backend API Error: {e} - Details: {error_details}")
    except requests.exceptions.RequestException as e:
        # Fallback to direct execution if backend server is unreachable
        try:
            return _run_optimization_direct(
                file_bytes=file_bytes,
                k_road=k_road,
                solve_mode=solve_mode,
                use_hub_capacity=use_hub_capacity,
                use_co2=use_co2,
            )
        except Exception as direct_err:
            raise Exception(f"Could not connect to backend API ({e}) and direct execution failed: {direct_err}")
