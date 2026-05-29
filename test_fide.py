import pandas as pd
import sys
import os

# Add backend to path so we can import optimizer
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))
sys.stdout.reconfigure(encoding='utf-8')
from app.core.optimizer import HubLogisticsOptimizer
from app.utils.excel_parser import load_logistics_data

def main():
    file_path = 'data/Fide.xlsx'
    
    try:
        data = load_logistics_data(file_path)
    except Exception as e:
        print(f"Error loading {file_path}: {e}")
        return

    print("Hub capacities:", data.get('HubCapacity', {}))
    print("Demand map raw:", data['Demand'])

    optimizer = HubLogisticsOptimizer(
        data=data,
        k_road=1.0,
        hub_capacity=data.get('HubCapacity', {}),
        use_co2=False
    )
    
    print("\n--- Running MIP+LP (Two Stage) ---")
    res_mip, obj_mip = optimizer.solve_two_stage()
    if res_mip is None:
        print("Model is infeasible or returned None")
    else:
        print(f"LP solved, objective: {obj_mip}")
        ports = optimizer.port_nodes
        port_flows = res_mip[(res_mip['From'].isin(ports)) | (res_mip['To'].isin(ports))]
        print("\nFlows involving ports:")
        print(port_flows.to_string())
        
        for p in ports:
            inflow = res_mip[(res_mip['To'] == p)]['Flow'].sum()
            outflow = res_mip[(res_mip['From'] == p)]['Flow'].sum()
            print(f"Port {p} summary -> Inflow: {inflow}, Outflow: {outflow}")
            
        print("\n--- Mode Flow Analysis ---")
        mode_flows = {}
        arc_analysis = []
        for index, row in res_mip.iterrows():
            m = row['Mode'].lower()
            f = row['Flow']
            c = row['Cost']
            u = row['From']
            v = row['To']
            
            # Find in arc_tuples
            uc, dist, fc = 0, 0, 0
            for tup in optimizer.arc_tuples:
                if tup[0] == u and tup[1] == v and tup[2].lower() == m:
                    uc, dist, fc = tup[4], tup[5], tup[6]
                    break
                    
            if m not in mode_flows:
                mode_flows[m] = {'flow': 0, 'cost': 0}
            mode_flows[m]['flow'] += f
            mode_flows[m]['cost'] += c
            
            if f > 0:
                arc_analysis.append({
                    'Arc': f"{u} -> {v}",
                    'Mode': m,
                    'Flow': f,
                    'VarCost': uc * dist,
                    'FixedCost': fc,
                    'TotalCost': c
                })
        
        total_f = sum(x['flow'] for x in mode_flows.values())
        for m, data in mode_flows.items():
            pct = (data['flow'] / total_f * 100) if total_f > 0 else 0
            print(f"Mode {m}: Flow = {data['flow']} ({pct:.2f}%), Total Cost = {data['cost']}")
            
        print("\n--- Why not Road? (Comparing Unit Costs for some key arcs) ---")
        for item in arc_analysis:
            if item['Mode'] != 'road':
                u, v = item['Arc'].split(' -> ')
                r_uc, r_dist, r_fc = None, None, None
                for tup in optimizer.arc_tuples:
                    if tup[0] == u and tup[1] == v and tup[2].lower() == 'road':
                        r_uc, r_dist, r_fc = tup[4], tup[5], tup[6]
                        break
                if r_uc is not None:
                    print(f"Arc {item['Arc']}: Chosen {item['Mode']} (VarCost={item['VarCost']}, FC={item['FixedCost']}) vs Road (VarCost={r_uc * r_dist}, FC={r_fc})")
    
    print("\n--- Model Setup Info ---")
    print("Supply total:", sum(optimizer.supply_map.values()))
    print("Demand total (Domestic):", optimizer.domestic_demand_total)
    print("Export demand total:", optimizer.export_demand_total)
    print("Port nodes:", optimizer.port_nodes)
    print("Export demand by port:", optimizer.export_demand_by_port)
    
    # Check why '1' is a port
    export_arcs = optimizer.arcs[optimizer.arcs[optimizer.arc_isexport] == 1]
    print("\nArcs with IsExport=1:")
    print(export_arcs[[optimizer.arc_from, optimizer.arc_to, optimizer.arc_isexport]].to_string())
    
    nodes_info = optimizer.nodes_info
    print("\nNode info for '1':", nodes_info.get('1'))


if __name__ == '__main__':
    main()
