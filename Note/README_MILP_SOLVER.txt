# MILP Logistics Network Optimization Solver
## Hướng dẫn cho AI Implement Code

---

## 1. TỔNG QUAN BÀI TOÁN

### 1.1 Mục tiêu
Tối ưu hóa mạng logistics đa phương thức **4-tier** từ Cảng Lạch Huyện → Hải Phòng → Bắc Ninh/Hà Nội → Demand cuối (MASAN, AEON):

```
Tier 0: CẢNG LẠCH HUYỆN (Port - Source + Demand)
  Supply: 3300 TEU/năm (nhập khẩu)
  Demand: 2040 TEU/năm (xuất khẩu)
  Net: +1260 TEU phát ra mạng

Tier 1: Hải Phòng (Hub + Sink)
  - ICD1-HP (Transshipment): b=0
  - KCN1-HP (Sink): b=-900
  - CS1-HP (Transshipment): b=0

Tier 2: Bắc Ninh / Hà Nội (Hub + Source + Sink)
  - ICD2-BN, ICD2-HN (Transshipment): b=0
  - KCN2-BN (Source): b=+800
  - KCN2-HY (Source): b=+200
  - KCN2-HN (Sink): b=-480
  - DC2-BN (Sink): b=-280

Tier 3: Demand cuối (Sink)
  - MASAN: b=-400
  - AEON: b=-200
```

### 1.2 Phương thức vận tải
- **Road**: Chi phí cao, tốc độ, linh hoạt
- **Barge**: Chi phí thấp, sức chứa lớn, chậm
- **Rail, Sea**: (được định nghĩa trong Cost sheet nhưng Arcs hiện không có)

### 1.3 Ràng buộc chính
- **Flow conservation**: Tại mỗi node, dòng vào - dòng ra = b(i)
- **Capacity arc**: Mỗi cung (i,j,mode) có năng lực tối đa
- **Cân bằng cung-cầu**: Total Supply = Total Demand = 5850 TEU
- **ExportDemand**: Ít nhất 2040 TEU phải về Cảng để xuất

---

## 2. CẤU TRÚC DỮ LIỆU EXCEL

### 2.1 Sheet "Nodes" — Danh sách node (PRIMARY)
```
Cột: STT | Node_Name | Tier | Node_Type | Design_Cap

STT=1: CẢNG LẠCH HUYỆN, Tier=0, Port, Cap=3300
STT=2: ICD1-HP, Tier=1, Transshipment, Cap=750
STT=3: KCN1-HP, Tier=1, Sink, Cap=977
STT=4: CS1-HP, Tier=1, Transshipment, Cap=800
STT=5: ICD2-BN, Tier=2, Transshipment, Cap=530
STT=6: ICD2-HN, Tier=2, Transshipment, Cap=285
STT=7: DC2-BN, Tier=2, Sink, Cap=280
STT=8: KCN2-HN, Tier=2, Sink, Cap=815
STT=9: KCN2-BN, Tier=2, Source, Cap=3348
STT=10: KCN2-HY, Tier=2, Source, Cap=1251
STT=11: MASAN, Tier=3, Sink, Cap=492
STT=12: AEON, Tier=3, Sink, Cap=200
```

**Giải thích:**
- `Node_Name`: Tên đầy đủ, phải match với From/To trong Arcs
- `Tier`: 0=Port, 1=Hub Hải Phòng, 2=Hub Bắc Ninh/Hà Nội, 3=Demand cuối
- `Node_Type`: Port / Transshipment / Source / Sink
  - Port: Vừa nhập vừa xuất
  - Transshipment: b(i)=0, chỉ trung chuyển
  - Source: b(i)>0, phát ròng ra mạng
  - Sink: b(i)<0, nhập ròng từ mạng
- `Design_Cap`: Công suất thiết kế (tham khảo, không ảnh hưởng trực tiếp MILP)

### 2.2 Sheet "Supply" — Nguồn cung
```
IP | Supply
CẢNG LẠCH HUYỆN | 3300
KCN2-HY | 700
KCN2-BN | 1850

Total Supply = 5850
```

### 2.3 Sheet "Demand" — Nhu cầu
```
DC | Demand
KCN1-HP | 900
DC2-BN | 280
KCN2-HN | 480
KCN2-BN | 1050
KCN2-HY | 500
MASAN | 400
AEON | 200
CẢNG LẠCH HUYỆN | 2040 ← ExportDemand

Total Demand = 5850 ✅ Cân bằng
```

**Lưu ý quan trọng:**
- Cảng Lạch Huyện vừa có Supply (3300) vừa có Demand (2040)
- b(Cảng) = 3300 - 2040 = +1260 (phát ròng 1260 TEU)
- Tất cả node Sink phải lấy hàng từ Source (trực tiếp hoặc qua Hub)

### 2.4 Sheet "Arcs" — Cung vận tải
```
Cột: From | To | Mode | Distance (km) | UnitCost | Cap | FixedCost | Enabled | IsExport

Ví dụ:
  CẢNG LẠCH HUYỆN → ICD1-HP: Road, 30km, 36000 VND/TEU-km, Cap=5400, FC=100M, IsExport=0
  ICD1-HP → CẢNG LẠCH HUYỆN: Road, 25km, 36000 VND/TEU-km, Cap=5400, FC=100M, IsExport=1
  ICD1-HP → ICD2-BN: Road & Barge (2 mode lựa chọn)
```

**Giải thích:**
- `From`, `To` phải match Node_Name trong Nodes sheet
- `Mode`: Road / Barge / Rail / Sea
- `Distance`: Cơ sở tính chi phí biến = Distance × UnitCost
- `Cap`: Năng lực tối đa trên cung (TEU/năm)
- `FixedCost`: Chi phí cố định khi mở tuyến (VND/năm)
- `Enabled`: 1=tuyến hoạt động, 0=không (để tương lai)
- `IsExport`: 1=tuyến xuất khẩu (To=Port), 0=tuyến nội địa

**Tính chất:**
- Tuyến là **một chiều** (CẢNG→ICD1 ≠ ICD1→CẢNG)
- Có thể có **2 mode cùng từ-đến** (Road + Barge), solver chọn mode nào rẻ hơn
- Tổng cộng **112 arcs** với 4 phương thức chính

### 2.5 Sheet "Cost" — Chi phí vận tải
```
Loại vận tải | Chi phí (VND/TEU-km)
Road | 36000
Barge | 13500
Rail | 8000
Road & Rail, Road & Barge | 22000
```

**Dùng để:**
- Tính chi phí biến trên mỗi arc: `Cost_biến(i,j,m) = Distance(i,j) × UnitCost(m)`

### 2.6 Sheet "Params" — Tham số toàn cục
```
exportDemand | 2040 (TEU/năm) → đã được thêm vào Demand sheet
BigM | 3,000,000 (Big-M constraint)
KL, KICD, KPORT | 1,000,000,000 (hệ số hạn chế hub — có thể chưa dùng)
hL, hICD, hPORT | 8, 10, 6 (chi phí mở/xử lý hub — có thể chưa dùng)
K_road, K_rail, K_water, K_sea | Inf (giới hạn modal shift — chưa active)
EF_road, EF_rail, EF_water, EF_sea | Hệ số phát thải CO2 (kg CO2/TEU-km)
lambda_CO2 | 1 (trọng số carbon trong objective — có thể chưa dùng)
```

---

## 3. FORMULATION MILP

### 3.1 Biến quyết định

**Biến liên tục (Continuous):**
```
x[i,j,m] ≥ 0 (TEU/năm)
  = Lượng hàng vận chuyển từ node i đến node j bằng mode m
  Miền: Arcs × {Road, Barge, Rail, Sea}
```

**Biến nhị phân (Binary) — Optional (tuỳ chọn)**
```
y[i,j,m] ∈ {0,1}
  = 1 nếu tuyến (i,j,m) được mở (chi phí cố định được tính)
  = 0 nếu tuyến được đóng
  
Nếu dùng: x[i,j,m] ≤ BigM × y[i,j,m] (Big-M constraint)
```

### 3.2 Hàm mục tiêu

**Phiên bản LP (không mở/đóng tuyến):**
```
min Z = ∑∑∑ [Distance(i,j) × UnitCost(m)] × x[i,j,m]
        + λ_CO2 × ∑∑∑ [Distance(i,j) × EF(m)] × x[i,j,m]

trong đó:
  - Chi phí biến = Distance × UnitCost = chi phí thực tế vận tải
  - Chi phí CO2 = Distance × EF(m) = phát thải carbon (tuỳ chọn)
  - λ_CO2 = trọng số (có thể = 0 nếu không tính carbon)
```

**Phiên bản MIP (mở/đóng tuyến):**
```
min Z = ∑∑∑ [Distance(i,j) × UnitCost(m)] × x[i,j,m]
        + ∑∑∑ FixedCost(i,j,m) × y[i,j,m]
        + λ_CO2 × ∑∑∑ [Distance(i,j) × EF(m)] × x[i,j,m]
```

### 3.3 Ràng buộc (Constraints)

#### **Ràng buộc 1: Flow Conservation (CORE)**

**Tại node i với net balance b(i) = Supply(i) - Demand(i):**

```
∑_{j: (i,j) ∈ Arcs} ∑_m x[i,j,m] - ∑_{j: (j,i) ∈ Arcs} ∑_m x[j,i,m] = b(i)

Hay viết đơn giản:
  Outflow(i) - Inflow(i) = b(i)

Các trường hợp cụ thể:

1. Node Transshipment (b=0): Inflow = Outflow
   Ví dụ: ICD1-HP, CS1-HP
   
2. Node Source (b>0): Outflow - Inflow = b > 0
   Ví dụ: CẢNG LẠCH HUYỆN (b=+1260), KCN2-BN (b=+800)
   
3. Node Sink (b<0): Inflow - Outflow = |b| > 0
   Ví dụ: KCN1-HP (b=-900), MASAN (b=-400)
   
4. Node Port (b≠0): Giống Source/Sink
   CẢNG LẠCH HUYỆN: b = 3300 - 2040 = +1260
```

#### **Ràng buộc 2: Capacity Arc**

```
x[i,j,m] ≤ Cap[i,j,m]  ∀ (i,j,m) ∈ Arcs

Ví dụ:
  x[CẢNG_LH → ICD1-HP, Road] ≤ 5400 TEU/năm
  x[ICD1-HP → ICD2-BN, Barge] ≤ 18000 TEU/năm
```

#### **Ràng buộc 3: Big-M (nếu dùng MIP với y[i,j,m])**

```
x[i,j,m] ≤ BigM × y[i,j,m]

Ý nghĩa:
  - Nếu y[i,j,m]=0 (đóng): x[i,j,m]=0 (không có hàng)
  - Nếu y[i,j,m]=1 (mở): x[i,j,m]≤BigM (có thể có hàng)

BigM = 3,000,000 (đủ lớn vì max flow ~5850)
```

#### **Ràng buộc 4: ExportDemand (nếu muốn kiểm tra)**

```
∑_{(i,j): IsExport=1, To=CẢNG_LẠCH_HUYỆN} ∑_m x[i,j,m] ≥ 2040

Ý nghĩa: Tổng hàng được đưa về Cảng để xuất phải ≥ 2040 TEU
Lưu ý: Với flow conservation ở Cảng (b=+1260), ràng buộc này tự thỏa
```

#### **Ràng buộc 5: Modal Shift (tùy chọn)**

```
∑_{(i,j): m=Road} x[i,j,m] ≤ K_road
∑_{(i,j): m=Barge} x[i,j,m] ≤ K_water

Hiện tại K_road, K_water = Inf (không giới hạn)
Có thể bật nếu muốn áp dụng chính sách modal shift
```

#### **Ràng buộc 6: Non-negativity & Integrality**

```
x[i,j,m] ≥ 0 (liên tục)
y[i,j,m] ∈ {0,1} (nhị phân, nếu dùng MIP)
```

---

## 4. HƯỚNG DẪN CODE IMPLEMENTATION

### 4.1 Bước 1: Load dữ liệu từ Excel

**Cần đọc các sheet:**
```
1. "Nodes" → DataFrame nodes
   Cột: Node_Name, Tier, Node_Type, Design_Cap
   
2. "Supply" → Dict supply_dict = {node_name: supply_amount}
   
3. "Demand" → Dict demand_dict = {node_name: demand_amount}
   
4. "Arcs" → DataFrame arcs
   Cột: From, To, Mode, Distance, UnitCost, Cap, FixedCost, IsExport, Enabled
   
5. "Cost" → Dict cost_dict = {mode: cost_per_km}
   (Bổ sung từ UnitCost trong Arcs)
   
6. "Params" → Dict params = {key: value}
   Ví dụ: BigM=3000000, export_demand=2040
```

**Xử lý dữ liệu:**
- Nạp toàn bộ dữ liệu, loại bỏ hàng NaN
- Chuẩn hóa tên node (trim spaces)
- Kiểm tra consistency: tất cả From/To trong Arcs có ở Nodes không?
- Tính `b(i) = supply[i] - demand[i]` cho mỗi node

### 4.2 Bước 2: Khởi tạo MILP Model

**Dùng thư viện PuLP hoặc Pyomo:**

```
Model structure:

  Variables:
    - x[i,j,m] ≥ 0 liên tục (LpContinuous)
    - y[i,j,m] ∈ {0,1} (LpBinary) — tùy chọn

  Objective:
    - min ∑∑∑ [Distance(i,j) × UnitCost(m) + λ×EF(m)] × x[i,j,m]
          + ∑∑∑ FixedCost(i,j,m) × y[i,j,m]

  Constraints:
    - Flow conservation tại mỗi node i:
      ∑_j,m x[i,j,m] - ∑_j,m x[j,i,m] = b(i)
      
    - Capacity arc:
      x[i,j,m] ≤ Cap[i,j,m]
      
    - Big-M (nếu MIP):
      x[i,j,m] ≤ BigM × y[i,j,m]
      
    - Non-negativity:
      x[i,j,m] ≥ 0
      y[i,j,m] ∈ {0,1}
```

### 4.3 Bước 3: Thêm Flow Conservation Constraint

**Thuật toán:**
```
for each node i in Nodes:
  outflow = ∑_{j: (i,j) in Arcs} ∑_m x[i,j,m]
  inflow = ∑_{j: (j,i) in Arcs} ∑_m x[j,i,m]
  
  model.addConstraint(outflow - inflow == b[i])
```

**Chi tiết:**
- Loop từng node
- Tìm tất cả arc từ node đó (outgoing)
- Tìm tất cả arc vào node đó (incoming)
- Lập constraint: out - in = b(i)

### 4.4 Bước 4: Thêm Capacity Constraint

```
for each arc (i,j,m) in Arcs:
  model.addConstraint(x[i,j,m] ≤ Cap[i,j,m])
```

### 4.5 Bước 5: Thêm Big-M Constraint (nếu MIP)

```
for each arc (i,j,m) in Arcs:
  model.addConstraint(x[i,j,m] ≤ BigM × y[i,j,m])
```

### 4.6 Bước 6: Solve

```
solver = PULP_CBC_CMD() hoặc GUROBI() hoặc CPLEX()
model.solve(solver)

Kiểm tra status:
  - LpStatusOptimal: Tìm được tối ưu
  - LpStatusInfeasible: Bài toán vô nghiệm (flow không cân bằng)
  - LpStatusUnbounded: Bài toán không bị chặn (hiếm xảy ra)
```

### 4.7 Bước 7: Xử lý kết quả

**Kết quả đầu ra:**
```
1. Objective value = Z_min (tổng chi phí tối ưu)

2. Solution: x[i,j,m] = ?
   In ra các arc có flow > 0.1 (để tránh numerical error)
   Format:
     From | To | Mode | Flow (TEU) | Distance | Cost
     
3. Kiểm tra:
   - Tổng Supply sử dụng = ?
   - Tổng Demand đáp ứng = ?
   - Có deficit/surplus không?
   
4. Visualize:
   - Vẽ network: Node + Arc (độ dày ~ flow)
   - Màu sắc: Tier 0 (vàng), Tier 1 (xanh), Tier 2 (đỏ), Tier 3 (tím)
   - Arc: Road (solid), Barge (dashed)
   - Layout: Tier-based concentric circles
```

---

## 5. LAYOUT VISUALIZATION (TỰ ĐỘNG)

### 5.1 Tier-based Concentric Layout

**Logic:**
```
Tier 0 (Port): 
  Đặt ở tâm (0, 0)
  
Tier 1 (Hub HP):
  Vòng tròn bán kính R1 = 2.5
  4 node → chia đều 360°
  
Tier 2 (Hub BN/HN):
  Vòng tròn bán kính R2 = 5.0
  6 node → chia đều 360°
  
Tier 3 (Demand):
  Vòng tròn bán kính R3 = 7.0
  2 node → chia đều 360°
```

**Công thức tính tọa độ:**
```
def compute_tier_layout(nodes_df):
  TIER_RADIUS = {0: 0, 1: 2.5, 2: 5.0, 3: 7.0}
  pos = {}
  
  for tier in [0, 1, 2, 3]:
    nodes_in_tier = nodes_df[nodes_df['Tier'] == tier]['Node_Name'].tolist()
    n = len(nodes_in_tier)
    r = TIER_RADIUS[tier]
    
    for idx, node_name in enumerate(nodes_in_tier):
      if n == 1:
        angle = π/2  # đỉnh
      else:
        angle = 2π × idx / n + π/2  # chia đều, bắt đầu từ đỉnh
      
      x = r × cos(angle)
      y = r × sin(angle)
      pos[node_name] = (x, y)
  
  return pos
```

**Ưu điểm:**
- Tự động điều chỉnh khi thêm node
- Node cùng tier không bị chồng lên nhau
- Trực quan theo tầng logistics

---

## 6. OUTPUT FORMAT

### 6.1 Console Output

```
================================================================================
MILP LOGISTICS NETWORK OPTIMIZATION RESULT
================================================================================

Problem Status: Optimal
Objective Value: Z_min = ??? (VND)

SOLUTION: Active Routes
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
From              To              Mode    Flow(TEU)  Distance(km)  Cost(VND)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CẢNG LẠCH HUYỆN   ICD1-HP         Road    500        30            540M
ICD1-HP           KCN1-HP         Road    400        8             115M
ICD1-HP           ICD2-BN         Barge   600        180           810M
...

FLOW BALANCE BY NODE:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Node_Name               Tier  Type           Supply  Demand  Inflow  Outflow  Balance
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CẢNG LẠCH HUYỆN         0     Port           3300    2040    500     3800     ✓
ICD1-HP                 1     Transshipment  0       0       1200    1200     ✓
KCN1-HP                 1     Sink           0       900     1100    200      ✓
...

EXPORT VERIFICATION:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total Export to Port: 2040 TEU ≥ Required 2040 ✓
```

### 6.2 Visualization Output

- **Network Graph**: Hiển thị node (màu theo tier) + arc (thickness ~ flow)
- **Flow Table**: Bảng chi tiết luồng hàng trên từng tuyến
- **Balance Chart**: Biểu đồ flow in/out tại mỗi node
- **Cost Breakdown**: Pie chart: chi phí theo mode (Road/Barge)

---

## 7. KIỂM THỬ & VALIDATION

### 7.1 Checklist

```
[ ] Dữ liệu nạp vào đầy đủ: nodes, arcs, supply, demand
[ ] Cân bằng cung-cầu: ∑Supply = ∑Demand
[ ] Tất cả node trong Arcs có ở Nodes không?
[ ] Tất cả dòng xuất khẩu về Port?
[ ] Flow conservation thỏa tại mỗi node?
[ ] Capacity constraint không vượt?
[ ] Objective value > 0 (có chi phí)?
```

### 7.2 Sensitivity Analysis (tuỳ chọn)

```
- Tăng/giảm export demand: Ảnh hưởng chi phí?
- Đóng một hub: Network có sụp?
- Tăng capacity một arc: Chi phí giảm bao nhiêu?
```

---

## 8. TECH STACK ĐỀ NGHỊ

```
Python Libraries:
  - pandas: Load & process Excel
  - openpyxl: Read Excel format
  - PuLP / Pyomo: MILP formulation
  - NetworkX: Network graph structure
  - Matplotlib / Plotly: Visualization
  - Numpy: Numerical computation

Solver:
  - CBC (open-source, bundled với PuLP)
  - Gurobi / CPLEX (commercial, tốt hơn)
  - HiGHS (open-source, cạnh tranh)
```

---

## 9. GHI CHÚ QUAN TRỌNG

1. **Flow Conservation**: Đây là core constraint. Nếu solver không tìm được giải, kiểm tra trước tiên constraint này.

2. **BigM Value**: Phải đủ lớn (>max flow) nhưng không quá lớn (tránh numerical instability). 3,000,000 là hợp lý cho bài toán này.

3. **Enabled Flag**: Các arc với `Enabled=0` nên loại bỏ khỏi mô hình (hoặc thêm ràng buộc x[i,j,m]=0).

4. **IsExport Flag**: Dùng để identify arc nào kết nối tới Port (Return path).

5. **Mode Options**: Một arc có thể có nhiều mode (Road + Barge). Solver sẽ chọn mode rẻ nhất, hoặc kết hợp cả hai nếu cần.

6. **Scalability**: Nếu thêm node, chỉ cần cập nhật Nodes + Arcs + Supply/Demand. Code sẽ tự scale.

---

## 10. THAM KHẢO

- MILP formulation: Network Flow + Mixed-Integer Programming
- Bài toán kinh điển: Facility Location + Hub Location + Transshipment
- Mô hình tương tự thực tế: Coupa Supply Chain Design, Blue Yonder, PTV VISUM Freight

---

**Cập nhật lần cuối:** 2026-05-01  
**Status:** Data structure đã ổn định, sẵn sàng code implement
