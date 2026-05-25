import os
import requests
import streamlit as st

# Support both env vars (local) and Streamlit Secrets (cloud)
def _get_config(key, default):
    """Get config from Streamlit Secrets first, then env vars."""
    try:
        return st.secrets.get(key, os.getenv(key, default))
    except Exception:
        return os.getenv(key, default)

API_BASE_URL = _get_config("API_BASE_URL", "http://localhost:8000/api/v1")
API_TIMEOUT_SECONDS = int(_get_config("API_TIMEOUT_SECONDS", "300"))

@st.cache_data(show_spinner=False)
def optimize_network(file_bytes, k_road, solve_mode, use_hub_capacity, use_co2=False):
    """
    Sends data to backend FastAPI for optimization.
    """
    url = f"{API_BASE_URL}/optimize"

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
        response = requests.post(url, files=files, data=data, timeout=API_TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.exceptions.Timeout:
        raise Exception(
            f"Backend request timed out after {API_TIMEOUT_SECONDS} seconds. "
            "Please try a smaller workbook or increase API_TIMEOUT_SECONDS."
        )
    except requests.exceptions.HTTPError as e:
        raise Exception(f"{e} - Details: {response.text}")
    except requests.exceptions.RequestException as e:
        raise Exception(f"Could not connect to backend API: {e}")
    return response.json()
