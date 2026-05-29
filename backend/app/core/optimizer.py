from ortools.linear_solver import pywraplp
from ortools.sat.python import cp_model
import os
import pandas as pd


class HubLogisticsOptimizer:
    def __init__(self, data, k_road=1.0, hub_capacity=None, use_co2=False):
        self.k_road = k_road
        self.use_co2 = use_co2
        self.hub_capacity = hub_capacity or {}
        self.last_flow_breakdown = {}
        self.flow_scale = 1000

        def get_col(df, *aliases):
            low_cols = {c: str(c).lower().strip() for c in df.columns}
            for alias in aliases:
                al = alias.lower().strip()
                exact = next((c for c, lc in low_cols.items() if lc == al), None)
                if exact:
                    return exact
                partial = next((c for c, lc in low_cols.items() if al in lc), None)
                if partial:
                    return partial
            return df.columns[0] if len(df.columns) > 0 else None

        s_df = data['Supply']
        node_s = get_col(s_df, 'IP', 'Source', 'From', 'Node', 'Nguồn')
        val_s = get_col(s_df, 'SupplyValue', 'Supply', 'Cung', 'Value')
        self.supply_map = {
            str(r[node_s]).strip(): float(r[val_s])
            for _, r in s_df.iterrows()
            if pd.notna(r[node_s]) and pd.notna(r[val_s])
        }

        d_df = data['Demand']
        node_d = get_col(d_df, 'DC', 'Destination', 'To', 'Node', 'Đích')
        val_d = get_col(d_df, 'DemandValue', 'Demand', 'Cầu', 'Cau', 'Value')
        self.demand_map = {
            str(r[node_d]).strip(): float(r[val_d])
            for _, r in d_df.iterrows()
            if pd.notna(r[node_d]) and pd.notna(r[val_d])
        }

        arcs_df = data['Arcs'].copy().reset_index(drop=True)
        from_col = get_col(arcs_df, 'From', 'Từ', 'Origin')
        to_col = get_col(arcs_df, 'To', 'Đến', 'Destination')
        mode_col = get_col(arcs_df, 'Mode', 'Phương thức', 'Type', 'Loại')
        cap_col = get_col(arcs_df, 'Cap', 'Capacity', 'Công suất', 'Sức chứa')
        uc_col = get_col(arcs_df, 'UnitCost', 'Chi phí', 'Cost', 'Đơn giá')
        dist_col = get_col(arcs_df, 'Distance', 'Khoảng cách', 'Km', 'Dist')
        fc_col = get_col(arcs_df, 'FixedCost', 'Fixed', 'Phí mở', 'Cố định')
        en_col = get_col(arcs_df, 'Enabled', 'Active', 'Sử dụng')
        isexport_col = get_col(arcs_df, 'IsExport', 'Export', 'Xuất khẩu')

        if en_col and en_col in arcs_df.columns:
            enabled_vals = arcs_df[en_col].dropna()
            if enabled_vals.isin([0, 1, True, False]).all():
                arcs_df = arcs_df[arcs_df[en_col].astype(str).isin(['1', 'True', 'true'])]

        arcs_df = arcs_df.dropna(subset=[from_col, to_col, mode_col])
        arcs_df[from_col] = arcs_df[from_col].astype(str).str.strip()
        arcs_df[to_col] = arcs_df[to_col].astype(str).str.strip()
        arcs_df[mode_col] = arcs_df[mode_col].astype(str).str.strip()
        arcs_df[cap_col] = pd.to_numeric(arcs_df[cap_col], errors='coerce').fillna(1000)
        arcs_df[uc_col] = pd.to_numeric(arcs_df[uc_col], errors='coerce').fillna(0)
        arcs_df[fc_col] = pd.to_numeric(arcs_df[fc_col], errors='coerce').fillna(0)

        if dist_col and dist_col in arcs_df.columns and dist_col not in (from_col, to_col, mode_col):
            arcs_df[dist_col] = pd.to_numeric(arcs_df[dist_col], errors='coerce').fillna(1.0)
        else:
            arcs_df['fallback_dist'] = 1.0
            dist_col = 'fallback_dist'

        if isexport_col and isexport_col in arcs_df.columns and isexport_col not in (from_col, to_col):
            arcs_df[isexport_col] = pd.to_numeric(arcs_df[isexport_col], errors='coerce').fillna(0)
        else:
            arcs_df['IsExport'] = 0
            isexport_col = 'IsExport'

        self.arcs = arcs_df
        self.arc_from = from_col
        self.arc_to = to_col
        self.arc_mode = mode_col
        self.arc_cap = cap_col
        self.arc_uc = uc_col
        self.arc_dist = dist_col
        self.arc_fc = fc_col
        self.arc_isexport = isexport_col

        self.nodes_info = data.get('nodes_info', {})
        self.port_nodes = set(
            arcs_df.loc[arcs_df[isexport_col] == 1, to_col]
            .astype(str).str.strip().unique()
        )
        for nid, info in self.nodes_info.items():
            node_type = str(info.get('node_type', '')).lower().strip()
            tier = pd.to_numeric(info.get('tier'), errors='coerce')
            if node_type == 'port' or (pd.notna(tier) and int(tier) == 0):
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
        raw_export = self._read_export_demand(data, total_s, total_d)
        self.export_demand_total = int(float(raw_export)) if raw_export is not None and not pd.isna(raw_export) else max(0, int(total_s - total_d))

        existing_port_demand = sum(self.demand_map.get(port, 0) for port in self.port_nodes)
        port_demand_shortfall = max(0, self.export_demand_total - existing_port_demand)
        if port_demand_shortfall > 0 and self.port_nodes:
            export_per_port = int(port_demand_shortfall // len(self.port_nodes))
            remainder = int(port_demand_shortfall % len(self.port_nodes))
            for i, port in enumerate(sorted(self.port_nodes)):
                self.demand_map[port] = self.demand_map.get(port, 0) + export_per_port + (1 if i < remainder else 0)

        self.nodes = set(self.arcs[self.arc_from]) | set(self.arcs[self.arc_to])
        self.nodes.update(self.supply_map)
        self.nodes.update(self.demand_map)

        non_zero_costs = self.arcs[self.arc_uc][self.arcs[self.arc_uc] > 0]
        mean_uc = float(non_zero_costs.mean()) if not non_zero_costs.empty else 1.0
        self.loop_penalty = max(1e-4, mean_uc * 0.001)

        self.arc_tuples = []
        for _, row in self.arcs.iterrows():
            u = str(row[self.arc_from]).strip()
            v = str(row[self.arc_to]).strip()
            if u == v:
                continue
            self.arc_tuples.append((
                u,
                v,
                str(row[self.arc_mode]).strip(),
                float(row[self.arc_cap]),
                float(row[self.arc_uc]),
                float(row[self.arc_dist]),
                float(row[self.arc_fc]),
                int(row[self.arc_isexport]),
            ))

        self.arc_lookup = {
            (u, v, m): {'is_export': is_export, 'dist': dist, 'uc': uc, 'fc': fc}
            for u, v, m, _, uc, dist, fc, is_export in self.arc_tuples
        }

        if self.arc_tuples:
            max_cost_coeff = max(uc * dist for (_, _, _, _, uc, dist, _, _) in self.arc_tuples)
            self.cost_scale = 1 if max_cost_coeff == int(max_cost_coeff) else 100
        else:
            self.cost_scale = 1

        self.export_demand_by_port = self._allocate_export_to_ports()
        self.domestic_demand_total = sum(
            demand for node, demand in self.demand_map.items()
            if node not in self.port_nodes
        )

    def _to_mip_flow_units(self, value):
        return int(round(float(value) * self.flow_scale))

    def _read_export_demand(self, data, total_s, total_d):
        parsed_export = data.get('ExportDemand', None)
        if parsed_export is not None and parsed_export > 0:
            return parsed_export
        for k, v in self.params.items():
            k_clean = str(k).lower().replace(' ', '').replace('_', '')
            if k_clean == 'exportdemand':
                return v
        return max(0, total_s - total_d)

    def _allocate_export_to_ports(self):
        if not self.port_nodes or self.export_demand_total <= 0:
            return {}

        ports = sorted(self.port_nodes)
        weights = [max(0.0, float(self.demand_map.get(port, 0))) for port in ports]
        weight_total = sum(weights)
        if weight_total <= 0:
            weights = [1.0 for _ in ports]
            weight_total = float(len(ports))

        raw = [self.export_demand_total * weight / weight_total for weight in weights]
        base = [int(value) for value in raw]
        remainder = int(self.export_demand_total - sum(base))
        fractions = sorted(
            range(len(ports)),
            key=lambda i: raw[i] - base[i],
            reverse=True,
        )
        for i in fractions[:remainder]:
            base[i] += 1
        return {port: float(amount) for port, amount in zip(ports, base)}

    def _classify_node_type(self, node):
        info = self.nodes_info.get(node, {})
        explicit_type = str(info.get('node_type', '')).lower().strip()
        tier = pd.to_numeric(info.get('tier'), errors='coerce')
        if explicit_type == 'transshipment':
            return 'transship'
        if explicit_type in ('source', 'sink', 'port', 'transship'):
            return explicit_type
        if pd.notna(tier) and int(tier) == 0:
            return 'port'
        if node in self.port_nodes:
            return 'port'
        has_supply = self.supply_map.get(node, 0) > 0
        has_demand = self.demand_map.get(node, 0) > 0
        if has_supply and not has_demand:
            return 'source'
        if has_demand and not has_supply:
            return 'sink'
        return 'transship'

    def _is_sink(self, node):
        return self._classify_node_type(node) == 'sink'

    def _mode_limit_value(self, mode_name):
        k_param_key = f'k_{mode_name}'
        k_val = self.params.get(k_param_key)
        if mode_name == 'road' and k_val is None:
            k_val = self.k_road
        return k_val

    def _required_total_flow(self):
        return float(self.domestic_demand_total + self.export_demand_total)

    def _validate_supply_need(self):
        total_supply = sum(self.supply_map.values())
        required = self._required_total_flow()
        if total_supply + 1e-6 < required:
            return False
        port_supply = sum(self.supply_map.get(port, 0) for port in self.port_nodes)
        return port_supply <= self.domestic_demand_total + 1e-6

    def solve(self):
        if not self._validate_supply_need():
            return None, 0, None

        time_limit = float(self.params.get('TimeLimit', 60))
        model = cp_model.CpModel()
        dom, exp, y = {}, {}, {}
        out_arcs = {n: [] for n in self.nodes}
        in_arcs = {n: [] for n in self.nodes}

        for u, v, m, cap, _, _, _, _ in self.arc_tuples:
            key = (u, v, m)
            cap_units = self._to_mip_flow_units(cap)
            dom[key] = model.NewIntVar(0, cap_units, f'dom_{u}_{v}_{m}')
            exp[key] = model.NewIntVar(0, cap_units, f'exp_{u}_{v}_{m}')
            y[key] = model.NewBoolVar(f'y_{u}_{v}_{m}')
            model.Add(dom[key] + exp[key] <= cap_units * y[key])
            out_arcs[u].append(key)
            in_arcs[v].append(key)

        dom_gen, exp_gen = {}, {}
        for node in self.nodes:
            supply = self._to_mip_flow_units(self.supply_map.get(node, 0))
            demand = self._to_mip_flow_units(0 if node in self.port_nodes else self.demand_map.get(node, 0))
            dom_in = sum(dom[arc] for arc in in_arcs[node])
            dom_out = sum(dom[arc] for arc in out_arcs[node])
            exp_in = sum(exp[arc] for arc in in_arcs[node])
            exp_out = sum(exp[arc] for arc in out_arcs[node])

            if node in self.port_nodes:
                port_supply = self._to_mip_flow_units(self.supply_map.get(node, 0))
                port_export = self._to_mip_flow_units(self.export_demand_by_port.get(node, 0))
                model.Add(dom_in == 0)
                model.Add(dom_out == port_supply)
                model.Add(exp_in == port_export)
                model.Add(exp_out == 0)
                continue

            if self._is_sink(node):
                model.Add(dom_in - dom_out == demand)
                model.Add(dom_out == 0)
                model.Add(exp_in == 0)
                model.Add(exp_out == 0)
                continue

            dom_gen[node] = model.NewIntVar(0, supply, f'dom_gen_{node}')
            exp_gen[node] = model.NewIntVar(0, supply, f'exp_gen_{node}')
            model.Add(dom_gen[node] + exp_gen[node] <= supply)
            model.Add(dom_out - dom_in == dom_gen[node] - demand)
            model.Add(exp_out - exp_in == exp_gen[node])

        self._add_mip_side_constraints(model, dom, exp)
        self._set_mip_objective(model, dom, exp, y)

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = time_limit
        solver.parameters.num_workers = 1 if os.getenv('RENDER') == 'true' else 0
        solver.parameters.log_search_progress = False
        status = solver.Solve(model)

        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return self._build_result_rows(
                get_dom=lambda key: float(solver.Value(dom[key])) / self.flow_scale,
                get_exp=lambda key: float(solver.Value(exp[key])) / self.flow_scale,
                get_y=lambda key: int(solver.Value(y[key])),
                objective=solver.ObjectiveValue() / (self.cost_scale * self.flow_scale),
                y_vars=y,
            )
        return None, 0, None

    def _add_mip_side_constraints(self, model, dom, exp):
        required_total_flow = self._to_mip_flow_units(self._required_total_flow())
        all_modes = set(str(m).lower() for (_, _, m) in dom)
        for mode_name in all_modes:
            k_val = self._mode_limit_value(mode_name)
            if k_val is not None and float(k_val) < 5.0:
                mode_flow = sum(
                    dom[key] + exp[key]
                    for key in dom
                    if str(key[2]).lower() == mode_name
                )
                k_pct = int(float(k_val) * 100)
                model.Add(mode_flow * 100 <= required_total_flow * k_pct)

        for hub_node, cap_val in self.hub_capacity.items():
            matched = next((n for n in self.nodes if n.lower().replace('-', '').replace(' ', '') == hub_node.lower().replace('-', '').replace(' ', '')), None)
            if matched:
                hub_inflow = sum(dom[key] + exp[key] for key in dom if key[1] == matched)
                cap_teu = self._to_mip_flow_units(cap_val * 1000 if cap_val < 5000 else cap_val)
                model.Add(hub_inflow <= cap_teu)

        if self.use_co2:
            raw_emax = self.params.get('E_max', None) or self.params.get('Emax', None) or self.params.get('emax', None)
            if raw_emax is not None and not pd.isna(raw_emax):
                ef_terms = []
                for u, v, m, _, _, dist, _, _ in self.arc_tuples:
                    ef = float(self.emission_factors.get(str(m).lower(), 0))
                    if ef > 0:
                        ef_terms.append((dom[u, v, m] + exp[u, v, m]) * int(ef * dist * 100))
                if ef_terms:
                    model.Add(sum(ef_terms) <= int(float(raw_emax) * 1000 * 100 * self.flow_scale))

    def _set_mip_objective(self, model, dom, exp, y):
        lambda_co2 = float(self.params.get('lambdaCO2', 0) or 0) if self.use_co2 else 0.0
        cost_terms = []
        for u, v, m, _, uc, dist, fc, _ in self.arc_tuples:
            key = (u, v, m)
            ef = float(self.emission_factors.get(str(m).lower(), 0))
            unit_transport_cost = (uc * dist) + (self.loop_penalty * dist)
            coeff = int(unit_transport_cost * self.cost_scale)
            cost_terms.append((dom[key] + exp[key]) * coeff)
            if self.use_co2 and ef > 0 and lambda_co2 > 0:
                cost_terms.append((dom[key] + exp[key]) * int(ef * dist * lambda_co2 * self.cost_scale))
            cost_terms.append(y[key] * int(fc * self.cost_scale * self.flow_scale))
        model.Minimize(sum(cost_terms) if cost_terms else 0)

    def solve_two_stage(self):
        print("\n--- STAGE 1: MIP (Network Design) ---")
        res_mip, _, y_vars = self.solve()
        if res_mip is None:
            return None, 0

        fixed_y = {}
        is_open_map = {}
        if not res_mip.empty:
            unique_res = res_mip.drop_duplicates(subset=['From', 'To', 'Mode'])
            is_open_map = unique_res.set_index(['From', 'To', 'Mode'])['Is_Open'].to_dict()
        for key in y_vars:
            fixed_y[key] = 1 if is_open_map.get(key, 0) > 0 else 0

        print("\n--- STAGE 2: LP (Flow Refinement) ---")
        return self.solve_lp(fixed_y)

    def solve_lp(self, fixed_y=None, use_arc_filtering=False):
        if not self._validate_supply_need():
            return None, 0

        solver = pywraplp.Solver.CreateSolver('GLOP')
        if not solver:
            return None, 0
        time_limit = float(self.params.get('TimeLimit', 60))
        solver.SetTimeLimit(int(time_limit * 1000))

        dom, exp = {}, {}
        out_arcs = {n: [] for n in self.nodes}
        in_arcs = {n: [] for n in self.nodes}

        for u, v, m, cap, _, _, _, _ in self.arc_tuples:
            key = (u, v, m)
            cap_val = float(cap) if fixed_y is None or fixed_y.get(key, 0) == 1 else 0.0
            dom[key] = solver.NumVar(0.0, cap_val, f'dom_{u}_{v}_{m}')
            exp[key] = solver.NumVar(0.0, cap_val, f'exp_{u}_{v}_{m}')
            solver.Add(dom[key] + exp[key] <= cap_val)
            out_arcs[u].append(key)
            in_arcs[v].append(key)

        for node in self.nodes:
            supply = float(self.supply_map.get(node, 0))
            demand = float(0 if node in self.port_nodes else self.demand_map.get(node, 0))
            dom_in = sum(dom[arc] for arc in in_arcs[node])
            dom_out = sum(dom[arc] for arc in out_arcs[node])
            exp_in = sum(exp[arc] for arc in in_arcs[node])
            exp_out = sum(exp[arc] for arc in out_arcs[node])

            if node in self.port_nodes:
                solver.Add(dom_in == 0)
                solver.Add(dom_out == float(self.supply_map.get(node, 0)))
                solver.Add(exp_in == float(self.export_demand_by_port.get(node, 0)))
                solver.Add(exp_out == 0)
                continue

            if self._is_sink(node):
                solver.Add(dom_in - dom_out == demand)
                solver.Add(dom_out == 0)
                solver.Add(exp_in == 0)
                solver.Add(exp_out == 0)
                continue

            dom_gen = solver.NumVar(0.0, supply, f'dom_gen_{node}')
            exp_gen = solver.NumVar(0.0, supply, f'exp_gen_{node}')
            solver.Add(dom_gen + exp_gen <= supply)
            solver.Add(dom_out - dom_in == dom_gen - demand)
            solver.Add(exp_out - exp_in == exp_gen)

        self._add_lp_side_constraints(solver, dom, exp)
        objective = solver.Objective()
        self._set_lp_objective(objective, dom, exp, fixed_y)
        objective.SetMinimization()

        status = solver.Solve()
        if status in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
            result, obj, _ = self._build_result_rows(
                get_dom=lambda key: float(dom[key].solution_value()),
                get_exp=lambda key: float(exp[key].solution_value()),
                get_y=lambda key: 1 if fixed_y is None or fixed_y.get(key, 0) == 1 else 0,
                objective=objective.Value(),
                y_vars=None,
            )
            return result, obj
        return None, 0

    def _add_lp_side_constraints(self, solver, dom, exp):
        all_modes = set(str(m).lower() for (_, _, m) in dom)
        required_total_flow = self._required_total_flow()
        for mode_name in all_modes:
            k_val = self._mode_limit_value(mode_name)
            if k_val is not None and float(k_val) < 5.0:
                mode_flow = sum(
                    dom[key] + exp[key]
                    for key in dom
                    if str(key[2]).lower() == mode_name
                )
                solver.Add(mode_flow <= required_total_flow * float(k_val))

        for hub_node, cap_val in self.hub_capacity.items():
            matched = next((n for n in self.nodes if n.lower().replace('-', '').replace(' ', '') == hub_node.lower().replace('-', '').replace(' ', '')), None)
            if matched:
                hub_inflow = sum(dom[key] + exp[key] for key in dom if key[1] == matched)
                cap_teu = float(cap_val * 1000) if cap_val < 5000 else float(cap_val)
                solver.Add(hub_inflow <= cap_teu)

    def _set_lp_objective(self, objective, dom, exp, fixed_y):
        fixed_cost_sum = 0.0
        for u, v, m, _, uc, dist, fc, _ in self.arc_tuples:
            key = (u, v, m)
            coeff = (uc * dist) + (self.loop_penalty * dist)
            objective.SetCoefficient(dom[key], coeff)
            objective.SetCoefficient(exp[key], coeff)
            if fixed_y is not None and fixed_y.get(key, 0) == 1:
                fixed_cost_sum += float(fc)
        objective.SetOffset(fixed_cost_sum)

    def _build_result_rows(self, get_dom, get_exp, get_y, objective, y_vars):
        rows = []
        self.last_flow_breakdown = {}
        for u, v, m, _, uc, dist, fc, _ in self.arc_tuples:
            key = (u, v, m)
            dom_flow = get_dom(key)
            exp_flow = get_exp(key)
            total_flow = dom_flow + exp_flow
            is_open = get_y(key)
            self.last_flow_breakdown[key] = {
                'domestic': dom_flow,
                'export': exp_flow,
                'total': total_flow,
            }
            if total_flow <= 1e-6 and not is_open:
                continue

            ef = float(self.emission_factors.get(str(m).lower(), 0))
            row_data = {
                'From': u,
                'To': v,
                'Mode': m,
                'Flow': int(round(total_flow)) if abs(total_flow - round(total_flow)) <= 1e-6 else float(total_flow),
                'Is_Open': int(is_open),
                'Is_Export': 1 if exp_flow > 1e-6 or v in self.port_nodes else 0,
                'Cost': (total_flow * uc * dist) + (int(is_open) * fc),
                'FixedCost': int(is_open) * fc,
            }
            if self.use_co2:
                row_data['CO2_Emission'] = round(total_flow * ef * dist / 1000, 4)
            rows.append(row_data)

        return pd.DataFrame(rows), objective, y_vars
