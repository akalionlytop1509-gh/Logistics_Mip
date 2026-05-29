import os
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("ortools")

from app.core.optimizer import HubLogisticsOptimizer
from app.core.postprocess import analyze_results
from app.utils.excel_parser import load_logistics_data


def _port_priority_data():
    return {
        "Supply": pd.DataFrame({
            "IP": ["PORT", "SRC"],
            "Supply": [30, 70],
        }),
        "Demand": pd.DataFrame({
            "DC": ["SINK"],
            "Demand": [60],
        }),
        "Arcs": pd.DataFrame({
            "From": ["PORT", "SRC", "SRC", "SINK"],
            "To": ["SINK", "SINK", "PORT", "PORT"],
            "Mode": ["Road", "Road", "Road", "Road"],
            "Distance": [1, 1, 1, 1],
            "UnitCost": [1, 1, 1, 1],
            "Cap": [100, 100, 100, 100],
            "FixedCost": [0, 0, 0, 0],
            "Enabled": [1, 1, 1, 1],
            "IsExport": [0, 0, 1, 1],
        }),
        "Params": pd.DataFrame({
            "Key": ["exportDemand", "TimeLimit"],
            "Value": [40, 5],
        }),
        "nodes_info": {
            "PORT": {"node_type": "port", "tier": 0},
            "SRC": {"node_type": "source", "tier": 1},
            "SINK": {"node_type": "sink", "tier": 2},
        },
        "ExportDemand": 40,
    }


def _assert_port_priority_invariants(opt):
    port_in_export = sum(
        info["export"]
        for (_, to_node, _), info in opt.last_flow_breakdown.items()
        if to_node == "PORT"
    )
    port_out_export = sum(
        info["export"]
        for (from_node, _, _), info in opt.last_flow_breakdown.items()
        if from_node == "PORT"
    )
    port_in_domestic = sum(
        info["domestic"]
        for (_, to_node, _), info in opt.last_flow_breakdown.items()
        if to_node == "PORT"
    )
    port_out_domestic = sum(
        info["domestic"]
        for (from_node, _, _), info in opt.last_flow_breakdown.items()
        if from_node == "PORT"
    )

    assert port_in_export == pytest.approx(40)
    assert port_out_export == pytest.approx(0)
    assert port_in_domestic == pytest.approx(0)
    assert port_out_domestic == pytest.approx(30)


def test_lp_respects_tier_zero_port_priority():
    opt = HubLogisticsOptimizer(_port_priority_data())

    result, _ = opt.solve_lp()

    assert result is not None
    assert not result.empty
    assert "PORT" in opt.port_nodes
    _assert_port_priority_invariants(opt)


def test_mip_respects_tier_zero_port_priority():
    opt = HubLogisticsOptimizer(_port_priority_data())

    result, _, _ = opt.solve()

    assert result is not None
    assert not result.empty
    _assert_port_priority_invariants(opt)


def test_fide_lp_metrics_do_not_double_count_export_or_domestic_flow():
    fide_path = Path("data/Fide.xlsx")
    if not fide_path.exists():
        pytest.skip("data/Fide.xlsx is not present in this checkout")

    data = load_logistics_data(str(fide_path))
    opt = HubLogisticsOptimizer(data)

    result, objective = opt.solve_lp()

    assert result is not None
    assert not result.empty
    metrics = analyze_results(
        result,
        objective,
        port_nodes=opt.port_nodes,
        demand_map=opt.demand_map,
        export_demand_total=opt.export_demand_total,
    )
    assert metrics["Export_Flow"] == 1_935_000
    assert metrics["Domestic_Flow"] == 2_065_000
    assert metrics["Total_Flow"] == 4_000_000


def test_fide_mip_two_stage_when_enabled():
    if os.getenv("RUN_SLOW_SOLVER_TESTS") != "1":
        pytest.skip("set RUN_SLOW_SOLVER_TESTS=1 to run the Fide MIP regression")

    fide_path = Path("data/Fide.xlsx")
    if not fide_path.exists():
        pytest.skip("data/Fide.xlsx is not present in this checkout")

    data = load_logistics_data(str(fide_path))
    opt = HubLogisticsOptimizer(data)

    result, _ = opt.solve_two_stage()

    assert result is not None
    assert not result.empty
