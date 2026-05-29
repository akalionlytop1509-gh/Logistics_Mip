import os
import requests
import streamlit as st
import time

# Support both env vars (local) and Streamlit Secrets (cloud)
def _get_config(key, default):
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

def _get_api_base_url():
    """Read API_BASE_URL fresh every call to always use the latest secret."""
    return _get_config("API_BASE_URL", "http://127.0.0.1:8000/api/v1")

def optimize_network(file_bytes, k_road, solve_mode, use_hub_capacity, use_co2=False):
    """
    Sends data to backend FastAPI for optimization.
    Returns the result synchronously.
    """
    api_base_url = _get_api_base_url()
    url = f"{api_base_url}/optimize"

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
        raise Exception(f"Could not connect to backend API: {e}")

