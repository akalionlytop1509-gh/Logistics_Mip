import re
import math
import pandas as pd
from collections import defaultdict

def clean_node_name(name):
    """
    Remove suffixes like ' - IMPORT', '_EXPORT', etc.
    """
    name = str(name).strip()
    cleaned = re.sub(r'(?i)( - |_| )(IMPORT|EXPORT)$', '', name)
    return cleaned.strip()

def resolve_node_type(node, nodes_info, supply_map, demand_map, port_nodes):
    """
    Resolve display node_type.
    Priority: nodes_info (from Nodes sheet) > inferred from supply/demand/port.
    """
    if node in nodes_info:
        raw = nodes_info[node].get('node_type', 'transship')
        # normalise legacy names
        return {'supply': 'source', 'demand': 'sink', 'hub': 'transship'}.get(raw, raw)
    # fallback inference (backward compat for Test.xlsx without Nodes sheet)
    if node in port_nodes:
        return "port"
    if node in supply_map and node not in demand_map:
        return "source"
    if node in demand_map and node not in supply_map:
        return "sink"
    return "transship"

def calculate_tier_layout(nodes_set, nodes_info, supply_map, demand_map, port_nodes):
    """
    Tier-based Hierarchical Layout (Tier → X axis, node index within tier → Y axis).
    """
    tier_map = {}
    for node in nodes_set:
        if node in nodes_info:
            tier_map[node] = int(nodes_info[node].get('tier', 0))
        else:
            ntype = resolve_node_type(node, nodes_info, supply_map, demand_map, port_nodes)
            tier_map[node] = {'port': 0, 'transship': 1, 'source': 2, 'sink': 2}.get(ntype, 2)

    max_tier = max(tier_map.values(), default=0)
    tier_groups = defaultdict(list)
    for node, tier in tier_map.items():
        tier_groups[tier].append(node)
    for t in tier_groups:
        tier_groups[t] = sorted(tier_groups[t])

    pos = {}
    x_margin = 0.05
    x_range  = 1.0 - x_margin

    for tier, group in tier_groups.items():
        if max_tier == 0:
            x = 1.0
        else:
            x = 1.0 - (tier / max_tier) * x_range

        n = len(group)
        # Slightly larger radius for more horizontal separation
        radius = min(0.3, 0.06 + 0.03 * n)
        
        for i, node in enumerate(group):
            if n == 1:
                y = 0.5
                pos[node] = (x, y)
            elif n == 2:
                # Spread n=2 nodes further apart (0.8 and 0.2)
                y = 0.8 - i * 0.6
                pos[node] = (x, y)
            else:
                angle = math.pi/2 - i * (math.pi / (n - 1))
                # Increase vertical spread from 0.45 to 0.6
                y = 0.5 + 0.6 * math.sin(angle)
                x_node = x - radius * math.cos(angle)
                pos[node] = (x_node, y)

    return pos

def prepare_network_data(results_df, all_arcs_df, supply_map, demand_map, port_nodes, nodes_info):
    """
    Performs visual merging of IMPORT/EXPORT nodes and prepares data for visualization.
    """
    port_nodes  = port_nodes  or set()
    nodes_info  = nodes_info  or {}
    results_df  = results_df  if results_df is not None else pd.DataFrame()

    # Merge Arcs
    all_arcs_merged = all_arcs_df.copy()
    all_arcs_merged['From'] = all_arcs_merged['From'].apply(clean_node_name)
    all_arcs_merged['To'] = all_arcs_merged['To'].apply(clean_node_name)
    all_arcs_merged = all_arcs_merged.drop_duplicates(subset=['From', 'To', 'Mode'])

    # Merge Results
    results_merged = results_df.copy()
    if not results_merged.empty:
        results_merged['From'] = results_merged['From'].apply(clean_node_name)
        results_merged['To'] = results_merged['To'].apply(clean_node_name)
        results_merged = results_merged.groupby(['From', 'To', 'Mode'], as_index=False).agg({'Flow': 'sum'})

    # Merge Maps & Info
    supply_merged = {}
    for k, v in supply_map.items():
        ck = clean_node_name(k)
        supply_merged[ck] = supply_merged.get(ck, 0) + v

    demand_merged = {}
    for k, v in demand_map.items():
        ck = clean_node_name(k)
        demand_merged[ck] = demand_merged.get(ck, 0) + v

    port_nodes_merged = set(clean_node_name(n) for n in port_nodes)

    info_merged = {}
    for k, v in nodes_info.items():
        ck = clean_node_name(k)
        if ck not in info_merged:
            info_merged[ck] = v.copy()
            info_merged[ck]['node_name'] = clean_node_name(v.get('node_name', ck))
        if v.get('node_type') == 'port':
            info_merged[ck]['node_type'] = 'port'

    return results_merged, all_arcs_merged, supply_merged, demand_merged, port_nodes_merged, info_merged
