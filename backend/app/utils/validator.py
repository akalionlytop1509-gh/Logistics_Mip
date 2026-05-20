import pandas as pd
import networkx as nx

def validate_logistics_data(data, optimizer):
    """
    Thực hiện các bước kiểm tra dữ liệu trước khi giải bài toán.
    Trả về (is_valid, errors, warnings)
    """
    errors = []
    warnings = []
    
    # 1. Kiểm tra Tổng Cung vs Tổng Cầu
    total_s = sum(optimizer.supply_map.values())
    total_d = sum(optimizer.demand_map.values())
    if total_s < total_d:
        errors.append(f"Tổng Cung ({total_s:,.0f}) nhỏ hơn Tổng Cầu ({total_d:,.0f}). Mô hình chắc chắn vô nghiệm.")

    # 2. Kiểm tra tính kết nối mạng lưới (Connectivity) sử dụng NetworkX
    G = nx.DiGraph()
    for _, row in optimizer.arcs.iterrows():
        u, v = str(row[optimizer.arc_from]).strip(), str(row[optimizer.arc_to]).strip()
        G.add_edge(u, v)
    
    supply_nodes = [n for n, s in optimizer.supply_map.items() if s > 0]
    demand_nodes = [n for n, d in optimizer.demand_map.items() if d > 0]
    
    # Kiểm tra xem mỗi điểm Demand có thể đến được từ ít nhất 1 điểm Supply không
    for d_node in demand_nodes:
        if d_node not in G:
            errors.append(f"Nút cầu '{d_node}' không tồn tại trong danh sách các tuyến đường (Arcs).")
            continue
            
        reachable = False
        for s_node in supply_nodes:
            if s_node in G and nx.has_path(G, s_node, d_node):
                reachable = True
                break
        if not reachable:
            errors.append(f"Nút cầu '{d_node}' bị cô lập. Không có đường đi nào từ bất kỳ nguồn cung nào tới nút này.")

    # 3. Kiểm tra dữ liệu âm hoặc không hợp lệ
    if (optimizer.arcs[optimizer.arc_uc] < 0).any():
        errors.append("Phát hiện chi phí (UnitCost) âm trong bảng Arcs.")
    
    if (optimizer.arcs[optimizer.arc_cap] < 0).any():
        errors.append("Phát hiện công suất (Capacity) âm trong bảng Arcs.")

    # 4. Cảnh báo (Warnings) - Không ngăn cản chạy nhưng nên lưu ý
    all_arc_nodes = set(optimizer.arcs[optimizer.arc_from]) | set(optimizer.arcs[optimizer.arc_to])
    defined_nodes = set(optimizer.nodes)
    
    undefined = all_arc_nodes - defined_nodes
    if undefined:
        warnings.append(f"Có {len(undefined)} nút xuất hiện trong Arcs nhưng không có trong sheet Nodes: {list(undefined)[:5]}...")

    return len(errors) == 0, errors, warnings
