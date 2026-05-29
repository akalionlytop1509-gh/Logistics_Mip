import io
import hashlib
import pandas as pd
from functools import lru_cache
from app.utils.excel_parser import load_logistics_data
from app.core.optimizer import HubLogisticsOptimizer
from app.core.postprocess import analyze_results
from app.utils.validator import validate_logistics_data

# Global cache for parsed data to avoid re-parsing same file
_PARSED_DATA_CACHE = {}

def get_data_from_bytes(file_hash: str, file_bytes: bytes):
    if file_hash in _PARSED_DATA_CACHE:
        return _PARSED_DATA_CACHE[file_hash]
    
    # Parse and store in cache
    data = load_logistics_data(io.BytesIO(file_bytes))
    
    # Simple cache management: if cache too big, clear it
    if len(_PARSED_DATA_CACHE) > 10:
        _PARSED_DATA_CACHE.clear()
        
    _PARSED_DATA_CACHE[file_hash] = data
    return data

def run_optimization(
    file_bytes: bytes,
    k_road: float,
    solve_mode: str,
    use_hub_capacity: bool,
    use_co2: bool = False,
):
    """
    Orchestrates the optimization process:
    1. Parse Excel data
    2. Run Optimizer
    3. Process results
    """
    # 1. Parse Data
    try:
        # Cache file loading by its SHA256 hash to prevent redundant parsing
        file_hash = hashlib.sha256(file_bytes).hexdigest()
        data = get_data_from_bytes(file_hash, file_bytes)
    except Exception as e:
        raise ValueError(f"Failed to parse Excel file: {str(e)}")

    # 2. Setup Hub Capacity if needed
    hub_cap = data.get('HubCapacity', {}) if use_hub_capacity else {}

    # 3. Initialize Optimizer
    try:
        # lambda_co2 và e_max được đọc từ sheet Params trong Excel (không nhập từ UI)
        optimizer = HubLogisticsOptimizer(
            data,
            k_road=k_road,
            hub_capacity=hub_cap,
            use_co2=use_co2,
        )
    except Exception as e:
        raise ValueError(f"Failed to initialize optimizer: {str(e)}")

    # 4. Validate Data before solving
    is_valid, validation_errors, validation_warnings = validate_logistics_data(data, optimizer)
    if not is_valid:
        return {
            "status": "infeasible",
            "message": "Dữ liệu không hợp lệ. Vui lòng sửa các lỗi sau:\n- " + "\n- ".join(validation_errors),
            "objective_value": 0,
            "metrics": {},
            "results_flow": [],
            "network_data": {"warnings": validation_warnings}
        }

    # 5. Solve
    if solve_mode.upper() == "MIP":
        res = optimizer.solve_two_stage()
        results_df, obj_val = res[0], res[1]
    else:
        results_df, obj_val = optimizer.solve_lp()

    # 5. Process results
    if results_df is None or results_df.empty:
        total_s = sum(optimizer.supply_map.values())
        total_d = sum(optimizer.demand_map.values())
        
        if total_s < total_d:
            msg = f"Dữ liệu không hợp lệ: Tổng Cung ({total_s}) nhỏ hơn Tổng Cầu + Xuất khẩu ({total_d}). Vui lòng kiểm tra lại Excel."
        else:
            msg = f"Mô hình Infeasible (Không tìm thấy lời giải). Tổng Cung ({total_s}) >= Tổng Cầu ({total_d}), nhưng mạng lưới bị tắc nghẽn. Hãy kiểm tra: 1) Capacity của các tuyến đường (Arcs) có đủ lớn không? 2) Có tuyến đường nào bị thiếu nối từ Nguồn đến Đích không? 3) Các ràng buộc k_road, Hub Capacity có quá chặt không?"
            
        return {
            "status": "infeasible",
            "message": msg,
            "objective_value": 0,
            "metrics": {},
            "results_flow": [],
            "network_data": {}
        }

    metrics = analyze_results(
        results_df,
        obj_val,
        port_nodes=optimizer.port_nodes,
        demand_map=optimizer.demand_map,
        export_demand_total=optimizer.export_demand_total,
    )

    # 6. Tính CO2 tổng trả về frontend
    co2_total = None
    if use_co2 and "CO2_Emission" in results_df.columns:
        co2_total = float(results_df["CO2_Emission"].sum())

    # Fill NaN with None for JSON serialization
    results_df = results_df.where(pd.notna(results_df), None)

    # ── Compute Node Balance for Node Analysis tab ──────────────────────
    # For each node: inflow = Σ flow arriving, outflow = Σ flow leaving
    nodes_info = data.get('nodes_info', {})
    node_balance = []
    all_nodes = list(optimizer.nodes)
    
    inflow_map = {}
    outflow_map = {}
    if results_df is not None and not results_df.empty:
        valid_flows = results_df[pd.notna(results_df['Flow'])]
        if not valid_flows.empty:
            inflow_map = valid_flows.groupby('To')['Flow'].sum().to_dict()
            outflow_map = valid_flows.groupby('From')['Flow'].sum().to_dict()

    for node in all_nodes:
        inflow = float(inflow_map.get(node, 0.0))
        outflow = float(outflow_map.get(node, 0.0))
        supply  = float(optimizer.supply_map.get(node, 0))
        demand  = float(optimizer.demand_map.get(node, 0))
        info    = nodes_info.get(node, {})
        node_balance.append({
            'node':        node,
            'node_name':   info.get('node_name', node),
            'node_type':   info.get('node_type', 'transship'),
            'tier':        info.get('tier', None),
            'design_cap':  info.get('design_cap', None),
            'supply':      supply,
            'demand':      demand,
            'inflow':      inflow,
            'outflow':     outflow,
            'balance':     round(inflow - outflow + supply - demand, 4),
        })

    return {
        "status": "optimal",
        "objective_value": obj_val,
        "co2_total": co2_total,
        "metrics": metrics,
        "results_flow": results_df.to_dict(orient="records"),
        "node_balance": node_balance,
        "network_data": {
            "supply_map":          optimizer.supply_map,
            "demand_map":          optimizer.demand_map,
            "port_nodes":          list(optimizer.port_nodes),
            "export_demand_total": optimizer.export_demand_total,
            "nodes":               list(optimizer.nodes),
            "all_arcs":            data['Arcs'].to_dict(orient="records"),
            "nodes_info":          nodes_info,   # ← NEW: {node_id: {tier, node_type, design_cap, node_name}}
        }
    }
