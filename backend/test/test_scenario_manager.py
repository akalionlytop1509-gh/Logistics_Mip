from frontend.scenario_manager import summarize_scenario_result


def test_summarize_optimal_response():
    response = {
        "status": "optimal",
        "objective_value": 1200,
        "co2_total": 4.5,
        "metrics": {
            "Total_Flow": 100,
            "Mode_Distribution": {"Road": 40, "Rail": 30, "Sea": 30},
            "Export_Flow": 25,
            "Domestic_Flow": 75,
        },
        "results_flow": [
            {"Flow": 40},
            {"Flow": 0},
            {"Flow": 60},
        ],
    }

    row = summarize_scenario_result("Base", response)

    assert row["scenario"] == "Base"
    assert row["status"] == "optimal"
    assert row["objective_value"] == 1200
    assert row["co2_total"] == 4.5
    assert row["total_flow"] == 100
    assert row["active_routes"] == 2
    assert row["road_flow"] == 40
    assert row["rail_flow"] == 30
    assert row["water_flow"] == 30
    assert row["road_share_pct"] == 40
    assert row["export_flow"] == 25
    assert row["domestic_flow"] == 75


def test_summarize_infeasible_response_without_metrics():
    row = summarize_scenario_result(
        "Road 30%",
        {
            "status": "infeasible",
            "message": "No feasible solution",
            "objective_value": 0,
        },
    )

    assert row["status"] == "infeasible"
    assert row["objective_value"] == 0
    assert row["total_flow"] == 0
    assert row["active_routes"] == 0
    assert row["road_share_pct"] == 0
    assert row["message"] == "No feasible solution"


def test_summarize_mode_names_are_case_insensitive():
    response = {
        "status": "optimal",
        "metrics": {
            "Total_Flow": 100,
            "Mode_Distribution": {
                "road": 15,
                "ROAD": 25,
                "barge": 20,
                "Waterway": 10,
            },
        },
        "results_flow": [],
    }

    row = summarize_scenario_result("Mixed", response)

    assert row["road_flow"] == 40
    assert row["water_flow"] == 30
    assert round(row["road_share_pct"], 2) == round(40 / 70 * 100, 2)


def test_summarize_missing_co2_is_allowed():
    row = summarize_scenario_result(
        "Green",
        {
            "status": "optimal",
            "metrics": {"Total_Flow": 10, "Mode_Distribution": {"Rail": 10}},
            "results_flow": [{"Flow": 10}],
        },
    )

    assert row["co2_total"] is None
    assert row["rail_flow"] == 10
