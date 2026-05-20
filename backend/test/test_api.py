import pytest
from fastapi.testclient import TestClient
import os
# Import app within fixture to avoid collection issues

# If run_server.py doesn't exist, we might need to import from where FastAPI app is defined
# Looking at routes.py, it's used in some main app file. 
# Let's try to import from the main entry point if possible.

# For now, let's create a dummy test to verify the structure
def test_read_main():
    # Placeholder for a real test
    assert True

@pytest.fixture
def client():
    # We need to find where the FastAPI 'app' is created. 
    # Usually it's in backend/app/main.py or similar.
    from backend.app.main import app
    return TestClient(app)

def test_optimize_endpoint(client):
    test_file_path = "data/Test.xlsx"
    if not os.path.exists(test_file_path):
        pytest.skip("Test file not found")
        
    with open(test_file_path, "rb") as f:
        response = client.post(
            "/api/v1/optimize",
            files={"file": ("Test.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={
                "k_road": 1.0,
                "solve_mode": "MIP",
                "use_hub_capacity": "false",
                "use_co2": "false"
            }
        )
    
    assert response.status_code == 200, f"Error: {response.json()}"
    data = response.json()
    assert "status" in data
    assert "node_balance" in data # This verifies our schema fix!
    assert len(data["node_balance"]) > 0
