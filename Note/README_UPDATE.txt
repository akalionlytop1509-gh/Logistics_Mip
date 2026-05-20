# Update cấu trúc dự liệu mới theo form sau: 
/Code_Hub
├── backend/                # TẦNG BACKEND (FastAPI + OR-Tools)
│   ├── app/
│   │   ├── main.py         # Khởi tạo FastAPI, tích hợp Middleware
│   │   ├── api/            # Định nghĩa các nút bấm (Endpoints)
│   │   │   ├── routes.py   # /optimize, /scenarios, /compare
│   │   │   └── schemas.py  # Pydantic: Kiểm tra định dạng đầu vào (Validation)
│   │   ├── core/           # Logic lõi (Linh hồn của bạn)
│   │   │   ├── optimizer.py # Chuyển từ file 2_model.py cũ (đã sửa lỗi Carbon)
│   │   │   └── config.py   # Load biến môi trường từ .env
│   │   ├── db/             # Tầng dữ liệu (Database)
│   │   │   ├── database.py # Kết nối SQLAlchemy (Engine, Session)
│   │   │   └── models.py   # Khai báo bảng: Supply, Arcs, Scenarios, Results
│   │   └── services/       # Điều phối kịch bản (Business Logic)
│   │       └── solver_service.py # Lấy data -> Gọi Optimizer -> Lưu Result vào DB
│   ├── tests/              # Tầng kiểm thử
│   │   └── test_api.py     # Pytest: Chạy thử xem API có bị lỗi không
│   ├── .env                # Lưu biến mật (DATABASE_URL, LAMBDA_DEFAULT)
│   └── requirements.txt    # Danh sách thư viện Backend (bạn đã nêu)
│
├── frontend/               # TẦNG FRONTEND (Streamlit)
│   ├── app.py              # Giao diện chính (Dashboard)
│   ├── components/         # Các thành phần giao diện tái sử dụng
│   │   ├── maps.py         # Vẽ bản đồ Folium
│   │   └── charts.py       # Vẽ biểu đồ Plotly/Matplotlib
│   └── api_client.py       # Hàm gọi đến Backend (dùng requests)
│
└── data/                   # Dữ liệu mẫu (Excel/CSV)
**Update Backend requirements.txt**
fastapi==0.104.1          # Web framework
uvicorn==0.24.0           # Server
sqlalchemy==2.0           # ORM
pydantic==2.x             # Validation
python-dotenv==1.0        # .env config
pytest==7.4               # Testing

┌──────────────────────────────┐
│ CẢNG LẠCH HUYÊN (IMPORT)     │ Supply = 3,300
│ Supply node (hàng nhập từ 
nước ngoài)│
└───────────┬──────────────────┘
            │
    ┌───────┴───────────┐
    ↓                   ↓
[Cấp 2: ICD/Hub]   [Cấp 3: KCN/Demand]
    │                   │
    ├─ KCN1-HP: 600    ├─ Demand KCN1: 500
    ├─ KCN2-BN: 950    ├─ Demand DC2: 220
    │                   ├─ Demand KCN2-HN: 460
    └───────┬───────────┘ ├─ Demand KCN2-BN: 1,050
            │             ├─ Demand KCN2-HY: 980
            │             ├─ Demand MASAN: 400
            │             └─ Demand AEON: 5
            │             ───────────────────────
            │             Tổng Demand nội địa = 3,615
            │
         [Dư = 1,235]
            │
    ┌───────┴──────────────────┐
    │ CẢNG LẠCH HUYÊN (EXPORT) │ Demand = 1,235
    │ Demand node              │
    └──────────────────────────┘
            ↓
    Xuất khẩu nước ngoài


## 1. Hàm mục tiêu (Objective Function)

Mục tiêu là **cực tiểu hóa tổng chi phí** \( Z \), bao gồm:
- Chi phí biến đổi (vận chuyển),
- Chi phí cố định (thiết lập/duy trì tuyến),
- Chi phí môi trường (phát thải CO₂) (bật/tắt)

Hàm mục tiêu tổng quát:

\[
\min Z = \sum_{i,j,m} \left( c_{ijm} \cdot d_{ijm} \cdot x_{ijm} \right) + \sum_{i,j,m} \left( F_{ijm} \cdot y_{ijm} \right) + \lambda \cdot \sum_{i,j,m} \left( E_m \cdot d_{ijm} \cdot x_{ijm} \right)
\]

Trong đó:
- \( c_{ijm} \): Đơn giá vận chuyển trên mỗi km (\( UnitCost \)),
- \( d_{ijm} \): Khoảng cách giữa hai nút \(i\) và \(j\) theo phương thức \(m\) (\( Distance \)),
- \( x_{ijm} \): Lượng hàng vận chuyển trên tuyến \(i \to j\) bằng phương thức \(m\),
- \( F_{ijm} \): Chi phí cố định để thiết lập/duy trì tuyến \(i \to j\) với phương thức \(m\) (\( FixedCost \)),
- \( y_{ijm} \): Biến nhị phân cho biết tuyến \(i \to j\) theo phương thức \(m\) có được sử dụng hay không (trong mô hình MIP),
- \( E_m \): Hệ số phát thải CO₂ của phương thức \(mode\) (\( EF_m \)),
- \( \lambda \): Trọng số carbon (mức độ ưu tiên môi trường).

> **Chú thích:** Trong trường hợp LP (tuyến tính thuần túy), mô hình tối thiểu hóa tổng chi phí biến đổi cộng với chi phí phát thải, không bao gồm chi phí cố định nếu không có biến nhị phân.

### Thành phần chi phí phát thải CO₂ trong hàm mục tiêu

\[
\lambda \cdot \sum_{i,j,m} \left( E_m \cdot d_{ijm} \cdot x_{ijm} \right)
\]

---

## 2. Ràng buộc phát thải CO₂ tối đa (Carbon Cap Constraint)

Tổng lượng phát thải CO₂ toàn mạng lưới không được vượt quá ngưỡng cho phép:

\[
\sum_{i,j,m} \left( x_{ijm} \cdot d_{ijm} \cdot EF_m \right) \leq E_{max}
\]

Trong đó:
- \( x_{ijm} \): Lượng hàng vận chuyển trên tuyến \(i \to j\) bằng phương thức \(m\),
- \( d_{ijm} \): Khoảng cách của tuyến đường (\( Distance \)),
- \( EF_m \): Hệ số phát thải CO₂ tương ứng với từng phương thức vận tải \(m\) (ví dụ: đường bộ có \(EF\) cao hơn đường thủy),
- \( E_{max} \): Tổng lượng phát thải tối đa được phép cho toàn mạng lưới.

Data Input
    ↓
HubLogisticsOptimizer.__init__()    ← Build Graph
    ↓
solve()   [CP-SAT / MIP]            ← Stage 1: Chọn tuyến mở/đóng (y ∈ {0,1})
    ↓ (trả về fixed_y)
solve_lp(fixed_y)   [GLOP / LP]     ← Stage 2: Tối ưu luồng liên tục trên tuyến đã chọn
    ↓
analyze_results() + Dashboard        ← Post-processing
