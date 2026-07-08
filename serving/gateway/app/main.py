import os
import uuid
import shutil
import logging
from logging.handlers import RotatingFileHandler
from typing import List
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, status, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session
from sqlalchemy import func

from serving.gateway.app.config import settings
from serving.gateway.app.database import init_db, get_db, Invoice, InvoiceItem
from serving.gateway.app.schemas import Invoice as InvoiceSchema, InvoiceCreate, StatisticsResponse, RevenueByDate, ItemRevenue
from serving.pipelines.vlm.pipeline import InvoiceExtractionPipeline

# Tạo thư mục logs và cấu hình logger ghi ra cả console và file
LOG_DIR = os.path.join(os.path.dirname(settings.UPLOAD_DIR), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "gateway.log")

# Cấu hình logging cho module
logger = logging.getLogger("serving.gateway")
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

# Cấu hình root logger để ghi log hệ thống ra file luôn
root_logger = logging.getLogger()
if not any(isinstance(h, RotatingFileHandler) for h in root_logger.handlers):
    root_file_handler = RotatingFileHandler(LOG_FILE, maxBytes=10*1024*1024, backupCount=5)
    root_file_handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s [%(name)s] - %(message)s"))
    root_logger.addHandler(root_file_handler)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Khởi tạo DB khi app khởi động
    logger.info("Initializing database...")
    init_db()
    yield

app = FastAPI(
    title="DocUnder Gateway",
    description="Document Intelligence API for Invoice Processing and Revenue Statistics",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration để Streamlit hoặc React có thể gọi API dễ dàng
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount thư mục upload tĩnh để dashboard có thể xem ảnh hoá đơn trực tiếp
app.mount("/static/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")

# API Key Verification Dependency
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

def verify_api_key(api_key: str = Depends(api_key_header)):
    if api_key != settings.API_KEY:
        logger.warning("Unauthorized access attempt detected with invalid X-API-Key")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Khoá API không hợp lệ hoặc thiếu. Truy cập bị từ chối."
        )
    return api_key

# Khởi tạo Prometheus Instrumentator (phải gọi ngoài lifespan để tránh lỗi thêm middleware sau khi start)
logger.info("Starting Prometheus metrics server...")
from prometheus_fastapi_instrumentator import Instrumentator
Instrumentator().instrument(app).expose(app)

def async_extract_invoice(invoice_id: int, file_path: str):
    """
    Tác vụ chạy nền thực hiện nén ảnh, gọi VLM trích xuất và cập nhật kết quả vào DB.
    """
    logger.info(f"Background task started for Invoice ID: {invoice_id}")
    # Phải tạo session riêng biệt để chạy nền an toàn
    from serving.gateway.app.database import SessionLocal
    db = SessionLocal()
    try:
        db_invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
        if not db_invoice:
            logger.error(f"Invoice ID {invoice_id} not found in background task")
            return

        with open(file_path, "rb") as f:
            image_bytes = f.read()

        # Gọi VLM pipeline (đã có nén ảnh và retry tự động bên trong)
        pipeline = InvoiceExtractionPipeline(
            base_url=settings.VLM_BASE_URL,
            api_key=settings.VLM_API_KEY,
            model=settings.VLM_MODEL
        )
        
        extracted_data = pipeline.extract_invoice(image_bytes)

        # Cập nhật thông tin hoá đơn
        db_invoice.invoice_number = extracted_data.get("invoice_number")
        db_invoice.invoice_date = extracted_data.get("invoice_date")
        db_invoice.tax_amount = extracted_data.get("tax_amount", 0.0)
        db_invoice.total_amount = extracted_data.get("total_amount", 0.0)
        db_invoice.status = "completed"

        # Lưu các line items chi tiết
        for item in extracted_data.get("items", []):
            db_item = InvoiceItem(
                invoice_id=invoice_id,
                description=item.get("description"),
                quantity=item.get("quantity", 1.0),
                unit_price=item.get("unit_price", 0.0),
                total_price=item.get("total_price", 0.0)
            )
            db.add(db_item)

        db.commit()
        logger.info(f"Background task completed successfully for Invoice ID: {invoice_id}")

    except Exception as e:
        db.rollback()
        logger.error(f"Background task failed for Invoice ID {invoice_id}: {e}")
        # Cập nhật trạng thái lỗi vào DB
        try:
            db_invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
            if db_invoice:
                db_invoice.status = "failed"
                db_invoice.error_message = str(e)
                db.commit()
        except Exception as db_err:
            logger.error(f"Failed to update failed status in database for Invoice {invoice_id}: {db_err}")
    finally:
        db.close()

@app.post("/api/extract", response_model=InvoiceSchema, status_code=status.HTTP_201_CREATED)
async def extract_and_save_invoice(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key)
):
    """
    Nhận file ảnh hoá đơn, lưu vào đĩa, khởi tạo bản ghi DB ở trạng thái 'processing',
    sau đó kích hoạt background task để gửi tới VLM và trả về Invoice ngay lập tức.
    """
    # 1. Kiểm tra định dạng file
    filename = file.filename
    ext = os.path.splitext(filename)[1].lower()
    if ext not in [".jpg", ".jpeg", ".png", ".pdf"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Định dạng file không được hỗ trợ. Vui lòng tải lên file ảnh (PNG, JPG, JPEG) hoặc PDF."
        )

    # 2. Tạo tên file duy nhất để tránh trùng lặp
    unique_filename = f"{uuid.uuid4()}{ext}"
    file_path = os.path.join(settings.UPLOAD_DIR, unique_filename)

    # 3. Đọc dữ liệu file và lưu vào đĩa
    try:
        content = await file.read()
        with open(file_path, "wb") as buffer:
            buffer.write(content)
    except Exception as e:
        logger.error(f"Error saving uploaded file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Không thể lưu trữ tệp tin tải lên."
        )

    # 4. Khởi tạo bản ghi Invoice rỗng trong DB với trạng thái "processing"
    try:
        db_invoice = Invoice(
            image_path=unique_filename,
            status="processing",
            tax_amount=0.0,
            total_amount=0.0
        )
        db.add(db_invoice)
        db.commit()
        db.refresh(db_invoice)

        # 5. Đăng ký tác vụ chạy nền xử lý VLM
        background_tasks.add_task(async_extract_invoice, db_invoice.id, file_path)
        
        # Trả về kết quả ngay lập tức
        return db_invoice

    except Exception as e:
        db.rollback()
        if os.path.exists(file_path):
            os.remove(file_path)
        logger.error(f"Failed to initialize invoice in database: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Không thể khởi tạo bản ghi trong cơ sở dữ liệu."
        )

@app.get("/api/invoices", response_model=List[InvoiceSchema])
def list_invoices(db: Session = Depends(get_db), _: str = Depends(verify_api_key)):
    """Lấy danh sách toàn bộ các hoá đơn đã lưu trong DB (sắp xếp mới nhất lên đầu)."""
    return db.query(Invoice).order_by(Invoice.created_at.desc()).all()

@app.get("/api/invoices/{invoice_id}", response_model=InvoiceSchema)
def get_invoice(invoice_id: int, db: Session = Depends(get_db), _: str = Depends(verify_api_key)):
    """Lấy chi tiết một hoá đơn theo ID."""
    db_invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not db_invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy hoá đơn yêu cầu."
        )
    return db_invoice

@app.put("/api/invoices/{invoice_id}", response_model=InvoiceSchema)
def update_invoice(
    invoice_id: int,
    invoice_data: InvoiceCreate,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key)
):
    """Cập nhật hoặc chỉnh sửa thủ công thông tin hoá đơn."""
    db_invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not db_invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy hoá đơn yêu cầu."
        )

    try:
        # Cập nhật thông tin chung hoá đơn
        db_invoice.invoice_number = invoice_data.invoice_number
        db_invoice.invoice_date = invoice_data.invoice_date
        db_invoice.tax_amount = invoice_data.tax_amount
        db_invoice.total_amount = invoice_data.total_amount
        db_invoice.status = "completed"  # Cập nhật thành completed khi chỉnh sửa thủ công thành công

        # Xoá các line items cũ và thêm lại danh sách mới
        db.query(InvoiceItem).filter(InvoiceItem.invoice_id == invoice_id).delete()
        for item in invoice_data.items:
            db_item = InvoiceItem(
                invoice_id=invoice_id,
                description=item.description,
                quantity=item.quantity,
                unit_price=item.unit_price,
                total_price=item.total_price
            )
            db.add(db_item)

        db.commit()
        db.refresh(db_invoice)
        return db_invoice
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update invoice: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Cập nhật hoá đơn thất bại."
        )

@app.delete("/api/invoices/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_invoice(invoice_id: int, db: Session = Depends(get_db), _: str = Depends(verify_api_key)):
    """Xoá một hoá đơn và các sản phẩm của nó khỏi DB, đồng thời xoá ảnh trên ổ đĩa."""
    db_invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not db_invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy hoá đơn yêu cầu."
        )

    try:
        # Xoá file ảnh vật lý
        if db_invoice.image_path:
            file_path = os.path.join(settings.UPLOAD_DIR, db_invoice.image_path)
            if os.path.exists(file_path):
                os.remove(file_path)

        db.delete(db_invoice)
        db.commit()
        return None
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete invoice: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Xoá hoá đơn thất bại."
        )

@app.get("/api/statistics", response_model=StatisticsResponse)
def get_revenue_statistics(db: Session = Depends(get_db), _: str = Depends(verify_api_key)):
    """Tính toán và trả về số liệu thống kê doanh thu (chỉ tính hoá đơn đã xử lý xong)."""
    # 1. Tổng doanh thu & Tổng số lượng hoá đơn (chỉ tính hoá đơn status="completed")
    stats = db.query(
        func.sum(Invoice.total_amount).label("total_revenue"),
        func.count(Invoice.id).label("total_invoices")
    ).filter(Invoice.status == "completed").first()

    total_revenue = float(stats.total_revenue) if stats.total_revenue is not None else 0.0
    total_invoices = int(stats.total_invoices) if stats.total_invoices is not None else 0

    # 2. Thống kê doanh thu theo ngày xuất hoá đơn
    # Group by invoice_date và sum total_amount
    revenue_query = db.query(
        Invoice.invoice_date,
        func.sum(Invoice.total_amount).label("daily_revenue")
    ).filter(Invoice.invoice_date.isnot(None), Invoice.status == "completed")\
     .group_by(Invoice.invoice_date)\
     .order_by(Invoice.invoice_date.asc())\
     .all()

    revenue_by_date = []
    for row in revenue_query:
        # Lọc ra các ngày hợp lệ
        date_str = str(row[0]).strip()
        if date_str:
            revenue_by_date.append(
                RevenueByDate(date=date_str, revenue=float(row[1] or 0.0))
            )

    # 3. Top các sản phẩm/dịch vụ đem lại doanh thu nhiều nhất
    top_items_query = db.query(
        InvoiceItem.description,
        func.sum(InvoiceItem.quantity).label("total_qty"),
        func.sum(InvoiceItem.total_price).label("item_revenue")
    ).join(Invoice, Invoice.id == InvoiceItem.invoice_id)\
     .filter(Invoice.status == "completed")\
     .group_by(InvoiceItem.description)\
     .order_by(func.sum(InvoiceItem.total_price).desc())\
     .limit(10)\
     .all()

    top_items = []
    for row in top_items_query:
        if row[0]:
            top_items.append(
                ItemRevenue(
                    description=str(row[0]),
                    quantity=float(row[1] or 0.0),
                    revenue=float(row[2] or 0.0)
                )
            )

    return StatisticsResponse(
        total_revenue=total_revenue,
        total_invoices=total_invoices,
        revenue_by_date=revenue_by_date,
        top_items=top_items
    )
