import os
import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from PIL import Image
import io
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv

# Tải cấu hình từ file .env (nếu chạy local)
load_dotenv()

# Cấu hình logging cho Streamlit Dashboard ghi ra file log quay vòng
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./data/uploads")
LOG_DIR = os.path.join(os.path.dirname(UPLOAD_DIR), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "dashboard.log")

logger = logging.getLogger("dashboard")
logger.setLevel(logging.INFO)

if not logger.handlers:
    formatter = logging.Formatter("[%(asctime)s] %(levelname)s [%(name)s] - %(message)s")
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler
    file_handler = RotatingFileHandler(LOG_FILE, maxBytes=10*1024*1024, backupCount=5)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

# Ghi nhận uvicorn/streamlit server logs
logger.info("Streamlit dashboard starting...")

# Cấu hình trang Streamlit
st.set_page_config(
    page_title="DocUnder - Document Intelligence Dashboard",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Cấu hình Backend URL và API Key
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8001")
API_KEY = os.getenv("API_KEY", "docunder_secret_token_2026")
HEADERS = {"X-API-Key": API_KEY}

# Custom CSS để giao diện trông hiện đại và chuyên nghiệp hơn
st.markdown("""
<style>
    .main {
        background-color: #f8f9fa;
    }
    .metric-card {
        background-color: white;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
        border: 1px solid #e9ecef;
        text-align: center;
    }
    .metric-title {
        font-size: 14px;
        color: #6c757d;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        margin-bottom: 8px;
    }
    .metric-value {
        font-size: 28px;
        font-weight: 700;
        color: #1a1a1a;
    }
    .stButton>button {
        border-radius: 6px;
    }
    h1, h2, h3 {
        color: #1e293b;
    }
</style>
""", unsafe_allow_html=True)

# Helper: Kiểm tra kết nối tới Backend
def check_backend_connection():
    try:
        response = requests.get(f"{BACKEND_URL}/api/invoices", headers=HEADERS, timeout=2)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False

# ==================== API Callers ====================
def fetch_statistics():
    try:
        response = requests.get(f"{BACKEND_URL}/api/statistics", headers=HEADERS)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        st.error(f"Lỗi khi lấy dữ liệu thống kê: {e}")
    return None

def fetch_invoices():
    try:
        response = requests.get(f"{BACKEND_URL}/api/invoices", headers=HEADERS)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        st.error(f"Lỗi khi lấy danh sách hoá đơn: {e}")
    return []

def extract_invoice(file_name, file_bytes):
    files = {"file": (file_name, file_bytes, "image/jpeg")}
    try:
        response = requests.post(f"{BACKEND_URL}/api/extract", files=files, headers=HEADERS)
        if response.status_code == 201:
            return response.json(), None
        else:
            detail = response.json().get("detail", "Lỗi không xác định")
            return None, detail
    except Exception as e:
        return None, f"Không thể kết nối đến server: {e}"

def update_invoice(invoice_id, payload):
    try:
        response = requests.put(f"{BACKEND_URL}/api/invoices/{invoice_id}", json=payload, headers=HEADERS)
        return response.status_code == 200
    except Exception as e:
        st.error(f"Lỗi khi cập nhật hoá đơn: {e}")
        return False

def delete_invoice(invoice_id):
    try:
        response = requests.delete(f"{BACKEND_URL}/api/invoices/{invoice_id}", headers=HEADERS)
        return response.status_code == 204
    except Exception as e:
        st.error(f"Lỗi khi xoá hoá đơn: {e}")
        return False

# Định dạng tiền tệ VND
def format_vnd(amount):
    return f"{amount:,.0f} đ"

# ==================== Sidebar Navigation ====================
st.sidebar.title("🧾 DocUnder")
st.sidebar.subheader("Document Intelligence & Revenue")

if not check_backend_connection():
    st.sidebar.error("❌ Mất kết nối tới Backend Gateway")
    st.sidebar.info(f"Vui lòng đảm bảo server đang chạy tại: {BACKEND_URL}")
else:
    st.sidebar.success("⚡ Đã kết nối tới Backend Gateway")

menu = st.sidebar.radio(
    "Danh mục quản lý",
    ["📊 Thống kê Doanh thu", "📤 Trích xuất Hoá đơn", "🗂️ Quản lý Hoá đơn"]
)

st.sidebar.markdown("---")
st.sidebar.info(
    "💡 **Mẹo**: Hệ thống sử dụng mô hình VLM Qwen3-VL kết hợp xử lý chạy nền (Background Task) để đọc ảnh hoá đơn bất đồng bộ không gây nghẽn hệ thống."
)

# ==================== Page 1: Thống kê Doanh thu ====================
if menu == "📊 Thống kê Doanh thu":
    st.title("📊 Thống kê Doanh thu từ Hoá đơn")
    st.markdown("Phân tích tổng hợp doanh thu và số lượng đơn từ các hoá đơn đã xử lý thành công.")

    stats = fetch_statistics()
    if stats:
        # Hàng KPIs
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-title">Tổng Doanh Thu</div>
                <div class="metric-value">{format_vnd(stats['total_revenue'])}</div>
            </div>
            """, unsafe_allow_html=True)
        with col2:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-title">Số Lượng Hoá Đơn</div>
                <div class="metric-value">{stats['total_invoices']}</div>
            </div>
            """, unsafe_allow_html=True)
        with col3:
            avg_val = stats['total_revenue'] / stats['total_invoices'] if stats['total_invoices'] > 0 else 0
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-title">Giá Trị Trung Bình / Hoá Đơn</div>
                <div class="metric-value">{format_vnd(avg_val)}</div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # Biểu đồ Doanh thu theo thời gian
        st.subheader("📈 Xu hướng doanh thu theo thời gian")
        if stats['revenue_by_date']:
            df_rev = pd.DataFrame(stats['revenue_by_date'])
            df_rev['revenue_formatted'] = df_rev['revenue'].apply(format_vnd)
            
            fig = px.bar(
                df_rev, 
                x='date', 
                y='revenue',
                labels={'date': 'Ngày hoá đơn', 'revenue': 'Doanh thu (VND)'},
                title="Doanh thu theo ngày (Chỉ tính hoá đơn đã xử lý hoàn tất)",
                hover_data={'revenue': ':,.0f'}
            )
            fig.update_layout(template="plotly_white")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("Chưa có dữ liệu hoá đơn hợp lệ để thống kê theo thời gian.")

        # Biểu đồ Sản phẩm bán chạy
        st.subheader("🏆 Top sản phẩm mang lại doanh thu cao nhất")
        if stats['top_items']:
            df_items = pd.DataFrame(stats['top_items'])
            fig_items = px.bar(
                df_items,
                x='revenue',
                y='description',
                orientation='h',
                labels={'revenue': 'Doanh thu (VND)', 'description': 'Tên sản phẩm'},
                title="Top sản phẩm nổi bật",
                color='revenue',
                color_continuous_scale='Blues',
                hover_data={'revenue': ':,.0f', 'quantity': True}
            )
            fig_items.update_layout(yaxis={'categoryorder': 'total ascending'}, template="plotly_white")
            st.plotly_chart(fig_items, use_container_width=True)
        else:
            st.warning("Chưa có dữ liệu sản phẩm.")
    else:
        st.warning("Chưa có dữ liệu thống kê. Hãy tải lên hoá đơn trước.")

# ==================== Page 2: Trích xuất Hoá đơn ====================
elif menu == "📤 Trích xuất Hoá đơn":
    st.title("📤 Trích xuất Hoá đơn tự động bằng AI")
    st.markdown("Tải lên hình ảnh hoá đơn. Tác vụ trích xuất sẽ được xử lý chạy nền giúp tối ưu hiệu năng.")

    uploaded_file = st.file_uploader(
        "Kéo thả hoặc bấm để chọn ảnh hoá đơn (PNG, JPG, JPEG)", 
        type=["jpg", "jpeg", "png"]
    )

    if uploaded_file is not None:
        file_bytes = uploaded_file.read()
        
        # Tạo 2 cột: Cột 1 xem trước ảnh, Cột 2 hiển thị nút trích xuất
        c1, c2 = st.columns([1, 1])
        with c1:
            st.image(file_bytes, caption="Ảnh hoá đơn tải lên", use_container_width=True)
        
        with c2:
            st.subheader("Hành động")
            if st.button("🚀 Bắt đầu trích xuất bằng VLM", type="primary", use_container_width=True):
                with st.spinner("Đang gửi ảnh và khởi tạo yêu cầu trích xuất..."):
                    result, err = extract_invoice(uploaded_file.name, file_bytes)
                    if err:
                        st.error(f"Lỗi khởi động trích xuất: {err}")
                    else:
                        st.success("🎉 Đã nhận yêu cầu! Bắt đầu xử lý bất đồng bộ...")
                        # Lưu ID hoá đơn đang xử lý vào session state để Polling
                        st.session_state["processing_invoice_id"] = result["id"]
                        st.session_state["last_extracted_invoice"] = None # Reset kết quả hiển thị cũ

        # Vòng lặp Polling kiểm tra trạng thái hoá đơn đang xử lý chạy nền
        if st.session_state.get("processing_invoice_id"):
            inv_id = st.session_state["processing_invoice_id"]
            
            # Khởi tạo container trạng thái Streamlit native UI
            status_placeholder = st.empty()
            status_container = status_placeholder.status("🔄 AI đang co nén ảnh và phân tích hoá đơn. Vui lòng đợi...", expanded=True)
            
            import time
            max_polls = 40  # Tương đương tối đa 60 giây
            polled = 0
            success = False
            
            while polled < max_polls:
                try:
                    resp = requests.get(f"{BACKEND_URL}/api/invoices/{inv_id}", headers=HEADERS)
                    if resp.status_code == 200:
                        inv_data = resp.json()
                        status_str = inv_data.get("status")
                        
                        if status_str == "completed":
                            status_container.update(label="🎉 Trích xuất dữ liệu thành công!", state="complete", expanded=False)
                            st.session_state["last_extracted_invoice"] = inv_data
                            st.session_state["processing_invoice_id"] = None
                            success = True
                            time.sleep(0.5)
                            status_placeholder.empty()
                            st.rerun()
                            break
                        elif status_str == "failed":
                            err_msg = inv_data.get("error_message") or "Lỗi không xác định từ mô hình VLM."
                            status_container.update(label="❌ Trích xuất hoá đơn thất bại!", state="error", expanded=True)
                            st.error(f"Chi tiết lỗi từ VLM: {err_msg}")
                            st.session_state["processing_invoice_id"] = None
                            break
                    else:
                        status_container.update(label="⚠️ Không thể lấy trạng thái từ API Gateway", state="error")
                        st.session_state["processing_invoice_id"] = None
                        break
                except Exception as e:
                    status_container.update(label=f"⚠️ Lỗi kết nối API: {e}", state="error")
                    st.session_state["processing_invoice_id"] = None
                    break
                
                time.sleep(1.5)
                polled += 1
            else:
                status_container.update(label="⏱️ Hết thời gian chờ (Timeout)!", state="error", expanded=True)
                st.warning("Tác vụ xử lý kéo dài quá lâu. Bạn có thể kiểm tra lại ở tab 'Quản lý Hoá đơn' hoặc xem log.")
                st.session_state["processing_invoice_id"] = None

        # Hiển thị form chỉnh sửa khi đã hoàn tất trích xuất thành công
        if st.session_state.get("last_extracted_invoice"):
            st.markdown("---")
            st.subheader("📝 Kiểm tra & Chỉnh sửa thông tin trích xuất")
            st.info("Bạn có thể điều chỉnh lại các thông tin nếu AI trích xuất chưa chính xác hoàn toàn.")
            
            invoice_data = st.session_state["last_extracted_invoice"]
            invoice_id = invoice_data["id"]

            with st.form(key=f"edit_invoice_form_{invoice_id}"):
                # 2 cột cho các thông tin chung
                col_info1, col_info2 = st.columns(2)
                with col_info1:
                    inv_num = st.text_input("Số Hoá Đơn", value=invoice_data["invoice_number"] or "")
                    tax_amt = st.number_input("Tiền Thuế VAT (VND)", value=float(invoice_data["tax_amount"] or 0.0), step=1000.0)
                
                with col_info2:
                    inv_date = st.text_input("Ngày Xuất Hoá Đơn (YYYY-MM-DD)", value=invoice_data["invoice_date"] or "")
                    total_amt = st.number_input("Tổng Tiền Thanh Toán (VND)", value=float(invoice_data["total_amount"] or 0.0), step=1000.0)

                # Dòng sản phẩm chi tiết
                st.write("**Danh sách sản phẩm/dịch vụ chi tiết:**")
                
                # Biến đổi items thành dataframe để dùng st.data_editor
                items_list = invoice_data["items"]
                df_items = pd.DataFrame(items_list) if items_list else pd.DataFrame(columns=["description", "quantity", "unit_price", "total_price"])
                
                # Đảm bảo các cột cần thiết tồn tại
                for col in ["description", "quantity", "unit_price", "total_price"]:
                    if col not in df_items.columns:
                        df_items[col] = ""
                
                # Cấu hình kiểu dữ liệu của df_items
                df_items = df_items[["description", "quantity", "unit_price", "total_price"]]
                edited_df = st.data_editor(
                    df_items,
                    num_rows="dynamic",
                    column_config={
                        "description": st.column_config.TextColumn("Tên sản phẩm/dịch vụ", required=True),
                        "quantity": st.column_config.NumberColumn("Số lượng", min_value=0.0, format="%.2f"),
                        "unit_price": st.column_config.NumberColumn("Đơn giá (VND)", format="%d"),
                        "total_price": st.column_config.NumberColumn("Thành tiền (VND)", format="%d"),
                    },
                    use_container_width=True,
                    key=f"data_editor_extract_{invoice_id}"
                )

                submit_button = st.form_submit_button(label="💾 Xác nhận & Cập nhật dữ liệu")
                
                if submit_button:
                    # Chuyển đổi edited_df ngược lại list of dicts
                    updated_items = []
                    for _, row in edited_df.iterrows():
                        if pd.isna(row["description"]) or not str(row["description"]).strip():
                            continue
                        
                        try:
                            qty = float(row["quantity"]) if not pd.isna(row["quantity"]) else 1.0
                        except ValueError:
                            qty = 1.0
                            
                        try:
                            price = float(row["unit_price"]) if not pd.isna(row["unit_price"]) else 0.0
                        except ValueError:
                            price = 0.0
                            
                        try:
                            total_p = float(row["total_price"]) if not pd.isna(row["total_price"]) else qty * price
                        except ValueError:
                            total_p = qty * price
                            
                        updated_items.append({
                            "description": str(row["description"]).strip(),
                            "quantity": qty,
                            "unit_price": price,
                            "total_price": total_p
                        })

                    # Dựng payload
                    payload = {
                        "invoice_number": inv_num if inv_num.strip() else None,
                        "invoice_date": inv_date if inv_date.strip() else None,
                        "tax_amount": tax_amt,
                        "total_amount": total_amt,
                        "items": updated_items
                    }

                    if update_invoice(invoice_id, payload):
                        st.success("Đã cập nhật thông tin hoá đơn thành công!")
                        # Lấy lại data mới để reload session state
                        try:
                            resp = requests.get(f"{BACKEND_URL}/api/invoices/{invoice_id}", headers=HEADERS)
                            if resp.status_code == 200:
                                st.session_state["last_extracted_invoice"] = resp.json()
                                st.rerun()
                        except Exception:
                            pass
                    else:
                        st.error("Cập nhật thất bại. Vui lòng kiểm tra lại kết nối và xác thực.")

# ==================== Page 3: Quản lý Hoá đơn ====================
elif menu == "🗂️ Quản lý Hoá đơn":
    st.title("🗂️ Danh sách Hoá đơn")
    st.markdown("Quản lý, tìm kiếm, chỉnh sửa hoặc xoá các hoá đơn trong hệ thống.")

    invoices = fetch_invoices()

    if not invoices:
        st.info("Chưa có hoá đơn nào trong hệ thống. Hãy sang tab 'Trích xuất Hoá đơn' để bắt đầu.")
    else:
        # Chuyển đổi sang DataFrame để dễ lọc
        df_list = []
        for inv in invoices:
            df_list.append({
                "ID": inv["id"],
                "Số hoá đơn": inv["invoice_number"] or "N/A",
                "Ngày lập": inv["invoice_date"] or "N/A",
                "Trạng thái": inv["status"].upper(),
                "Tiền thuế": format_vnd(inv["tax_amount"]),
                "Tổng thanh toán": format_vnd(inv["total_amount"]),
                "Ảnh hoá đơn": inv["image_path"],
                "Ngày thêm": pd.to_datetime(inv["created_at"]).strftime("%d/%m/%Y %H:%M")
            })
        
        df_display = pd.DataFrame(df_list)
        st.dataframe(df_display, use_container_width=True, hide_index=True)

        st.markdown("<br>", unsafe_allow_html=True)
        st.subheader("🔍 Chi tiết và Chỉnh sửa hoá đơn")
        
        # Chọn hoá đơn để xem/sửa
        invoice_ids = [inv["id"] for inv in invoices]
        selected_id = st.selectbox(
            "Chọn ID Hoá đơn để xem chi tiết hoặc chỉnh sửa:", 
            options=invoice_ids,
            format_func=lambda x: f"ID {x} - Số: {next(i['invoice_number'] for i in invoices if i['id'] == x) or 'N/A'} - Trạng thái: {next(i['status'] for i in invoices if i['id'] == x).upper()}"
        )

        if selected_id:
            # Lấy data chi tiết hoá đơn được chọn
            invoice_data = next(i for i in invoices if i["id"] == selected_id)
            
            # Chia thành 2 cột: Cột trái xem ảnh, Cột phải là form xem/sửa
            col_detail1, col_detail2 = st.columns([1, 1])
            
            with col_detail1:
                if invoice_data["image_path"]:
                    # Hiển thị ảnh từ static url của FastAPI
                    image_url = f"{BACKEND_URL}/static/uploads/{invoice_data['image_path']}"
                    try:
                        st.image(image_url, caption=f"Ảnh Hoá Đơn ID {selected_id}", use_container_width=True)
                    except Exception:
                        st.error("Không thể load ảnh từ server.")
                else:
                    st.info("Hoá đơn này không kèm ảnh.")
            
            with col_detail2:
                # Nếu hoá đơn đang xử lý chạy nền, hiển thị thông báo
                if invoice_data["status"] == "processing":
                    st.info("⏳ Hoá đơn này đang được AI phân tích chạy nền. Vui lòng F5 (Rerun) hoặc chọn lại khi đã hoàn tất.")
                elif invoice_data["status"] == "failed":
                    st.error(f"❌ Phân tích thất bại! Lỗi: {invoice_data.get('error_message')}")
                
                with st.form(key=f"manage_invoice_form_{selected_id}"):
                    st.write(f"### Cập nhật Hoá Đơn ID: {selected_id}")
                    
                    col_det_info1, col_det_info2 = st.columns(2)
                    with col_det_info1:
                        m_inv_num = st.text_input("Số Hoá Đơn", value=invoice_data["invoice_number"] or "")
                        m_tax_amt = st.number_input("Tiền Thuế VAT (VND)", value=float(invoice_data["tax_amount"] or 0.0), step=1000.0)
                    
                    with col_det_info2:
                        m_inv_date = st.text_input("Ngày Xuất Hoá Đơn (YYYY-MM-DD)", value=invoice_data["invoice_date"] or "")
                        m_total_amt = st.number_input("Tổng Tiền Thanh Toán (VND)", value=float(invoice_data["total_amount"] or 0.0), step=1000.0)

                    # Dòng sản phẩm
                    st.write("**Danh sách sản phẩm/dịch vụ chi tiết:**")
                    m_items_list = invoice_data["items"]
                    m_df_items = pd.DataFrame(m_items_list) if m_items_list else pd.DataFrame(columns=["description", "quantity", "unit_price", "total_price"])
                    
                    for col in ["description", "quantity", "unit_price", "total_price"]:
                        if col not in m_df_items.columns:
                            m_df_items[col] = ""
                    
                    m_df_items = m_df_items[["description", "quantity", "unit_price", "total_price"]]
                    m_edited_df = st.data_editor(
                        m_df_items,
                        num_rows="dynamic",
                        column_config={
                            "description": st.column_config.TextColumn("Tên sản phẩm/dịch vụ", required=True),
                            "quantity": st.column_config.NumberColumn("Số lượng", min_value=0.0, format="%.2f"),
                            "unit_price": st.column_config.NumberColumn("Đơn giá (VND)", format="%d"),
                            "total_price": st.column_config.NumberColumn("Thành tiền (VND)", format="%d"),
                        },
                        use_container_width=True,
                        key=f"data_editor_manage_{selected_id}"
                    )

                    c_btn1, c_btn2 = st.columns(2)
                    with c_btn1:
                        m_submit = st.form_submit_button("💾 Lưu thay đổi", use_container_width=True)
                    with c_btn2:
                        m_delete = st.form_submit_button("🗑️ Xoá Hoá Đơn", use_container_width=True)

                    if m_submit:
                        m_updated_items = []
                        for _, row in m_edited_df.iterrows():
                            if pd.isna(row["description"]) or not str(row["description"]).strip():
                                continue
                            
                            try:
                                qty = float(row["quantity"]) if not pd.isna(row["quantity"]) else 1.0
                            except ValueError:
                                qty = 1.0
                                
                            try:
                                price = float(row["unit_price"]) if not pd.isna(row["unit_price"]) else 0.0
                            except ValueError:
                                price = 0.0
                                
                            try:
                                total_p = float(row["total_price"]) if not pd.isna(row["total_price"]) else qty * price
                            except ValueError:
                                total_p = qty * price
                                
                            m_updated_items.append({
                                "description": str(row["description"]).strip(),
                                "quantity": qty,
                                "unit_price": price,
                                "total_price": total_p
                            })

                        m_payload = {
                            "invoice_number": m_inv_num if m_inv_num.strip() else None,
                            "invoice_date": m_inv_date if m_inv_date.strip() else None,
                            "tax_amount": m_tax_amt,
                            "total_amount": m_total_amt,
                            "items": m_updated_items
                        }

                        if update_invoice(selected_id, m_payload):
                            st.success("Đã cập nhật hoá đơn thành công!")
                            st.rerun()
                        else:
                            st.error("Cập nhật thất bại. Vui lòng kiểm tra lại quyền truy cập.")

                    elif m_delete:
                        if delete_invoice(selected_id):
                            st.success("Đã xoá hoá đơn thành công!")
                            st.rerun()
                        else:
                            st.error("Xoá hoá đơn thất bại. Vui lòng kiểm tra lại quyền truy cập.")
