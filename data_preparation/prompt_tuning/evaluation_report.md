# Báo cáo đánh giá câu lệnh (Prompt Evaluation Report)

*Ngày đánh giá: 2026-07-08*
*Mô hình sử dụng: `cyankiwi/Qwen3-VL-30B-A3B-Instruct-AWQ-4bit`*
*Endpoint: `https://props-gory-overlay.ngrok-free.dev/v1/`*

---

## 📊 Chỉ Số Đánh Giá Tổng Hợp (Summary Metrics)

| Chỉ số (Metrics) | Kết quả (Score) | Ý nghĩa |
| :--- | :--- | :--- |
| **JSON Parse Rate** | 100.0% (4/4) | Tỷ lệ VLM trả về định dạng JSON hợp lệ |
| **Invoice Number Accuracy** | 87.7% | Độ khớp của Số hoá đơn |
| **Invoice Date Accuracy** | 25.0% | Tỷ lệ khớp ngày tháng (YYYY-MM-DD) |
| **Tax Amount Accuracy** | 100.0% | Độ khớp tiền thuế VAT (cho phép sai lệch tương đối) |
| **Total Amount Accuracy** | 75.0% | Độ khớp tổng số tiền thanh toán |
| **Line Items (F1 Score)** | 100.0% | Độ khớp các sản phẩm bán ra (tên & số lượng) |

---

## 🧾 Kết Quả Chi Tiết Từng File (Detailed Results)

### 📄 img/BIL20240618060152.jpg
- **Trạng thái JSON**: `Hợp lệ (Valid)`
- **Độ khớp Số hoá đơn**: `84.2%`
- **Độ khớp Ngày xuất**: `0.0%`
- **Độ khớp Tiền thuế**: `100.0%`
- **Độ khớp Tổng tiền**: `100.0%`
- **Dòng hàng F1 Score**: `100.0%`

### 📄 img/BIL20240619105250.jpg
- **Trạng thái JSON**: `Hợp lệ (Valid)`
- **Độ khớp Số hoá đơn**: `100.0%`
- **Độ khớp Ngày xuất**: `100.0%`
- **Độ khớp Tiền thuế**: `100.0%`
- **Độ khớp Tổng tiền**: `100.0%`
- **Dòng hàng F1 Score**: `100.0%`

### 📄 img/BIL20240702120637.jpg
- **Trạng thái JSON**: `Hợp lệ (Valid)`
- **Độ khớp Số hoá đơn**: `66.7%`
- **Độ khớp Ngày xuất**: `0.0%`
- **Độ khớp Tiền thuế**: `100.0%`
- **Độ khớp Tổng tiền**: `100.0%`
- **Dòng hàng F1 Score**: `100.0%`

### 📄 img/BIL20240916122044.jpg
- **Trạng thái JSON**: `Hợp lệ (Valid)`
- **Độ khớp Số hoá đơn**: `100.0%`
- **Độ khớp Ngày xuất**: `0.0%`
- **Độ khớp Tiền thuế**: `100.0%`
- **Độ khớp Tổng tiền**: `0.0%`
- **Dòng hàng F1 Score**: `100.0%`

