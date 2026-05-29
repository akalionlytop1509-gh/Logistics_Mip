import sys
import os
import glob
from pathlib import Path

# Enforce UTF-8 for Windows stdout before anything else
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

import streamlit as st
import pandas as pd
import plotly.express as px

# Import frontend components
import api_client
import scenario_manager

import components.map as viz_map
import components.charts as viz_charts

def highlight_export_lh(row):
    try:
        from_node = str(row.get('From', '')).upper()
        to_node = str(row.get('To', '')).upper()
        is_lh = ('LẠCH HUYỆN' in from_node) or ('LH' in from_node) or ('LẠCH HUYỆN' in to_node) or ('LH' in to_node)
        is_export = bool(row.get('Is_Export', 0))
        if is_lh and is_export:
            return ['background-color: rgba(59, 130, 246, 0.15)'] * len(row)
    except Exception:
        pass
    return [''] * len(row)

# ── Inline theme (avoids package import issue entirely)
def _get_css():
    return """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [data-testid="stAppViewContainer"], .stText, .stMarkdown {
    font-family: 'Inter', sans-serif;
}

h1, h2, h3, h4, [data-testid="stMetricValue"], [data-testid="stMetricLabel"] {
    font-family: 'Inter', sans-serif !important;
    font-weight: 700 !important;
}

div[data-testid="stMetric"] {
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 1rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}

.stDataFrame thead tr th {
    font-weight: 600 !important;
    font-size: 12px !important;
}

.stTabs [data-baseweb="tab-list"] { gap: 8px; }
.stTabs [aria-selected="true"] {
    border-bottom: 2px solid #3b82f6 !important;
    font-weight: 600 !important;
}

#MainMenu {visibility: hidden;}
header {visibility: hidden;}
footer {visibility: hidden;}
.stDeployButton {display:none;}

/* ── Ghim Sidebar: ẩn nút collapse (mũi tên thu gọn) ── */
[data-testid="collapsedControl"] {
    display: none !important;
}
button[kind="header"][data-testid="baseButton-header"],
[data-testid="stSidebarCollapseButton"] {
    display: none !important;
}
/* Đảm bảo sidebar luôn hiển thị với độ rộng cố định */
[data-testid="stSidebar"] {
    min-width: 280px !important;
    max-width: 380px !important;
}
/* Ẩn nút collapse bên trong sidebar (mũi tên <) */
[data-testid="stSidebarCollapseButton"] {
    display: none !important;
}
/* Ẩn nút re-open khi sidebar đã đóng (mũi tên >) */
[data-testid="collapsedControl"] {
    display: none !important;
}
</style>
"""

# ── Page configuration
st.set_page_config(
    page_title="Pro Hub — Logistics Optimizer",
    page_icon="🚚",
    layout="wide",
    initial_sidebar_state="expanded"
)
st.markdown(_get_css(), unsafe_allow_html=True)

# ── Force sidebar luôn mở bằng JavaScript ──────────────────────────────────
import streamlit.components.v1 as components
components.html("""
<script>
(function() {
    function forceOpenSidebar() {
        // Tìm nút "collapsed control" (mũi tên > để mở lại sidebar)
        var collapsedBtn = window.parent.document.querySelector('[data-testid="collapsedControl"] button');
        if (!collapsedBtn) {
            collapsedBtn = window.parent.document.querySelector('[data-testid="collapsedControl"]');
        }
        if (collapsedBtn) {
            collapsedBtn.click();
        }

        // Ẩn nút collapse bên trong sidebar
        var collapseBtn = window.parent.document.querySelector('[data-testid="stSidebarCollapseButton"]');
        if (collapseBtn) {
            collapseBtn.style.setProperty('display', 'none', 'important');
        }

        // Ẩn luôn vùng collapsedControl
        var collapsedArea = window.parent.document.querySelector('[data-testid="collapsedControl"]');
        if (collapsedArea) {
            collapsedArea.style.setProperty('display', 'none', 'important');
        }
    }

    // Chạy ngay khi load
    forceOpenSidebar();

    // Theo dõi DOM changes để xử lý khi Streamlit re-render
    var observer = new MutationObserver(function(mutations) {
        forceOpenSidebar();
    });
    observer.observe(window.parent.document.body, {
        childList: true,
        subtree: true,
        attributes: true,
        attributeFilter: ['aria-expanded']
    });
})();
</script>
""", height=0)

# ─────────────────────────────────────────────────────────────────────────────
# CURRENCY AUTO-DETECTION
# ─────────────────────────────────────────────────────────────────────────────
import io

# On Streamlit Cloud, the app runs from the repo root or frontend/
# Use parent.parent for local dev, but check if data/ exists
_candidate_root = Path(__file__).parent.parent
if (_candidate_root / "data").exists():
    root_path = _candidate_root
else:
    root_path = Path(__file__).parent  # Fallback for cloud

if "detected_currency" not in st.session_state:
    st.session_state["detected_currency"] = "VND"
if "last_file_id" not in st.session_state:
    st.session_state["last_file_id"] = None

early_file_bytes = None
early_file_id = None

uploaded_file_val = st.session_state.get("sidebar_uploaded_file")
selected_file_val = st.session_state.get("sidebar_selected_file", "-- None --")

if uploaded_file_val:
    early_file_bytes = uploaded_file_val.getvalue()
    early_file_id = uploaded_file_val.name
elif selected_file_val != "-- None --":
    file_path = root_path / selected_file_val
    if file_path.exists():
        try:
            with open(file_path, "rb") as f:
                early_file_bytes = f.read()
            early_file_id = selected_file_val
        except Exception:
            pass

if early_file_bytes and early_file_id != st.session_state.get("last_file_id"):
    has_usd = False
    try:
        xls = pd.ExcelFile(io.BytesIO(early_file_bytes))
        arcs_s = next((s for s in xls.sheet_names if s.strip().lower() in ['arcs', 'arcs (mip)', 'arcs (lp)', 'cung đường']), None)
        if arcs_s:
            df_header = pd.read_excel(xls, sheet_name=arcs_s, nrows=0)
            if any('usd' in str(c).lower() or '$' in str(c) for c in df_header.columns):
                has_usd = True
                
        if not has_usd:
            params_s = next((s for s in xls.sheet_names if s.strip().lower() in ['params', 'parameters', 'tham số']), None)
            if params_s:
                df_params = pd.read_excel(xls, sheet_name=params_s)
                for col in df_params.columns:
                    if df_params[col].astype(str).str.contains('usd|USD|\\$', regex=True).any():
                        has_usd = True
                        break
    except Exception:
        pass
    
    st.session_state["detected_currency"] = "USD" if has_usd else "VND"
    st.session_state["last_file_id"] = early_file_id
    st.session_state["manual_currency"] = st.session_state["detected_currency"]

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🚚 **Pro Hub**")
    st.caption("Enterprise Logistics Optimizer")
    st.divider()

    # Data Source
    st.markdown("#### 📂 Data Source")
    data_dir = root_path / "data"
    local_files = glob.glob(str(data_dir / "*.xlsx"))
    local_basenames = [os.path.relpath(f, str(root_path)) for f in local_files]
    selected_basename = st.selectbox("Select File", ["-- None --"] + local_basenames, key="sidebar_selected_file")
    uploaded_file = st.file_uploader("Upload", type=["xlsx"], key="sidebar_uploaded_file")

    st.divider()

    # Currency selection (Auto-detected)
    currency = st.session_state.get("detected_currency", "VND")
    st.session_state["manual_currency"] = currency

    st.divider()

    # Sensitivity Analysis
    st.markdown("#### Sensitivity Analysis")
    max_road_pct = st.slider(
        "K_road",
        min_value=0, max_value=100, value=100, step=5,
        format="%d%%",
        help=(
            "Max % of total flow that can use road transport.\n\n"
            "100% = Inf (road fully open, model chooses freely).\n"
            "50% = at least 50% must use Rail/Sea/Barge.\n"
            "0% = road completely banned, only other modes."
        )
    )
    # Convert % → multiplier for the model: 100% → 1.0, 0% → 0.0
    k_road = max_road_pct / 100.0

    st.caption(f"Road <= {max_road_pct}% of total flow")

    # ── CO2 / Green Logistics ────────────────────────────────────────────────
    st.markdown("#### 🌿 Green Logistics (CO₂)")
    use_co2 = st.toggle(
        "Bật tính toán CO₂",
        value=False,
        help=(
            "Khi bật: đưa phát thải CO₂ vào hàm mục tiêu (λ·Σ E_m·d·x) "
            "và áp ràng buộc E_max nếu có.\n\n"
            "λ và E_max được đọc từ sheet Params trong file Excel đầu vào."
        )
    )
    if use_co2:
        st.caption("λ và E\_max lấy từ sheet **Params** trong Excel.")
        st.caption("📌 EF của từng mode lấy từ sheet **Params** (ví dụ: Key `EF_road`, `EF_rail`, đơn vị kg/TEU.km).")

    st.divider()

    # Solver Settings
    st.markdown("#### ⚙️ Solver Strategy")
    solve_mode = st.radio(
        "Mode",
        options=["MIP", "LP"],
        index=0,
    )

    st.divider()

    # Hub Capacity Scenario
    st.markdown("#### 🏭 Hub Constraint")
    scenario = st.radio(
        "Kịch bản",
        options=["Không giới hạn Hub", "Giới hạn Hub Capacity"],
        index=0,
        help="Áp dụng ràng buộc công suất hub từ sheet 'Nodes' trong Excel."
    )
    use_hub_capacity = scenario.startswith("Giới hạn")

# ─────────────────────────────────────────────────────────────────────────────
# MAIN AREA
# ─────────────────────────────────────────────────────────────────────────────
st.title("Pro Hub Logistics Optimizer")
st.markdown("##### Strategic Multimodal Network Optimization Pipeline")

# Determine file to load
file_to_use = None
file_bytes = None

if uploaded_file:
    file_bytes = uploaded_file.getvalue()
elif selected_basename != "-- None --":
    file_path = str(root_path / selected_basename)
    try:
        with open(file_path, "rb") as f:
            file_bytes = f.read()
    except Exception as e:
        st.error(f"Failed to read local file: {e}")

if not file_bytes:
    st.info("📂 **Action Required**: Please select or upload an Excel data source in the sidebar.")
    st.stop()

# ── Solve using Backend API
with st.spinner("Running Optimization Pipeline via Backend..."):
    try:
        response = api_client.optimize_network(
            file_bytes=file_bytes,
            k_road=k_road,
            use_co2=use_co2,
            solve_mode=solve_mode,
            use_hub_capacity=use_hub_capacity
        )
    except Exception as e:
        st.error(f"❌ Backend API Error: {e}")
        st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# RESULTS
# ─────────────────────────────────────────────────────────────────────────────
current_infeasible = response.get("status") == "infeasible" or not response.get("results_flow")
if current_infeasible:
    msg = response.get("message", "No solution found. Check that total supply >= domestic demand + export demand.")
    st.error(f"❌ **Infeasible**: {msg}")

# Success banner
scenario_label = "Kịch bản 2" if use_hub_capacity else "Kịch bản 1"
obj_val = response.get("objective_value", 0)
co2_total = response.get("co2_total", None)
co2_label = f" | CO₂: {co2_total:,} tấn" if (use_co2 and co2_total is not None) else ""

# ── Define currency formatters
if currency == "USD":
    curr_symbol = "USD"
    curr_format = lambda x: f"${x:,.2f}" if isinstance(x, (int, float)) and pd.notna(x) else x
    curr_col_name = "Total Cost (USD)"
else:
    curr_symbol = "VND"
    curr_format = lambda x: f"{x:,.0f} VND" if isinstance(x, (int, float)) and pd.notna(x) else x
    curr_col_name = "Total Cost (VND)"

if not current_infeasible:
    st.success(f"✅ **Optimal Solution Found** — Objective: {curr_format(obj_val)} | Strategy: {solve_mode} | {scenario_label}{co2_label}")

# Cảnh báo khi bật CO2 nhưng file Excel thiếu cột EmissionFactor
if use_co2 and (co2_total is None or co2_total == 0):
    st.warning(
        "⚠️ **CO₂ bật nhưng tất cả giá trị bằng 0.** "
        "Kiểm tra sheet **Params** trong Excel: cần có các Key `EF_road`, `EF_rail`, `EF_sea`... (kg CO₂/TEU.km) "
        "cho mỗi Mode. "
        "Sheet **Params** cũng cần có key `lambdaCO2`."
    )

metrics = response.get("metrics", {})
mode_dist = metrics.get("Mode_Distribution", {})
results_df = pd.DataFrame(response.get("results_flow", []))
network_data = response.get("network_data", {})

supply_map = network_data.get("supply_map", {})
demand_map = network_data.get("demand_map", {})
port_nodes = set(network_data.get("port_nodes", []))
export_demand_total = network_data.get("export_demand_total", 0)
nodes = set(network_data.get("nodes", []))
all_arcs_df = pd.DataFrame(network_data.get("all_arcs", []))

# ── KPI Cards (native Streamlit metrics)
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("Total Supply", f"{sum(supply_map.values()):,.0f} TEU")
with c2:
    st.metric("Total Demand", f"{sum(demand_map.values()):,.0f} TEU", help="Incl. Export")
with c3:
    st.metric("Objective Cost", curr_format(obj_val))
with c4:
    active_routes = len(results_df[results_df['Flow'] > 0]) if not results_df.empty else 0
    st.metric("Active Routes", f"{active_routes}", f"of {len(all_arcs_df)} candidates")

st.markdown("")  # spacer

# ── Main Tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📈 Network Flow", "📊 Node Analysis", "📋 Detailed Flow", "📥 Input Data", "🔄 Scenario Comparison"])

# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 — NETWORK FLOW
# ─────────────────────────────────────────────────────────────────────────────
with tab1:
    @st.fragment
    def render_network_tab_content():
        st.subheader("Optimized Logistics Network (Solid=Used, Dashed=Candidate)")
        show_candidate_arcs = st.toggle("Hiển thị lưới tuyến ứng viên (Candidate Arcs)", value=False)

        # 🌿 Summary CO2 (Always show if co2_total exists)
        if co2_total is not None:
            st.info(f"🌿 **Tổng phát thải CO₂**: {co2_total:,} tấn")

        fig = viz_map.build_network_figure(
            results_df,
            all_arcs_df,
            supply_map,
            demand_map,
            port_nodes,
            nodes_info=network_data.get("nodes_info", {}),
            show_candidate_arcs=show_candidate_arcs
        )

        if fig:
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("Could not generate network diagram.")

        st.divider()
        st.markdown("#### Flow Allocation Results")
        if not results_df.empty:
            active_flows = results_df[results_df['Flow'] > 0].copy()
            
            format_dict = {
                "Flow": lambda x: f"{x:,.1f}".rstrip('0').rstrip('.') if '.' in f"{x:,.1f}" else f"{x:,.0f}" if isinstance(x, (int, float)) else x,
            }
            if currency == "USD":
                format_dict["Cost"] = lambda x: f"${x:,.2f}" if isinstance(x, (int, float)) and pd.notna(x) else x
                format_dict["FixedCost"] = lambda x: f"${x:,.2f}" if isinstance(x, (int, float)) and pd.notna(x) else x
            else:
                format_dict["Cost"] = lambda x: f"{x:,.0f} VND" if isinstance(x, (int, float)) and pd.notna(x) else x
                format_dict["FixedCost"] = lambda x: f"{x:,.0f} VND" if isinstance(x, (int, float)) and pd.notna(x) else x
                
            if "CO2_Emission" in active_flows.columns:
                format_dict["CO2_Emission"] = lambda x: f"{x:,.4f}" if isinstance(x, (int, float)) and pd.notna(x) else x
                
            styled_flows = active_flows.style.apply(highlight_export_lh, axis=1).format(format_dict)
            
            col_cfg_tab1 = {
                "Flow":      st.column_config.Column("Flow (TEU)"),
                "Mode":      st.column_config.TextColumn("Mode"),
                "Is_Export": st.column_config.CheckboxColumn("Export?"),
                "Is_Open":   st.column_config.CheckboxColumn("Open?"),
                "Cost":      st.column_config.Column(curr_col_name),
                "FixedCost": st.column_config.Column(f"Fixed Cost ({currency})"),
            }
            if "CO2_Emission" in active_flows.columns:
                col_cfg_tab1["CO2_Emission"] = st.column_config.Column("CO₂ (tấn)")
                
            st.dataframe(
                styled_flows,
                use_container_width=True,
                column_config=col_cfg_tab1,
                hide_index=True
            )
            
    render_network_tab_content()

# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 — NODE ANALYSIS (NEW & IMPROVED)
# ─────────────────────────────────────────────────────────────────────────────
with tab2:
    st.markdown("#### ⚖️ Node Balance & Capacity Analysis")
    node_balance = response.get("node_balance", [])

    if node_balance:
        bal_df = pd.DataFrame(node_balance)
        def clean_format(x):
            if not isinstance(x, (int, float)) or pd.isna(x): return x
            return f"{x:,.10f}".rstrip('0').rstrip('.') if '.' in f"{x:,.10f}" else f"{x:,.0f}"

        # Rename columns for display
        st.dataframe(
            bal_df.style.format(clean_format),
            use_container_width=True,
            column_config={
                "node_name":  "Node Name",
                "node_type":  "Type",
                "tier":       "Tier",
                "supply":     "Supply (TEU)",
                "demand":     "Demand (TEU)",
                "inflow":     "Inflow (TEU)",
                "outflow":    "Outflow (TEU)",
                "balance":    "Net Balance",
                "design_cap": "Design Cap",
            },
            hide_index=True
        )
    else:
        st.info("No node balance data available.")

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### 🥧 Modal Split")
        fig_pie = viz_charts.create_modal_split_pie_chart(mode_dist)
        if fig_pie:
            st.plotly_chart(fig_pie, use_container_width=True)

    with col2:
        st.markdown("#### 📦 Flow Volume by Mode")
        fig_bar = viz_charts.create_flow_volume_bar_chart(mode_dist)
        if fig_bar:
            st.plotly_chart(fig_bar, use_container_width=True)

# ─────────────────────────────────────────────────────────────────────────────
# TAB 3 — DETAILED RESULTS
# ─────────────────────────────────────────────────────────────────────────────
with tab3:
    st.markdown("#### Flow Allocation Table")
    if not results_df.empty:
        active_tab3 = results_df[results_df['Flow'] > 0].copy()
        
        format_dict_tab3 = {
            "Flow": lambda x: f"{x:,.1f}".rstrip('0').rstrip('.') if '.' in f"{x:,.1f}" else f"{x:,.0f}" if isinstance(x, (int, float)) else x,
        }
        if currency == "USD":
            format_dict_tab3["Cost"] = lambda x: f"${x:,.2f}" if isinstance(x, (int, float)) and pd.notna(x) else x
            format_dict_tab3["FixedCost"] = lambda x: f"${x:,.2f}" if isinstance(x, (int, float)) and pd.notna(x) else x
        else:
            format_dict_tab3["Cost"] = lambda x: f"{x:,.0f} VND" if isinstance(x, (int, float)) and pd.notna(x) else x
            format_dict_tab3["FixedCost"] = lambda x: f"{x:,.0f} VND" if isinstance(x, (int, float)) and pd.notna(x) else x
            
        styled_tab3 = active_tab3.style.apply(highlight_export_lh, axis=1).format(format_dict_tab3)
        
        col_cfg_tab3 = {
            "Flow": st.column_config.Column("Flow (TEU)"),
            "Is_Export": st.column_config.CheckboxColumn("Export Route?"),
            "Is_Open": st.column_config.CheckboxColumn("Arc Open?"),
            "Mode": st.column_config.TextColumn("Mode 🚛"),
            "Cost": st.column_config.Column(curr_col_name),
            "FixedCost": st.column_config.Column(f"Fixed Cost ({currency})"),
        }
            
        st.dataframe(
            styled_tab3,
            use_container_width=True,
            column_config=col_cfg_tab3,
            hide_index=True
        )
        csv = results_df.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Download Results (CSV)", csv,
                           "optimization_results.csv", "text/csv", key="download_csv")

# ─────────────────────────────────────────────────────────────────────────────
# TAB 4 — INPUT DATA
# ─────────────────────────────────────────────────────────────────────────────
with tab4:
    try:
        import io
        xls = pd.ExcelFile(io.BytesIO(file_bytes))
        for sheet_name in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=sheet_name)
            if not df.empty:
                with st.expander(f"📄 Sheet: **{sheet_name}**  ({len(df)} rows)"):
                    st.dataframe(df, use_container_width=True, hide_index=True)
    except Exception as e:
        st.warning(f"Could not load input data preview: {e}")

with tab5:
    st.markdown("#### Scenario Comparison")
    st.caption("Run standard scenarios against the same Excel data and current solver mode.")

    if st.button("▶ Run Scenario Comparison", type="primary"):
        scenario_rows = []
        scenario_flows_dict = {}
        errors = []
        progress = st.progress(0)

        for idx, scenario_cfg in enumerate(scenario_manager.SCENARIOS, start=1):
            try:
                # ALL params come strictly from scenario_manager.SCENARIOS config
                scenario_response = api_client.optimize_network(
                    file_bytes=file_bytes,
                    k_road=scenario_cfg["k_road"],
                    solve_mode=scenario_cfg.get("solver_strategy", "MIP"),
                    use_hub_capacity=scenario_cfg["use_hub_capacity"],
                    use_co2=scenario_cfg["use_co2"],
                )
                scenario_rows.append(
                    scenario_manager.summarize_scenario_result(
                        scenario_cfg["name"],
                        scenario_response,
                        k_road=scenario_cfg["k_road"],
                        solver_strategy=scenario_cfg.get("solver_strategy", "MIP"),
                    )
                )
                scenario_flows_dict[scenario_cfg["name"]] = scenario_response.get("results_flow", [])
            except Exception as e:
                errors.append(f"{scenario_cfg['name']}: {e}")
                scenario_rows.append(
                    scenario_manager.summarize_scenario_result(
                        scenario_cfg["name"],
                        {
                            "status": "error",
                            "message": str(e),
                            "objective_value": 0,
                            "metrics": {},
                            "results_flow": [],
                        },
                        k_road=scenario_cfg["k_road"],
                        solver_strategy=scenario_cfg.get("solver_strategy", "MIP"),
                    )
                )
                scenario_flows_dict[scenario_cfg["name"]] = []
            progress.progress(idx / len(scenario_manager.SCENARIOS))

        st.session_state["scenario_comparison_rows"] = scenario_rows
        st.session_state["scenario_comparison_errors"] = errors
        st.session_state["scenario_comparison_flows"] = scenario_flows_dict

    scenario_rows = st.session_state.get("scenario_comparison_rows", [])
    scenario_errors = st.session_state.get("scenario_comparison_errors", [])
    scenario_flows_dict = st.session_state.get("scenario_comparison_flows", {})

    if scenario_errors:
        with st.expander("Scenario run warnings"):
            for err in scenario_errors:
                st.warning(err)

    if scenario_rows:
        scenario_df = pd.DataFrame(scenario_rows)
        display_df = scenario_df.copy()
        display_df["co2_total"] = display_df["co2_total"].fillna(0)

        format_dict_scenarios = {
            "k_road_limit": lambda x: f"{x*100:,.1f}%" if isinstance(x, (int, float)) and pd.notna(x) else x,
            "road_share_pct": lambda x: f"{x:,.1f}%" if isinstance(x, (int, float)) and pd.notna(x) else x,
            "total_flow": lambda x: f"{x:,.0f}" if isinstance(x, (int, float)) and pd.notna(x) else x,
            "active_routes": lambda x: f"{x:,.0f}" if isinstance(x, (int, float)) and pd.notna(x) else x,
            "road_flow": lambda x: f"{x:,.0f}" if isinstance(x, (int, float)) and pd.notna(x) else x,
            "export_flow": lambda x: f"{x:,.0f}" if isinstance(x, (int, float)) and pd.notna(x) else x,
            "domestic_flow": lambda x: f"{x:,.0f}" if isinstance(x, (int, float)) and pd.notna(x) else x,
            "co2_total": lambda x: f"{x:,.2f}" if isinstance(x, (int, float)) and pd.notna(x) else x,
        }
        if currency == "USD":
            format_dict_scenarios["objective_value"] = lambda x: f"${x:,.2f}" if isinstance(x, (int, float)) and pd.notna(x) else x
        else:
            format_dict_scenarios["objective_value"] = lambda x: f"{x:,.0f} VND" if isinstance(x, (int, float)) and pd.notna(x) else x

        st.dataframe(
            display_df.style.format(format_dict_scenarios, na_rep=""),
            use_container_width=True,
            hide_index=True,
            column_config={
                "scenario": st.column_config.TextColumn("Scenario"),
                "status": st.column_config.TextColumn("Status"),
                "k_road_limit": "K-road Kịch bản",
                "objective_value": f"Objective Cost ({currency})",
                "co2_total": "CO₂ (tấn)",
                "total_flow": "Total Flow (TEU)",
                "active_routes": "Active Routes",
                "road_flow": "Road Flow",
                "road_share_pct": "Tỷ lệ Đường bộ (Thực tế)",
                "export_flow": "Export Flow",
                "domestic_flow": "Domestic Flow",
                "message": st.column_config.TextColumn("Message"),
            },
        )

        feasible_df = display_df[display_df["status"] == "optimal"].copy()
        if not feasible_df.empty:
            col_a, col_b = st.columns(2)
            with col_a:
                fig_cost = viz_charts.create_scenario_cost_chart(feasible_df, currency=currency)
                st.plotly_chart(fig_cost, use_container_width=True)

            with col_b:
                has_co2 = feasible_df["co2_total"].fillna(0).sum() > 0
                if has_co2:
                    fig_co2 = viz_charts.create_scenario_co2_chart(feasible_df, currency=currency)
                    st.plotly_chart(fig_co2, use_container_width=True)
                else:
                    fig_road = viz_charts.create_scenario_road_chart(feasible_df)
                    st.plotly_chart(fig_road, use_container_width=True)

            if has_co2:
                st.write("")
                st.markdown("### 🌿 Điểm Hài Hòa Tối Ưu (Eco-Efficiency Sweet Spot)")
                st.caption(
                    "Biểu đồ phân tích điểm hài hòa tối ưu giữa Chi phí Vận hành (Transport Cost) và Phát thải CO₂. "
                    "Bằng cách áp dụng đơn giá khí thải CO₂ quy đổi (Carbon Price), chúng ta tìm ra kịch bản "
                    "có Tổng chi phí Xã hội (Social Cost) thấp nhất làm điểm đáy của hình Parabol."
                )
                fig_social = viz_charts.create_scenario_social_cost_chart(feasible_df, currency=currency)
                if fig_social:
                    st.plotly_chart(fig_social, use_container_width=True)

            modal_cols = ["scenario", "road_flow", "rail_flow", "water_flow"]
            st.markdown("#### Modal Split Summary")
            
            format_dict_modal = {
                "road_flow": lambda x: f"{x:,.0f}" if isinstance(x, (int, float)) and pd.notna(x) else x,
                "rail_flow": lambda x: f"{x:,.0f}" if isinstance(x, (int, float)) and pd.notna(x) else x,
                "water_flow": lambda x: f"{x:,.0f}" if isinstance(x, (int, float)) and pd.notna(x) else x,
            }

            st.dataframe(
                display_df[modal_cols].style.format(format_dict_modal),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "scenario": "Scenario",
                    "road_flow": "Road",
                    "rail_flow": "Rail",
                    "water_flow": "Sea/Barge/Waterway",
                },
            )

            # Phân vùng xuất báo cáo Scenario Comparison
            st.divider()
            st.markdown("### 📥 Xuất Báo Cáo So Sánh (Export Report)")
            st.caption("Tải xuống báo cáo phân tích so sánh đa trang Excel (.xlsx) có biểu đồ trực quan hoặc tệp CSV (.csv) tiện lợi.")
            
            btn_col1, btn_col2 = st.columns(2)
            with btn_col1:
                try:
                    from utils.export import generate_scenario_excel
                    excel_bytes = generate_scenario_excel(display_df, scenario_flows_dict, currency=currency)
                    st.download_button(
                        label="📊 Tải Báo cáo Excel đầy đủ (.xlsx)",
                        data=excel_bytes,
                        file_name="Logistics_Scenario_Comparison_Report.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="download_excel_scenarios",
                        use_container_width=True
                    )
                except Exception as ex:
                    st.error(f"Lỗi tạo file Excel: {ex}")
            with btn_col2:
                try:
                    csv_data = display_df.to_csv(index=False).encode("utf-8")
                    st.download_button(
                        label="📄 Tải Bảng tổng quan CSV (.csv)",
                        data=csv_data,
                        file_name="Logistics_Scenario_Comparison_Summary.csv",
                        mime="text/csv",
                        key="download_csv_scenarios",
                        use_container_width=True
                    )
                except Exception as ex:
                    st.error(f"Lỗi tạo file CSV: {ex}")
    else:
        st.info("Click the button above to run the six standard scenarios.")
