SCENARIOS = [
    {
        "name": "Kịch Bản 0",
        "k_road": 1.0,
        "use_hub_capacity": True,
        "use_co2": True,
        "solver_strategy": "MIP",  
    },
    {
        "name": "Kịch Bản 1",
        "k_road": 0.6,
        "use_hub_capacity": True,
        "use_co2": True,
        "solver_strategy": "MIP",  
    },
    {
        "name": "Kịch Bản 2",
        "k_road": 0.4,
        "use_hub_capacity": True,
        "use_co2": True,
        "solver_strategy": "MIP",  
    },
    {
        "name": "Kịch Bản 3",
        "k_road": 0.1,
        "use_hub_capacity": True,
        "use_co2": True,
        "solver_strategy": "MIP", 
    },
    {
        "name": "Kịch Bản 4",
        "k_road": 0,
        "use_hub_capacity": True,
        "use_co2": True,
        "solver_strategy": "MIP",
    },
    
]


def _mode_value(mode_distribution, *names):
    wanted = {name.lower() for name in names}
    total = 0.0
    for mode, value in (mode_distribution or {}).items():
        if str(mode).strip().lower() in wanted:
            total += float(value or 0)
    return total


def summarize_scenario_result(scenario_name, response, k_road=None, solver_strategy=None):
    metrics = response.get("metrics") or {}
    mode_distribution = metrics.get("Mode_Distribution") or {}
    total_flow = float(metrics.get("Total_Flow") or 0)
    road_flow = _mode_value(mode_distribution, "road")
    rail_flow = _mode_value(mode_distribution, "rail")
    water_flow = _mode_value(mode_distribution, "sea", "barge", "water", "waterway")
    results_flow = response.get("results_flow") or []
    active_routes = sum(1 for row in results_flow if float(row.get("Flow") or 0) > 0)
    modal_split_total = sum((float(v or 0) for v in mode_distribution.values()))
    road_share = (road_flow / modal_split_total * 100) if modal_split_total else 0.0

    return {
        "scenario": scenario_name,
        "k_road_limit": k_road,
        "status": response.get("status", "unknown"),
        "objective_value": float(response.get("objective_value") or 0),
        "co2_total": response.get("co2_total"),
        "total_flow": total_flow,
        "active_routes": active_routes,
        "road_flow": road_flow,
        "rail_flow": rail_flow,
        "water_flow": water_flow,
        "road_share_pct": road_share,
        "export_flow": float(metrics.get("Export_Flow") or 0),
        "domestic_flow": float(metrics.get("Domestic_Flow") or 0),
        "message": response.get("message", ""),
    }
