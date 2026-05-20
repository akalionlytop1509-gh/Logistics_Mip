import os
import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")

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

    response = requests.post(url, files=files, data=data)
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        raise Exception(f"{e} - Details: {response.text}")
    return response.json()
