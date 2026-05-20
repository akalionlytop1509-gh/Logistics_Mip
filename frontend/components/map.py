import math
import pandas as pd
import plotly.graph_objects as go
from collections import defaultdict
import components.network as net

# ── Mode → colour ────────────────────────────────────────────────────────────
MODE_COLOR = {
    "road":      "#868e96",
    "rail":      "#2b8a3e",
    "waterway":  "#e64980",
    "barge":     "#e64980",
    "water":     "#e64980",
    "sea":       "#7950f2",
}

# ── Node style by type (updated terminology) ─────────────────────────────────
NODE_STYLE = {
    "source":    {"color": "#ff6b6b", "symbol": "circle", "label": "Source"},
    "sink":      {"color": "#4dabf7", "symbol": "circle", "label": "Sink"},
    "port":      {"color": "#fab005", "symbol": "square", "label": "Port"},
    "transship": {"color": "#adb5bd", "symbol": "circle", "label": "Transship"},
}
_FALLBACK_STYLE = {"color": "#adb5bd", "symbol": "circle", "label": "Node"}

def build_network_figure(
    results_df,
    all_arcs_df,
    supply_map: dict,
    demand_map: dict,
    port_nodes: set = None,
    nodes_info: dict = None,
    title: str = "Network (solid = used arcs; dashed = closed candidates)",
) -> go.Figure:
    """
    Build a Plotly network figure using Tier-based Hierarchical Layout.
    """
    if all_arcs_df is None or all_arcs_df.empty:
        return None

    # 1. Prepare data using network engine
    results_merged, arcs_merged, supply_merged, demand_merged, port_merged, info_merged = net.prepare_network_data(
        results_df, all_arcs_df, supply_map, demand_map, port_nodes, nodes_info
    )

    # 2. Build node set and Layout
    nodes_set = set(arcs_merged['From'].astype(str)) | set(arcs_merged['To'].astype(str))
    pos = net.calculate_tier_layout(nodes_set, info_merged, supply_merged, demand_merged, port_merged)

    # 3. Active flow map
    active_map = {}
    if not results_merged.empty:
        for _, row in results_merged.iterrows():
            active_map[(str(row['From']), str(row['To']), str(row['Mode']))] = float(row['Flow'] or 0)

    # 4. Create traces
    traces = []

    # Unused arcs trace
    cand_x, cand_y = [], []
    for _, row in arcs_merged.iterrows():
        u, v, m = str(row['From']), str(row['To']), str(row['Mode'])
        if active_map.get((u, v, m), 0) <= 1e-3:
            x0, y0 = pos.get(u, (0, 0))
            x1, y1 = pos.get(v, (0, 0))
            cand_x += [x0, x1, None]
            cand_y += [y0, y1, None]

    if cand_x:
        traces.append(go.Scatter(
            x=cand_x, y=cand_y,
            mode='lines',
            line=dict(color='#dee2e6', width=1, dash='dash'),
            hoverinfo='none',
            showlegend=True,
            name='Closed Candidate'
        ))

    # Active arcs traces
    pair_groups = defaultdict(list)
    active_arcs_list = []
    for _, row in arcs_merged.iterrows():
        u, v, m = str(row['From']), str(row['To']), str(row['Mode'])
        flow = active_map.get((u, v, m), 0)
        if flow > 1e-3:
            pair = tuple(sorted([u, v]))
            pair_groups[pair].append((u, v, m))
            active_arcs_list.append((u, v, m, flow))

    mode_in_legend = set()
    annotations = []
    
    for u, v, m, flow in active_arcs_list:
        color = MODE_COLOR.get(m.lower(), '#868e96')
        x0, y0 = pos.get(u, (0, 0))
        x1, y1 = pos.get(v, (0, 0))
        
        pair = tuple(sorted([u, v]))
        group = pair_groups[pair]
        n_total = len(group)
        idx = group.index((u, v, m))
        
        base_sep = 0.025 
        offset_val = (idx - (n_total - 1) / 2.0) * base_sep
        if u > v: offset_val = -offset_val

        dx, dy = x1 - x0, y1 - y0
        length = math.sqrt(dx**2 + dy**2) or 1
        nx, ny = dy / length, -dx / length
        
        off_x, off_y = offset_val * nx, offset_val * ny
        x0_off, y0_off = x0 + off_x, y0 + off_y
        x1_off, y1_off = x1 + off_x, y1 + off_y
        
        traces.append(go.Scatter(
            x=[x0_off, x1_off, None], y=[y0_off, y1_off, None],
            mode='lines',
            line=dict(color=color, width=2),
            hoverinfo='none',
            name=m,
            legendgroup=m,
            showlegend=(m not in mode_in_legend),
        ))
        mode_in_legend.add(m)
            
        arr_x, arr_y = x0_off + 0.75 * (x1_off - x0_off), y0_off + 0.75 * (y1_off - y0_off)
        traces.append(go.Scatter(
            x=[arr_x], y=[arr_y],
            mode='text',
            text=[f"{flow:,.0f}"], # Fixed number format with comma
            textposition="top center",
            textfont=dict(color='#0f172a', size=11),
            hoverinfo='text',
            hovertext=f"From: {u}<br>To: {v}<br>Mode: {m}<br>Flow: {flow:,.0f}", # Fixed hover
            showlegend=False
        ))
        
        annotations.append(dict(
            ax=x0_off + 0.65 * (x1_off - x0_off), ay=y0_off + 0.65 * (y1_off - y0_off), 
            x=arr_x, y=arr_y,
            xref='x', yref='y', axref='x', ayref='y',
            showarrow=True, arrowhead=2, arrowsize=1.2, arrowwidth=2, arrowcolor=color, standoff=0
        ))

    # Node traces
    type_groups = {}
    for node in nodes_set:
        ntype = net.resolve_node_type(node, info_merged, supply_merged, demand_merged, port_merged)
        type_groups.setdefault(ntype, []).append(node)

    for ntype, group in sorted(type_groups.items()):
        style = NODE_STYLE.get(ntype, _FALLBACK_STYLE)
        node_x = [pos.get(n, (0, 0))[0] for n in group]
        node_y = [pos.get(n, (0, 0))[1] for n in group]
        labels = [info_merged.get(n, {}).get('node_name', n) for n in group]
        
        hover_texts = []
        for n in group:
            inf = info_merged.get(n, {})
            ht = f"<b>{inf.get('node_name', n)}</b><br>Type: {ntype.upper()}"
            if inf.get('tier') is not None: ht += f"<br>Tier: {inf['tier']}"
            if inf.get('design_cap'): ht += f"<br>Design Cap: {inf['design_cap']:,.0f}" # Fixed formatting
            hover_texts.append(ht)

        traces.append(go.Scatter(
            x=node_x, y=node_y,
            mode='markers+text',
            marker=dict(size=30, color=style['color'], symbol=style['symbol'], line=dict(color='#1e293b', width=2)),
            text=labels, textposition="top center", textfont=dict(size=13, color='#0f172a'),
            hoverinfo='text', hovertext=hover_texts, name=style['label'],
        ))

    fig = go.Figure(data=traces)
    fig.update_layout(
        title=dict(text=title, x=0.5, font=dict(size=18, color='#0f172a', family='Inter, sans-serif')),
        showlegend=True, height=900,
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[-0.1, 1.2]),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[-0.2, 1.2]),
        plot_bgcolor='#fafafa', paper_bgcolor='white', margin=dict(l=60, r=60, t=80, b=120),
        legend=dict(orientation="h", yanchor="bottom", y=-0.15, xanchor="center", x=0.5, font=dict(size=13),
                    bgcolor='#f1f5f9', bordercolor='#cbd5e1', borderwidth=1),
        annotations=annotations,
    )
    return fig
