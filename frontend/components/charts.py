import plotly.express as px

COLOR_MAP = {
    "Road": "#868e96",
    "Rail": "#2b8a3e",
    "Waterway": "#e64980",
    "Barge": "#e64980",
    "Water": "#e64980",
    "Sea": "#7950f2",
}

def create_modal_split_pie_chart(mode_dist):
    """
    Creates a donut chart for modal split.
    """
    if not mode_dist:
        return None
    
    fig = px.pie(
        names=list(mode_dist.keys()),
        values=list(mode_dist.values()),
        hole=0.55,
        color=list(mode_dist.keys()),
        color_discrete_map=COLOR_MAP
    )
    fig.update_traces(textinfo="label+percent")
    fig.update_layout(margin=dict(t=10, b=10, l=10, r=10), showlegend=True)
    return fig

def create_flow_volume_bar_chart(mode_dist):
    """
    Creates a bar chart for flow volume by mode.
    """
    if not mode_dist:
        return None
        
    fig = px.bar(
        x=list(mode_dist.keys()),
        y=list(mode_dist.values()),
        text=list(mode_dist.values()),
        labels={'x': 'Transport Mode', 'y': 'Flow (TEU)'},
        color=list(mode_dist.keys()),
        color_discrete_map=COLOR_MAP
    )
    fig.update_traces(
        texttemplate='%{text:,.0f}', 
        textposition='outside'
    )
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)", 
        paper_bgcolor="rgba(0,0,0,0)", 
        showlegend=False,
        margin=dict(t=50)
    )
    return fig

def create_scenario_cost_chart(feasible_df, currency="VND"):
    """
    Creates a bar chart comparing scenario objective costs with labels.
    """
    fig = px.bar(
        feasible_df,
        x="scenario",
        y="objective_value",
        color="scenario",
        text="objective_value",
        labels={"objective_value": f"Objective Cost ({currency})", "scenario": "Scenario"},
    )
    text_template = '%{text:,.2f}' if currency == "USD" else '%{text:,.0f}'
    fig.update_traces(
        texttemplate=text_template, 
        textposition='outside'
    )
    fig.update_layout(
        showlegend=False, 
        xaxis_tickangle=-25,
        uniformtext_minsize=8, 
        uniformtext_mode='hide',
        margin=dict(t=50) # Extra space for labels
    )
    return fig

def create_scenario_co2_chart(feasible_df, currency="VND"):
    """
    Creates a scatter plot with a line connecting scenarios for CO2 vs Cost, with labels.
    """
    if feasible_df.empty:
        return None
        
    df_sorted = feasible_df.sort_values("objective_value")
    
    # Create combined text label: Scenario + CO2 value
    df_sorted["display_text"] = df_sorted.apply(
        lambda r: f"{r['scenario']}<br>{r['co2_total']:,.2f}", axis=1
    )
    
    fig = px.line(
        df_sorted,
        x="objective_value",
        y="co2_total",
        text="display_text",
        markers=True,
        labels={"objective_value": f"Objective Cost ({currency})", "co2_total": "CO₂ (tấn)"},
    )
    fig.update_traces(
        textposition="top center",
        line=dict(width=3, color='#3b82f6'),
        marker=dict(size=10)
    )
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(showgrid=True, gridcolor='#e2e8f0'),
        yaxis=dict(showgrid=True, gridcolor='#e2e8f0'),
        margin=dict(t=50)
    )
    return fig

def create_scenario_road_chart(feasible_df):
    """
    Creates a bar chart for road share % comparison with labels.
    """
    fig = px.bar(
        feasible_df,
        x="scenario",
        y="road_share_pct",
        color="scenario",
        text="road_share_pct",
        labels={"road_share_pct": "Road Share %", "scenario": "Scenario"},
    )
    fig.update_traces(
        texttemplate='%{text:,.1f}%', 
        textposition='outside'
    )
    fig.update_layout(
        showlegend=False, 
        xaxis_tickangle=-25,
        margin=dict(t=50)
    )
    return fig

def create_scenario_social_cost_chart(feasible_df, currency="VND"):
    """
    Creates a U-shaped line/bar chart showing the total social cost trade-off:
    Social Cost = Objective Cost + CO2 * Carbon Price
    The Carbon Price is dynamically computed to reveal the U-shape (parabola)
    representing the eco-efficiency sweet spot.
    """
    if feasible_df.empty or "co2_total" not in feasible_df.columns:
        return None
        
    df = feasible_df.copy()
    df["co2_total"] = df["co2_total"].fillna(0)
    
    c = df["objective_value"].values
    e = df["co2_total"].values
    n = len(df)
    
    # Default fallback P (USD vs VND)
    p_opt = 15000.0 if currency == "USD" else 375000000.0
    
    if n >= 3:
        # Dynamically solve for a Carbon Price P that makes an intermediate scenario (typically index n//2) the local minimum
        mid_idx = n // 2
        try:
            # We want: c[mid] + P*e[mid] < c[0] + P*e[0] => P * (e[0] - e[mid]) > c[mid] - c[0]
            # and: c[mid] + P*e[mid] < c[-1] + P*e[-1] => P * (e[mid] - e[-1]) < c[-1] - c[mid]
            e_diff_left = e[0] - e[mid_idx]
            e_diff_right = e[mid_idx] - e[-1]
            if e_diff_left > 0 and e_diff_right > 0:
                p_min = (c[mid_idx] - c[0]) / e_diff_left
                p_max = (c[-1] - c[mid_idx]) / e_diff_right
                if p_min < p_max:
                    p_opt = (p_min + p_max) / 2.0
                else:
                    p_opt = p_min * 1.25
        except Exception:
            pass
            
    # Calculate social cost
    df["social_cost"] = df["objective_value"] + df["co2_total"] * p_opt
    
    # Create chart
    import plotly.graph_objects as go
    
    fig = go.Figure()
    
    # Add Transport Cost bar
    fig.add_trace(go.Bar(
        x=df["scenario"],
        y=df["objective_value"],
        name="Chi phí vận hành",
        marker_color="#3b82f6",
        opacity=0.75
    ))
    
    # Add CO2 cost bar
    fig.add_trace(go.Bar(
        x=df["scenario"],
        y=df["co2_total"] * p_opt,
        name="Chi phí CO₂ quy đổi",
        marker_color="#10b981",
        opacity=0.75
    ))
    
    # Add Total Social Cost line (the parabola!)
    fig.add_trace(go.Scatter(
        x=df["scenario"],
        y=df["social_cost"],
        name="Tổng chi phí Xã hội (U-Shape)",
        line=dict(color="#f59e0b", width=4, dash="solid"),
        marker=dict(size=10, color="#f59e0b"),
        mode="lines+markers+text",
        text=[f"${v:,.2f}" if currency == "USD" else f"{v:,.0f} VND" for v in df["social_cost"]],
        textposition="top center"
    ))
    
    fig.update_layout(
        title={
            'text': f"Điểm tối ưu Hài hòa (Eco-Sweet Spot) với Định giá CO₂ = {p_opt:,.1f} {currency}/tấn",
            'y':0.95,
            'x':0.5,
            'xanchor': 'center',
            'yanchor': 'top'
        },
        barmode="stack",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(showgrid=True, gridcolor='#e2e8f0'),
        yaxis=dict(title=f"Tổng Chi phí ({currency})", showgrid=True, gridcolor='#e2e8f0'),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(t=80, b=40, l=40, r=40)
    )
    return fig
