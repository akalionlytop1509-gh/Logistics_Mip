# 4_validate_data.py - NEW FILE
# ✅ Toàn diện kiểm tra dữ liệu trước khi solver

import pandas as pd
from typing import Tuple, List

def validate_logistics_data(data: dict) -> Tuple[bool, List[str], List[str]]:
    """
    Comprehensive validation of logistics network data.
    
    Args:
        data: dict with Supply, Demand, Arcs, Cost, Params, ExportDemand, etc.
    
    Returns:
        (is_valid: bool, errors: List[str], warnings: List[str])
    """
    errors = []
    warnings = []

    # ─────────────────────────────────────────────────────────────────────
    # 1. CHECK REQUIRED SHEETS
    # ─────────────────────────────────────────────────────────────────────
    required_sheets = ['Supply', 'Demand', 'Arcs']
    for sheet in required_sheets:
        if sheet not in data or data[sheet] is None:
            errors.append(f"❌ Missing required sheet: {sheet}")
            return False, errors, warnings

    if data['Supply'].empty:
        errors.append("❌ Sheet 'Supply' is empty")
    if data['Demand'].empty:
        errors.append("❌ Sheet 'Demand' is empty")
    if data['Arcs'].empty:
        errors.append("❌ Sheet 'Arcs' is empty")

    if errors:
        return False, errors, warnings

    # ─────────────────────────────────────────────────────────────────────
    # 2. CHECK SUPPLY-DEMAND BALANCE
    # ─────────────────────────────────────────────────────────────────────
    total_supply = float(data.get('TotalSupply', 0))
    total_demand = float(data.get('TotalDemand', 0))
    export_demand = float(data.get('ExportDemand', 0))
    total_need = total_demand + export_demand

    if total_supply == 0:
        errors.append("❌ Total Supply is 0 (check Supply sheet)")
    
    if total_need == 0:
        errors.append("❌ Total Demand + Export is 0 (check Demand sheet & Params)")
    
    if total_supply > 0 and total_need > 0:
        imbalance = total_supply - total_need
        
        if imbalance < 0:
            errors.append(
                f"❌ INFEASIBLE: Supply < Demand + Export\n"
                f"   Supply: {total_supply:,.0f} | Need: {total_need:,.0f} | Short: {abs(imbalance):,.0f}"
            )
        elif imbalance > total_need * 0.5:  # Excess > 50%
            warnings.append(
                f"⚠️  Excess supply > 50%: {imbalance:,.0f} TEU\n"
                f"   Supply: {total_supply:,.0f} | Need: {total_need:,.0f}"
            )

    # ─────────────────────────────────────────────────────────────────────
    # 3. CHECK COLUMN EXISTENCE
    # ─────────────────────────────────────────────────────────────────────
    supply_df = data['Supply']
    demand_df = data['Demand']
    arcs_df = data['Arcs']

    # Helper to find column
    def col_exists(df, *aliases):
        low_cols = [c.lower().strip() for c in df.columns]
        for alias in aliases:
            if alias.lower().strip() in low_cols:
                return True
        return any(alias.lower().strip() in col.lower() for col in df.columns for alias in aliases)

    # Supply columns
    if not col_exists(supply_df, 'IP', 'Source'):
        errors.append("❌ Supply sheet missing 'IP' or 'Source' column")
    if not col_exists(supply_df, 'SupplyValue', 'Supply', 'Cung'):
        errors.append("❌ Supply sheet missing 'SupplyValue' column")

    # Demand columns
    if not col_exists(demand_df, 'DC', 'Destination'):
        errors.append("❌ Demand sheet missing 'DC' column")
    if not col_exists(demand_df, 'DemandValue', 'Demand', 'Cầu'):
        errors.append("❌ Demand sheet missing 'DemandValue' column")

    # Arcs columns
    if not col_exists(arcs_df, 'From'):
        errors.append("❌ Arcs sheet missing 'From' column")
    if not col_exists(arcs_df, 'To'):
        errors.append("❌ Arcs sheet missing 'To' column")
    if not col_exists(arcs_df, 'Mode'):
        errors.append("❌ Arcs sheet missing 'Mode' column")
    if not col_exists(arcs_df, 'UnitCost'):
        errors.append("❌ Arcs sheet missing 'UnitCost' column")
    if not col_exists(arcs_df, 'Cap', 'Capacity'):
        errors.append("❌ Arcs sheet missing 'Cap'/'Capacity' column")

    if errors:
        return False, errors, warnings

    # ─────────────────────────────────────────────────────────────────────
    # 4. CHECK NODE CONNECTIVITY
    # ─────────────────────────────────────────────────────────────────────
    supply_nodes = set(supply_df.iloc[:, 0].astype(str).str.strip().unique())  # First col
    demand_nodes = set(demand_df.iloc[:, 0].astype(str).str.strip().unique())
    arc_from_nodes = set(arcs_df.iloc[:, 0].astype(str).str.strip().unique())  # First col
    arc_to_nodes = set(arcs_df.iloc[:, 1].astype(str).str.strip().unique())    # Second col
    all_arc_nodes = arc_from_nodes | arc_to_nodes

    # Supply nodes not in arcs
    orphan_supply = supply_nodes - all_arc_nodes
    if orphan_supply:
        errors.append(
            f"❌ Supply nodes with no outgoing arc: {orphan_supply}"
        )

    # Demand nodes not in arcs
    orphan_demand = demand_nodes - all_arc_nodes
    if orphan_demand:
        errors.append(
            f"❌ Demand nodes with no incoming arc: {orphan_demand}"
        )

    # ─────────────────────────────────────────────────────────────────────
    # 5. CHECK FOR NEGATIVE COSTS
    # ─────────────────────────────────────────────────────────────────────
    # Find FixedCost column
    fc_col = None
    for c in arcs_df.columns:
        if 'fixedcost' in c.lower() or 'fixed' in c.lower():
            fc_col = c
            break

    if fc_col:
        negative_fc = arcs_df[arcs_df[fc_col] < 0]
        if not negative_fc.empty:
            errors.append(
                f"❌ Negative FixedCost found in {len(negative_fc)} arc(s)"
            )

    # Find UnitCost column
    uc_col = None
    for c in arcs_df.columns:
        if 'unitcost' in c.lower() or 'chi phí' in c.lower():
            uc_col = c
            break

    if uc_col:
        negative_uc = arcs_df[arcs_df[uc_col] < 0]
        if not negative_uc.empty:
            errors.append(
                f"❌ Negative UnitCost found in {len(negative_uc)} arc(s)"
            )

    # ─────────────────────────────────────────────────────────────────────
    # 6. CHECK FOR DUPLICATE ARCS
    # ─────────────────────────────────────────────────────────────────────
    if len(arcs_df) > 0:
        arc_combo = arcs_df.iloc[:, 0].astype(str) + "_" + \
                    arcs_df.iloc[:, 1].astype(str) + "_" + \
                    arcs_df.iloc[:, 2].astype(str)  # From_To_Mode
        duplicates = arc_combo[arc_combo.duplicated()].unique()
        if len(duplicates) > 0:
            warnings.append(
                f"⚠️  Duplicate arcs found (same From-To-Mode): {len(duplicates)}\n"
                f"   First arc will be kept, others ignored"
            )

    # ─────────────────────────────────────────────────────────────────────
    # 7. CHECK EXPORT DEMAND
    # ─────────────────────────────────────────────────────────────────────
    if export_demand == 0:
        warnings.append("ℹ️  ExportDemand = 0 (no export requirements)")

    if export_demand > total_need:
        warnings.append(
            f"⚠️  ExportDemand ({export_demand:,.0f}) > Total Demand ({total_demand:,.0f})\n"
            f"   All demand might be export-focused"
        )

    # ─────────────────────────────────────────────────────────────────────
    # 8. CHECK PARAMS
    # ─────────────────────────────────────────────────────────────────────
    if 'Params' in data and not data['Params'].empty:
        params_df = data['Params']
        
        # Check if critical params exist
        param_names = set(params_df.iloc[:, 0].astype(str).str.lower().str.strip().unique())
        
        if not any(p in param_names for p in ['lambdaco2', 'lambda']):
            warnings.append("ℹ️  'lambdaCO2' param not found - will default to 0")
        
        if not any(p in param_names for p in ['bigm', 'big_m']):
            warnings.append("ℹ️  'BigM' param not found - will use 999999999")
    else:
        warnings.append("ℹ️  'Params' sheet not provided - defaults will be used")

    # ─────────────────────────────────────────────────────────────────────
    # 9. FINAL VERDICT
    # ─────────────────────────────────────────────────────────────────────
    is_valid = len(errors) == 0

    return is_valid, errors, warnings


def print_validation_report(is_valid: bool, errors: List[str], warnings: List[str]):
    """Pretty-print validation results"""
    print("\n" + "="*70)
    print("📋 DATA VALIDATION REPORT")
    print("="*70)

    if is_valid:
        print("✅ ALL CHECKS PASSED - Data is ready for optimization\n")
    else:
        print("❌ VALIDATION FAILED - Please fix errors before proceeding\n")

    if errors:
        print(f"🔴 ERRORS ({len(errors)}):")
        for i, err in enumerate(errors, 1):
            print(f"   {i}. {err}")
        print()

    if warnings:
        print(f"🟡 WARNINGS ({len(warnings)}):")
        for i, warn in enumerate(warnings, 1):
            print(f"   {i}. {warn}")
        print()

    print("="*70 + "\n")

    return is_valid