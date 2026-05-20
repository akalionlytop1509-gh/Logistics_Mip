from ortools.sat.python import cp_model
from ortools.linear_solver import pywraplp
import pandas as pd


class HubLogisticsOptimizer:
    def __init__(self, data, k_road=1.0, hub_capacity=None, use_co2=False):
        self.k_road = k_road
        self.use_co2 = use_co2
        self.hub_capacity = hub_capacity or {}

        def get_col(df, *aliases):
            low_cols = {c: c.lower().strip() for c in df.columns}
            for alias in aliases:
                al = alias.lower().strip()
                exact = next((c for c, lc in low_cols.items() if lc == al), None)
                if exact: return exact
                partial = next((c for c, lc in low_cols.items() if al in lc), None)
                if partial: return partial
            return df.columns[0] if len(df.columns) > 0 else None

        s_df = data['Supply']
        node_s = get_col(s_df, 'IP', 'Source', 'From', 'Node', 'Nguồn')
        val_s  = get_col(s_df, 'SupplyValue', 'Supply', 'Cung', 'Value')
        self.supply_map = {
            str(r[node_s]).strip(): float(r[val_s])
            for _, r in s_df.iterrows()
            if pd.notna(r[node_s]) and pd.notna(r[val_s])
        }

        d_df = data['Demand']
        node_d = get_col(d_df, 'DC', 'Destination', 'To', 'Node', 'Đích')
        val_d  = get_col(d_df, 'DemandValue', 'Demand', 'Cầu', 'Value')
        self.demand_map = {
            str(r[node_d]).strip(): float(r[val_d])
            for _, r in d_df.iterrows()
            if pd.notna(r[node_d]) and pd.notna(r[val_d])
        }

        arcs_df = data['Arcs'].copy().reset_index(drop=True)

        from_col     = get_col(arcs_df, 'From', 'Từ', 'Origin')
        to_col       = get_col(arcs_df, 'To', 'Đến', 'Destination')
        mode_col     = get_col(arcs_df, 'Mode', 'Phương thức', 'Type', 'Loại')
        cap_col      = get_col(arcs_df, 'Cap', 'Capacity', 'Công suất', 'Sức chứa')
        uc_col       = get_col(arcs_df, 'UnitCost', 'Chi phí', 'Cost', 'Đơn giá')
        dist_col     = get_col(arcs_df, 'Distance', 'Khoảng cách', 'Km', 'Dist')
        fc_col       = get_col(arcs_df, 'FixedCost', 'Fixed', 'Phí mở', 'Cố định')
        en_col       = get_col(arcs_df, 'Enabled', 'Active', 'Sử dụng')
        isexport_col = get_col(arcs_df, 'IsExport', 'Export', 'Xuất khẩu')

        if en_col and en_col in arcs_df.columns:
            enabled_vals = arcs_df[en_col].dropna()
            if enabled_vals.isin([0, 1, True, False]).all():
                arcs_df = arcs_df[arcs_df[en_col].astype(str).isin(['1', 'True', 'true'])]

        arcs_df = arcs_df.dropna(subset=[from_col, to_col, mode_col])
        arcs_df[from_col] = arcs_df[from_col].astype(str).str.strip()
        arcs_df[to_col]   = arcs_df[to_col].astype(str).str.strip()
        arcs_df[mode_col] = arcs_df[mode_col].astype(str).str.strip()
        arcs_df[cap_col]  = pd.to_numeric(arcs_df[cap_col], errors='coerce').fillna(1000)
        arcs_df[uc_col]   = pd.to_numeric(arcs_df[uc_col],  errors='coerce').fillna(0)
        arcs_df[fc_col]   = pd.to_numeric(arcs_df[fc_col],  errors='coerce').fillna(0)

        if dist_col and dist_col in arcs_df.columns and dist_col not in (from_col, to_col, mode_col):
            arcs_df[dist_col] = pd.to_numeric(arcs_df[dist_col], errors='coerce').fillna(1.0)
        else:
            arcs_df['_dist'] = 1.0
            dist_col = '_dist'

        if isexport_col and isexport_col in arcs_df.columns and isexport_col not in (from_col, to_col):
            arcs_df[isexport_col] = pd.to_numeric(arcs_df[isexport_col], errors='coerce').fillna(0)
        else:
            arcs_df['IsExport'] = 0
            isexport_col = 'IsExport'

        self.arcs         = arcs_df
        self.arc_from     = from_col
        self.arc_to       = to_col
        self.arc_mode     = mode_col
        self.arc_cap      = cap_col
        self.arc_uc       = uc_col
        self.arc_dist     = dist_col
        self.arc_fc       = fc_col
        self.arc_isexport = isexport_col

        self.port_nodes = set(
            arcs_df.loc[arcs_df[isexport_col] == 1, to_col]
            .astype(str).str.strip().unique()
        )
        
        if hasattr(self, 'nodes_info') and self.nodes_info:
            for nid, info in self.nodes_info.items():
                if info.get('node_type') == 'port':
                    self.port_nodes.add(str(nid).strip())
        elif data.get('nodes_info'):
            for nid, info in data.get('nodes_info', {}).items():
                if info.get('node_type') == 'port':
                    self.port_nodes.add(str(nid).strip())

        p_df = data.get('Params', pd.DataFrame())
        self.params = {}
        if not p_df.empty:
            p_key = get_col(p_df, 'Key', 'Param', 'Parameter', 'Tham số', 'Name')
            p_val = get_col(p_df, 'Value', 'Val', 'Giá trị')
            self.params = {
                str(r[p_key]).strip(): pd.to_numeric(r[p_val], errors='coerce')
                for _, r in p_df.iterrows() if pd.notna(r[p_key])
            }

        self.emission_factors = {}
        for key, val in self.params.items():
            k_lower = key.strip().lower()
            if k_lower.startswith('ef_') or k_lower.startswith('emissionfactor_'):
                sep = k_lower.index('_')
                mode_name_lower = k_lower[sep + 1:]
                if pd.notna(val) and float(val) > 0:
                    self.emission_factors[mode_name_lower] = float(val)
        
        self.co2_data_available = bool(self.emission_factors)

        total_s = sum(self.supply_map.values())
        total_d = sum(self.demand_map.values())

        raw_export = self.params.get('ExportDemand', None)
        if raw_export is not None and not pd.isna(raw_export):
            self.export_demand_total = int(float(raw_export))
        else:
            self.export_demand_total = max(0, int(total_s - total_d))

        existing_port_demand = sum(self.demand_map.get(port, 0) for port in self.port_nodes)
        port_demand_shortfall = max(0, self.export_demand_total - existing_port_demand)
        
        if port_demand_shortfall > 0 and self.port_nodes:
            export_per_port = int(port_demand_shortfall // len(self.port_nodes))
            remainder = int(port_demand_shortfall % len(self.port_nodes))
            for i, port in enumerate(self.port_nodes):
                self.demand_map[port] = self.demand_map.get(port, 0) + export_per_port + (1 if i < remainder else 0)

        self.nodes = set(self.arcs[self.arc_from]) | set(self.arcs[self.arc_to])
        
        # Calculate dynamic loop penalty to prevent cycle tricks in LP (GLOP) 
        # caused by large numeric scaling differences in currencies like VND.
        # It is set to 0.001 of the mean non-zero unit cost.
        non_zero_costs = self.arcs[self.arc_uc][self.arcs[self.arc_uc] > 0]
        mean_uc = float(non_zero_costs.mean()) if not non_zero_costs.empty else 1.0
        self.loop_penalty = max(1e-4, mean_uc * 0.001)

        self.arc_lookup = {}
        for _, row in self.arcs.iterrows():
            self.arc_lookup[(row[self.arc_from], row[self.arc_to], row[self.arc_mode])] = {
                'is_export': int(row[self.arc_isexport]),
                'dist': float(row[self.arc_dist]),
                'uc': float(row[self.arc_uc]),
                'fc': int(row[self.arc_fc])
            }

    def solve(self):
        time_limit = float(self.params.get('TimeLimit', 60))
        
        total_s = sum(self.supply_map.values())
        total_d = sum(self.demand_map.values())
        
        if total_s < total_d:
            print(f"INFEASIBLE: Total Supply ({total_s}) < Total Demand ({total_d})")
            return None, 0, None

        model = cp_model.CpModel()
        x, y = {}, {}

        # Miller-Tucker-Zemlin (MTZ) potential variables to prevent directed cycles
        pot = {}
        num_nodes = len(self.nodes)
        for node in self.nodes:
            pot[node] = model.NewIntVar(0, num_nodes - 1, f'pot_{node}')

        out_arcs = {n: [] for n in self.nodes}
        in_arcs = {n: [] for n in self.nodes}

        for _, row in self.arcs.iterrows():
            u, v, m = row[self.arc_from], row[self.arc_to], row[self.arc_mode]
            if str(u).strip() == str(v).strip():
                continue
            cap = int(row[self.arc_cap])

            x[u, v, m] = model.NewIntVar(0, cap, f'x_{u}_{v}_{m}')
            y[u, v, m] = model.NewBoolVar(f'y_{u}_{v}_{m}')
            model.Add(x[u, v, m] <= cap * y[u, v, m])
            
            # MTZ Constraint: If the arc is active (y == 1), then pot[v] >= pot[u] + 1
            # This mathematically prevents any directed cycles in the selected subgraph.
            model.Add(pot[v] >= pot[u] + 1).OnlyEnforceIf(y[u, v, m])
            
            out_arcs[u].append((u, v, m))
            in_arcs[v].append((u, v, m))

        # ── Single-Commodity Flow Conservation ──
        for node in self.nodes:
            total_in  = sum(x[arc] for arc in in_arcs[node])
            total_out = sum(x[arc] for arc in out_arcs[node])
            supply = int(self.supply_map.get(node, 0))
            demand = int(self.demand_map.get(node, 0))

            if node in self.port_nodes:
                model.Add(total_in + supply == total_out + demand)
            else:
                if supply > 0 and demand == 0:
                    model.Add(total_out - total_in == supply)
                elif demand > 0 and supply == 0:
                    model.Add(total_in - total_out == demand)
                elif supply > 0 and demand > 0:
                    model.Add(total_in + supply == total_out + demand)
                else:
                    model.Add(total_in == total_out)

        # ── Virtual Loop Prevention (k_mode constraints) ──
        if self.export_demand_total > 0 and self.port_nodes:
            export_inflow = sum(
                sum(x[arc] for arc in in_arcs[port])
                for port in self.port_nodes if port in in_arcs
            )
            model.Add(export_inflow >= self.export_demand_total)

        # Generalize k_road to all modes: if k_rail, k_barge, etc. are in params
        all_modes = set(str(m).lower() for (_, _, m) in x)
        for mode_name in all_modes:
            # Check for k_{mode} parameter (e.g., k_road, k_rail)
            k_param_key = f'k_{mode_name}'
            # Default to self.k_road for 'road' mode if k_road is not explicitly in params but was passed in __init__
            k_val = self.params.get(k_param_key)
            if mode_name == 'road' and k_val is None:
                k_val = self.k_road
            
            if k_val is not None and float(k_val) < 5.0: # Ignore if k is very large
                mode_flow = sum(x[u, v, m] for (u, v, m) in x if str(m).lower() == mode_name)
                real_required_flow = int(total_d)
                k_pct = int(float(k_val) * 100)
                model.Add(mode_flow * 100 <= real_required_flow * k_pct)

        if self.hub_capacity:
            for hub_node, cap_val in self.hub_capacity.items():
                matched = next((n for n in self.nodes if n.lower().replace('-','').replace(' ','') == hub_node.lower().replace('-','').replace(' ','')), None)
                if matched:
                    hub_inflow = sum(x[u, v, m] for (u, v, m) in x if v == matched)
                    cap_teu = int(cap_val * 1000) if cap_val < 5000 else int(cap_val)
                    model.Add(hub_inflow <= cap_teu)

        lambda_co2 = float(self.params.get('lambdaCO2', 0) or 0) if self.use_co2 else 0.0

        if self.use_co2:
            raw_emax = (self.params.get('E_max', None) or self.params.get('Emax', None) or self.params.get('emax', None))
            if raw_emax is not None and not pd.isna(raw_emax):
                e_max_val = float(raw_emax)
                ef_terms = []
                for _, row in self.arcs.iterrows():
                    u2, v2, m2 = row[self.arc_from], row[self.arc_to], row[self.arc_mode]
                    if str(u2).strip() == str(v2).strip(): continue
                    ef2 = float(self.emission_factors.get(str(m2).lower(), 0))
                    dist2 = float(row[self.arc_dist])
                    if ef2 > 0:
                        ef_terms.append(x[u2, v2, m2] * int(ef2 * dist2 * 100))
                if ef_terms:
                    e_max_scaled = int(e_max_val * 1000 * 100)
                    model.Add(sum(ef_terms) <= e_max_scaled)

        cost_terms = []
        for _, row in self.arcs.iterrows():
            u, v, m = row[self.arc_from], row[self.arc_to], row[self.arc_mode]
            if str(u).strip() == str(v).strip(): continue
            uc, dist, fc = float(row[self.arc_uc]), float(row[self.arc_dist]), int(row[self.arc_fc])
            ef = float(self.emission_factors.get(str(m).lower(), 0))
            
            # Scale cost by 1000 to preserve 3 decimal places in integer-only CP-SAT
            # Add a small efficiency penalty to each unit-km to discourage loops
            # This ensures LH -> CS1 -> LH is strictly worse than LH staying at LH
            unit_transport_cost = (uc * dist) + (self.loop_penalty * dist)
            cost_terms.append(x[u, v, m] * int(unit_transport_cost * 1000))
            if self.use_co2 and ef > 0 and lambda_co2 > 0:
                cost_terms.append(x[u, v, m] * int(ef * dist * lambda_co2 * 1000))
            if (u, v, m) in y:
                cost_terms.append(y[u, v, m] * (fc * 1000))

        model.Minimize(sum(cost_terms) if cost_terms else 0)

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = time_limit
        solver.parameters.log_search_progress = True 
        
        status = solver.Solve(model)
        
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            rows = []
            for (u, v, m) in x:
                fv = solver.Value(x[u, v, m])
                if fv > 0:
                    is_open = int(solver.Value(y[u, v, m]))
                    arc_info = self.arc_lookup.get((u, v, m), {})
                    is_export = 1 if v in self.port_nodes else arc_info.get('is_export', 0)
                    ef = float(self.emission_factors.get(str(m).lower(), 0))
                    dist_val = arc_info.get('dist', 1.0)
                    uc_val = arc_info.get('uc', 0.0)
                    fc_val = arc_info.get('fc', 0)

                    row_data = {
                        'From': u, 'To': v, 'Mode': m, 'Flow': int(fv),
                        'Is_Open': is_open, 'Is_Export': is_export,
                        'Cost': (fv * uc_val * dist_val) + (is_open * fc_val)
                    }
                    if self.use_co2:
                        row_data['CO2_Emission'] = round(fv * ef * dist_val / 1000, 4)
                    rows.append(row_data)
                        
            return pd.DataFrame(rows), solver.ObjectiveValue(), y

        return None, 0, None

    def solve_two_stage(self):
        print("\n--- STAGE 1: MIP (Network Design) ---")
        res_mip, obj_mip, y_vars = self.solve()
        if res_mip is None:
            return None, 0
        
        fixed_y = {}
        is_open_map = {}
        if not res_mip.empty:
            unique_res = res_mip.drop_duplicates(subset=['From', 'To', 'Mode'])
            is_open_map = unique_res.set_index(['From', 'To', 'Mode'])['Is_Open'].to_dict()
            
        for (u, v, m), var in y_vars.items():
            val = 1 if is_open_map.get((u, v, m), 0) > 0 else 0
            fixed_y[u, v, m] = val
            
        print("\n--- STAGE 2: LP (Flow Refinement) ---")
        res_lp, obj_lp = self.solve_lp(fixed_y)
        return res_lp, obj_lp

    def solve_lp(self, fixed_y=None):
        solver = pywraplp.Solver.CreateSolver('GLOP')
        if not solver:
            return None, 0

        time_limit = float(self.params.get('TimeLimit', 60))
        solver.SetTimeLimit(int(time_limit * 1000))

        total_s = sum(self.supply_map.values())
        total_d = sum(self.demand_map.values())
        if total_s < total_d:
            return None, 0
            
        x = {}
        out_arcs = {n: [] for n in self.nodes}
        in_arcs = {n: [] for n in self.nodes}

        for _, row in self.arcs.iterrows():
            u, v, m = row[self.arc_from], row[self.arc_to], row[self.arc_mode]
            if str(u).strip() == str(v).strip():
                continue
                
            original_cap = float(row[self.arc_cap])
            if fixed_y is None or fixed_y.get((u, v, m), 0) == 1:
                cap = original_cap
            else:
                cap = 0.0

            x[u, v, m] = solver.NumVar(0.0, cap, f'x_{u}_{v}_{m}')
            out_arcs[u].append((u, v, m))
            in_arcs[v].append((u, v, m))

        for node in self.nodes:
            total_in = sum(x[arc] for arc in in_arcs[node])
            total_out = sum(x[arc] for arc in out_arcs[node])
            supply = float(self.supply_map.get(node, 0))
            demand = float(self.demand_map.get(node, 0))

            if node in self.port_nodes:
                solver.Add(total_in + supply == total_out + demand)
            else:
                if supply > 0 and demand == 0:
                    solver.Add(total_out - total_in <= supply)
                elif demand > 0 and supply == 0:
                    solver.Add(total_in - total_out == demand)
                elif supply > 0 and demand > 0:
                    solver.Add(total_in + supply == total_out + demand)
                else:
                    solver.Add(total_in == total_out)

        # ── Virtual Loop Prevention (k_mode constraints) ──
        all_modes = set(str(m).lower() for (_, _, m) in x)
        for mode_name in all_modes:
            k_param_key = f'k_{mode_name}'
            k_val = self.params.get(k_param_key)
            if mode_name == 'road' and k_val is None:
                k_val = self.k_road
            
            if k_val is not None and float(k_val) < 5.0:
                mode_flow = sum(x[u, v, m] for (u, v, m) in x if str(m).lower() == mode_name)
                real_required_flow = float(total_d)
                solver.Add(mode_flow <= real_required_flow * float(k_val))

        if self.export_demand_total > 0 and self.port_nodes:
            export_inflow = sum(
                sum(x[arc] for arc in in_arcs[port])
                for port in self.port_nodes if port in in_arcs
            )
            solver.Add(export_inflow >= float(self.export_demand_total))

        if self.hub_capacity:
            for hub_node, cap_val in self.hub_capacity.items():
                matched = next((n for n in self.nodes if n.lower().replace('-','').replace(' ','') == hub_node.lower().replace('-','').replace(' ','')), None)
                if matched:
                    hub_inflow = sum(x[u, v, m] for (u, v, m) in x if v == matched)
                    cap_teu = float(cap_val * 1000) if cap_val < 5000 else float(cap_val)
                    solver.Add(hub_inflow <= cap_teu)

        objective = solver.Objective()
        for _, row in self.arcs.iterrows():
            u, v, m = row[self.arc_from], row[self.arc_to], row[self.arc_mode]
            if str(u).strip() == str(v).strip(): continue
            uc = float(row[self.arc_uc])
            dist = float(row[self.arc_dist])
            # Add dynamically scaled efficiency penalty to discourage loops
            objective.SetCoefficient(x[u, v, m], (uc * dist) + (self.loop_penalty * dist))
            
        fixed_cost_sum = 0
        if fixed_y is not None:
            fixed_cost_sum = sum(float(row[self.arc_fc]) for _, row in self.arcs.iterrows() if fixed_y.get((row[self.arc_from], row[self.arc_to], row[self.arc_mode]), 0) == 1)
        
        objective.SetOffset(fixed_cost_sum)
        objective.SetMinimization()

        status = solver.Solve()

        if status == pywraplp.Solver.OPTIMAL or status == pywraplp.Solver.FEASIBLE:
            rows = []
            for (u, v, m) in x:
                fv = x[u, v, m].solution_value()
                
                if fv > 0 or (fixed_y is not None and fixed_y.get((u, v, m), 0) == 1):
                    arc_info = self.arc_lookup.get((u, v, m), {})
                    is_export = 1 if v in self.port_nodes else arc_info.get('is_export', 0)
                    ef = float(self.emission_factors.get(str(m).lower(), 0))
                    dist_val = arc_info.get('dist', 1.0)
                    uc_val = arc_info.get('uc', 0.0)
                    fc_val = arc_info.get('fc', 0)
                    is_open = 1
                    
                    row_data = {
                        'From': u, 'To': v, 'Mode': m, 'Flow': float(fv),
                        'Is_Open': 1, 'Is_Export': is_export,
                        'Cost': (fv * uc_val * dist_val) + (is_open * fc_val)
                    }
                    if self.use_co2:
                        row_data['CO2_Emission'] = round(fv * ef * dist_val / 1000, 4)
                    rows.append(row_data)

            return pd.DataFrame(rows), solver.Objective().Value()
        
        return None, 0
