# data_loader.py
import sys
import pandas as pd
import os
import warnings

# Fix Windows CP1252 encoding that crashes on emoji/Vietnamese chars
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


def _unit_scale(df, skip_cols):
    """
    Phát hiện cột đơn vị '1000 TEU/năm' trong DataFrame.
    Nếu có → trả về 1000.0 (cần nhân giá trị lên), ngược lại trả về 1.0.
    skip_cols: set tên cột dữ liệu chính (node name, value) không kiểm tra.
    """
    for col in df.columns:
        if col in skip_cols:
            continue
        # Kiểm tra tên cột
        if '1000' in str(col):
            return 1000.0
        # Kiểm tra giá trị trong cột
        for v in df[col].dropna().astype(str):
            if '1000' in v:
                return 1000.0
    return 1.0


def load_logistics_data(file_source):
    """
    Loads logistics data từ các sheet CỐT LÕI: Readme, Nodes, Arcs, Supply, Demand, Params.


    ✅ NEW:
    - Đọc sheet Nodes → Node_Type, Tier, Design_Cap, Node_Name
    - Tương thích ngược: auto-generate nodes_info nếu không có sheet Nodes
    - Extracts ExportDemand từ Params
    - Calculates TotalSupply, TotalDemand

    Args:
        file_source: str (file path) hoặc file-like object (UploadedFile)

    Returns:
        dict: {
            'Supply': DataFrame,
            'Demand': DataFrame,
            'Arcs':   DataFrame,
            'Params': DataFrame,
            'Nodes':  DataFrame,       # rỗng nếu không có sheet
            'Cost':   DataFrame,       # legacy placeholder (rỗng)
            'nodes_info': dict,        # {node_id: {tier, node_type, design_cap, node_name}}
            'ExportDemand': float,
            'TotalSupply':  float,
            'TotalDemand':  float,
            'HubCapacity':  dict,      # {node_id: design_cap} cho backward compat
        }
    """

    # 1. Check file existence & ExcelFile
    if isinstance(file_source, str):
        if not os.path.exists(file_source):
            return create_sample_data(file_source)

    try:
        xl = pd.ExcelFile(file_source)
        sheets = xl.sheet_names
    except Exception as e:
        raise Exception(f"Failed to read Excel file: {str(e)}")

    # ─── Helper: Flexible column/sheet matching ───────────────────────────────
    def find_sheet(candidates):
        """Tìm sheet match với list tên (support Việt-Anh, case-insensitive)"""
        for c in candidates:
            match = next((s for s in sheets if s.strip().lower() == c.lower()), None)
            if match:
                return match
        return None

    def get_col(df, *aliases):
        """Tìm cột match trong DataFrame (exact trước, partial sau)"""
        low_cols = {c: c.lower().strip() for c in df.columns}
        for alias in aliases:
            al = alias.lower().strip()
            exact = next((c for c, lc in low_cols.items() if lc == al), None)
            if exact:
                return exact
            partial = next((c for c, lc in low_cols.items() if al in lc), None)
            if partial:
                return partial
        return df.columns[0] if len(df.columns) > 0 else None

    # ─── Locate CORE sheets only ─────────────────────────────────────────────
    supply_s = find_sheet(['Supply', 'Cung'])
    demand_s = find_sheet(['Demand', 'Cầu'])
    arcs_s   = find_sheet(['Arcs', 'Arcs (MIP)', 'Arcs (LP)', 'Cung đường'])
    params_s = find_sheet(['Params', 'Parameters', 'Tham số'])
    nodes_s  = find_sheet(['Nodes', 'Node', 'Nút'])

    if not all([supply_s, demand_s, arcs_s]):
        raise ValueError(f"Missing required sheets (Supply, Demand, Arcs). Found: {sheets}")

    # ─── Load data ───────────────────────────────────────────────────────────
    data = {
        'Supply': xl.parse(supply_s),
        'Demand': xl.parse(demand_s),
        'Arcs':   xl.parse(arcs_s),
        'Params': xl.parse(params_s) if params_s else pd.DataFrame(columns=['Key', 'Value']),
        'Nodes':  xl.parse(nodes_s)  if nodes_s  else pd.DataFrame(),
    }

    # ═══════════════════════════════════════════════════════════════════════════
    # ✅ PARSE NODES SHEET → nodes_info dict
    # Schema: Node_Name | Tier | Node_Type (source/sink/transship/port) | Design_Cap
    # Node_Name là key duy nhất (không có cột Node_ID riêng trong MILP.xlsx)
    # ═══════════════════════════════════════════════════════════════════════════
    nodes_info = {}  # {node_name: {tier, node_type, design_cap, node_name}}

    nodes_df = data['Nodes']
    if not nodes_df.empty:
        # Node_Name là key chính — phải match với From/To trong Arcs và Supply/Demand
        n_name_col = get_col(nodes_df, 'Node_Name', 'Name', 'Tên', 'NodeName')
        n_type_col = get_col(nodes_df, 'Node_Type', 'Type', 'Loại', 'NodeType')
        n_tier_col = get_col(nodes_df, 'Tier', 'Tầng', 'Level')
        n_cap_col  = get_col(nodes_df, 'Design_Cap', 'DesignCap', 'Capacity', 'Công suất', 'Cap')
        n_lat_col  = get_col(nodes_df, 'Latitude', 'Lat')
        n_lon_col  = get_col(nodes_df, 'Longitude', 'Long', 'Lon')

        for _, row in nodes_df.iterrows():
            if n_name_col is None or pd.isna(row.get(n_name_col)):
                continue
            node_name = str(row[n_name_col]).strip()
            if not node_name:
                continue

            tier_raw = pd.to_numeric(row.get(n_tier_col), errors='coerce') if n_tier_col else None
            tier = int(tier_raw) if pd.notna(tier_raw) else 0

            raw_type = row.get(n_type_col)
            node_type = str(raw_type).strip().lower() if n_type_col and pd.notna(raw_type) else 'transship'

            cap_raw = pd.to_numeric(row.get(n_cap_col), errors='coerce') if n_cap_col else None
            design_cap = float(cap_raw) if pd.notna(cap_raw) else None

            lat_raw = pd.to_numeric(row.get(n_lat_col), errors='coerce') if n_lat_col else None
            lon_raw = pd.to_numeric(row.get(n_lon_col), errors='coerce') if n_lon_col else None
            latitude = float(lat_raw) if pd.notna(lat_raw) else None
            longitude = float(lon_raw) if pd.notna(lon_raw) else None

            nodes_info[node_name] = {
                'tier':       tier,
                'node_type':  node_type,   # 'source' | 'sink' | 'transship' | 'port'
                'design_cap': design_cap,
                'node_name':  node_name,
                'latitude':   latitude,
                'longitude':  longitude,
            }

    data['nodes_info'] = nodes_info

    # ═══════════════════════════════════════════════════════════════════════════
    # ✅ EXTRACT TOTAL SUPPLY / DEMAND / EXPORT (logic cũ giữ nguyên)
    # ═══════════════════════════════════════════════════════════════════════════

    # ── Phát hiện đơn vị '1000 TEU/năm' → nhân giá trị ×1000 nếu cần ──────────
    supply_node_col = get_col(data['Supply'], 'IP', 'Source', 'From', 'Node', 'Nguồn')
    supply_col      = get_col(data['Supply'], 'SupplyValue', 'Supply', 'Cung', 'Value')
    s_scale = _unit_scale(data['Supply'], {supply_node_col, supply_col})
    if s_scale != 1.0:
        data['Supply'][supply_col] = pd.to_numeric(
            data['Supply'][supply_col], errors='coerce') * s_scale
    total_supply = float(data['Supply'][supply_col].sum())

    demand_node_col = get_col(data['Demand'], 'DC', 'Destination', 'To', 'Node', 'Đích')
    demand_col      = get_col(data['Demand'], 'DemandValue', 'Demand', 'Cầu', 'Value')
    d_scale = _unit_scale(data['Demand'], {demand_node_col, demand_col})
    if d_scale != 1.0:
        data['Demand'][demand_col] = pd.to_numeric(
            data['Demand'][demand_col], errors='coerce') * d_scale
    total_demand = float(data['Demand'][demand_col].sum())

    # Extract ExportDemand từ Params (chỉ scale row ExportDemand nếu Params có cột '1000 TEU')
    export_demand = 0.0
    if not data['Params'].empty:
        p_key_col  = get_col(data['Params'], 'Key', 'Param', 'Parameter', 'Tham số', 'Name')
        p_val_col  = get_col(data['Params'], 'Value', 'Val', 'Giá trị')
        p_unit_col = get_col(data['Params'], 'Unit', 'Đơn vị', 'Units')  # cột đơn vị (nếu có)

        params_dict = {}
        for _, row in data['Params'].iterrows():
            if pd.notna(row[p_key_col]) and pd.notna(row[p_val_col]):
                key = str(row[p_key_col]).strip()
                val = float(pd.to_numeric(row[p_val_col], errors='coerce') or 0)
                # Scale per-row: chỉ khi cột đơn vị ghi '1000 TEU'
                if p_unit_col and pd.notna(row.get(p_unit_col)):
                    unit_str = str(row[p_unit_col])
                    if '1000' in unit_str and 'TEU' in unit_str.upper():
                        val *= 1000.0
                params_dict[key] = val

        export_demand = -1.0
        for k, v in params_dict.items():
            k_clean = str(k).lower().replace(" ", "").replace("_", "")
            if "exportdemand" in k_clean or "demandexport" in k_clean:
                export_demand = float(v)
                break

        # Fallback: nếu không có ExportDemand trong Params
        if export_demand < 0:
            export_demand = max(0.0, total_supply - total_demand)

    # Với MILP.xlsx: Port đã có trong Demand sheet (export demand = 2040 TEU)
    # → total_supply == total_demand (mạng cân bằng) → warning bên dưới không cần thiết
    # Vẫn giữ để cảnh báo nếu data không cân bằng
    total_need = total_demand + export_demand
    if total_supply < total_need and export_demand > 0:
        # Chỉ warn khi Port KHÔNG có trong Demand sheet (export demand chưa được đưa vào)
        port_in_demand = any(
            str(r.get(demand_node_col, '')).strip() in
            [str(r2.get(supply_node_col, '')).strip()
             for _, r2 in data['Supply'].iterrows()]
            for _, r in data['Demand'].iterrows()
        )
        if not port_in_demand:
            warnings.warn(
                f"IMBALANCE WARNING: Supply ({total_supply:,.0f}) < Need ({total_need:,.0f}). "
                f"Shortfall: {total_need - total_supply:,.0f} TEU. Solver may return INFEASIBLE.",
                UserWarning
            )

    data['ExportDemand'] = export_demand
    data['TotalSupply']  = total_supply
    data['TotalDemand']  = total_demand

    # ═══════════════════════════════════════════════════════════════════════════
    # ✅ BACKWARD COMPAT: HubCapacity từ nodes_info.Design_Cap

    # ═══════════════════════════════════════════════════════════════════════════
    data['HubCapacity'] = {
        nid: info['design_cap']
        for nid, info in nodes_info.items()
        if info.get('design_cap') is not None and info['design_cap'] > 0
    }

    return data


def create_sample_data(file_path):
    """Tạo sample data Excel với đầy đủ structure (bao gồm sheet Nodes)"""
    if not isinstance(file_path, str):
        raise ValueError("Cannot create sample data on a non-path source.")

    os.makedirs(os.path.dirname(file_path) if os.path.dirname(file_path) else '.', exist_ok=True)

    with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
        pd.DataFrame({
            'IP': ['KCN_A', 'KCN_B', 'Lach_Huyen'],
            'SupplyValue': [500, 400, 200]
        }).to_excel(writer, sheet_name='Supply', index=False)

        pd.DataFrame({
            'DC': ['Store_1', 'Store_2', 'Store_3'],
            'DemandValue': [300, 350, 250]
        }).to_excel(writer, sheet_name='Demand', index=False)

        pd.DataFrame({
            'Node_ID':    ['KCN_A', 'KCN_B', 'Hub_1', 'Hub_2', 'Lach_Huyen', 'Store_1', 'Store_2', 'Store_3'],
            'Node_Name':  ['KCN A',  'KCN B',  'Hub 1',  'Hub 2',  'Lạch Huyện', 'Store 1', 'Store 2', 'Store 3'],
            'Node_Type':  ['source', 'source', 'transship', 'transship', 'port', 'sink', 'sink', 'sink'],
            'Tier':       [2, 2, 1, 1, 0, 2, 2, 2],
            'Design_Cap': [None, None, 800, 600, None, None, None, None],
        }).to_excel(writer, sheet_name='Nodes', index=False)

        pd.DataFrame({
            'From': ['KCN_A', 'KCN_A', 'KCN_B', 'KCN_B', 'Lach_Huyen', 'Lach_Huyen'],
            'To':   ['Hub_1', 'Hub_1', 'Hub_1', 'Hub_2', 'Store_1',    'Store_2'],
            'Mode': ['Road',  'Rail',  'Road',  'Barge', 'Road',        'Road'],
            'Distance':  [1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
            'FixedCost': [1000, 5000, 1000, 3000, 500, 500],
            'Cap':       [400, 600, 400, 500, 1000, 1000],
            'UnitCost':  [1.5, 0.8, 1.5, 0.6, 1.0, 1.0],
            'IsExport':  [0, 0, 0, 0, 0, 0],
        }).to_excel(writer, sheet_name='Arcs', index=False)

        pd.DataFrame({
            'Key':   ['lambdaCO2', 'BigM', 'ExportDemand'],
            'Value': [0.05, 1_000_000, 250],
        }).to_excel(writer, sheet_name='Params', index=False)

    print(f"Created sample data: {file_path}")
    return load_logistics_data(file_path)
