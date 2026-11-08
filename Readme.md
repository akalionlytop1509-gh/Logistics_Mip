# Pro Hub Logistics Optimizer

Enterprise Logistics Optimizer system with Google OR-Tools and Streamlit.

## 🌟 Kiến trúc Triển khai (Deployment)

Dự án hiện hỗ trợ **2 chế độ chạy**:
1. **Chế độ 1 nền tảng duy nhất (Khuyên dùng cho Production/Chia sẻ)**: Chạy toàn bộ ứng dụng (UI + Thuật toán tối ưu OR-Tools) trực tiếp trên **Streamlit Community Cloud** (miễn phí, không lo server backend bị ngủ đông hay lỗi kết nối mạng).
2. **Chế độ tách rời**: Backend FastAPI (Render/Docker) + Frontend Streamlit.

---

## 🚀 Hướng dẫn Triển khai lên Streamlit Community Cloud (Chỉ 1 nền tảng duy nhất)

1. Đẩy mã nguồn mới nhất lên GitHub repository của bạn: `https://github.com/akalionlytop1509-gh/Logistics_Mip`.
2. Truy cập [share.streamlit.io](https://share.streamlit.io/) và đăng nhập bằng tài khoản GitHub.
3. Nhấp vào **"Create app"** (hoặc "New app") và chọn:
   - **Repository**: `akalionlytop1509-gh/Logistics_Mip`
   - **Branch**: `main`
   - **Main file path**: `frontend/app.py`
4. Nhấp **Deploy!**

> 💡 **Lưu ý:** 
> Bạn **không cần** cài đặt bất kỳ Secrets nào (không cần Render, không cần `API_BASE_URL`). 
> Hệ thống sẽ tự động nhận diện và kích hoạt bộ giải toán OR-Tools trực tiếp trong Streamlit với hiệu năng cao nhất, không có độ trễ mạng và không bao giờ bị timeout.

---

## 💻 Chạy cục bộ (Local Development)

### Cách 1: Chạy All-in-One gọn nhẹ qua Streamlit
```bash
pip install -r requirements.txt
streamlit run frontend/app.py
```

### Cách 2: Chạy tách rời cả Backend FastAPI và Streamlit
```bash
python run.py
```
- Backend API: `http://127.0.0.1:8000`
- Frontend Dashboard: `http://localhost:8501`
