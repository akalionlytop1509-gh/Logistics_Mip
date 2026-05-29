import networkx as nx


def validate_logistics_data(data, optimizer):
    """
    Validate logistics data before solving.
    Returns (is_valid, errors, warnings).
    """
    errors = []
    warnings = []

    total_s = sum(optimizer.supply_map.values())
    total_d = sum(optimizer.demand_map.values())
    if total_s < total_d:
        errors.append(
            f"Total supply ({total_s:,.0f}) is lower than total demand ({total_d:,.0f}). "
            "The model is certainly infeasible."
        )

    G = nx.DiGraph()
    for _, row in optimizer.arcs.iterrows():
        u = str(row[optimizer.arc_from]).strip()
        v = str(row[optimizer.arc_to]).strip()
        G.add_edge(u, v)

    supply_nodes = [n for n, s in optimizer.supply_map.items() if s > 0]
    demand_nodes = [n for n, d in optimizer.demand_map.items() if d > 0]

    for d_node in demand_nodes:
        if d_node not in G:
            errors.append(f"Demand node '{d_node}' does not appear in Arcs.")
            continue

        reachable = any(
            s_node in G and nx.has_path(G, s_node, d_node)
            for s_node in supply_nodes
        )
        if not reachable:
            errors.append(
                f"Demand node '{d_node}' is isolated. No supply node can reach it."
            )

    if (optimizer.arcs[optimizer.arc_uc] < 0).any():
        errors.append("Negative UnitCost found in Arcs.")

    if (optimizer.arcs[optimizer.arc_cap] < 0).any():
        errors.append("Negative Capacity found in Arcs.")

    defined_nodes = {str(node).strip() for node in data.get("nodes_info", {}).keys()}
    if defined_nodes:
        all_arc_nodes = (
            set(optimizer.arcs[optimizer.arc_from].astype(str).str.strip())
            | set(optimizer.arcs[optimizer.arc_to].astype(str).str.strip())
        )
        business_nodes = set(optimizer.supply_map) | set(optimizer.demand_map)

        undefined_arc_nodes = all_arc_nodes - defined_nodes
        if undefined_arc_nodes:
            warnings.append(
                f"{len(undefined_arc_nodes)} nodes appear in Arcs but are missing from Nodes: "
                f"{list(undefined_arc_nodes)[:5]}..."
            )

        undefined_business_nodes = business_nodes - defined_nodes
        if undefined_business_nodes:
            warnings.append(
                f"{len(undefined_business_nodes)} Supply/Demand nodes are missing from Nodes: "
                f"{list(undefined_business_nodes)[:5]}..."
            )

    return len(errors) == 0, errors, warnings
