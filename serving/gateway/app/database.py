import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:////app/data/invoices.db")

# Nếu chạy local ngoài Docker, đảm bảo thư mục chứa db tồn tại
if DATABASE_URL.startswith("sqlite:///"):
    db_path = DATABASE_URL.replace("sqlite:///", "")
    # Trường hợp đường dẫn chứa /app/data nhưng chạy local ngoài Docker
    if db_path.startswith("/app/data/"):
        os.makedirs("./data", exist_ok=True)
        DATABASE_URL = "sqlite:///./data/invoices.db"
    else:
        dir_name = os.path.dirname(db_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

engine = create_engine(
    DATABASE_URL, 
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    invoice_number = Column(String, nullable=True, index=True)
    invoice_date = Column(String, nullable=True, index=True)  # Định dạng YYYY-MM-DD
    tax_amount = Column(Float, default=0.0)
    total_amount = Column(Float, default=0.0)
    image_path = Column(String, nullable=True)
    status = Column(String, default="processing", index=True)  # "processing", "completed", "failed"
    error_message = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Quan hệ 1-n với InvoiceItem, tự động xóa khi Invoice bị xóa
    items = relationship("InvoiceItem", back_populates="invoice", cascade="all, delete-orphan")

class InvoiceItem(Base):
    __tablename__ = "invoice_items"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), index=True)
    description = Column(String, nullable=False)
    quantity = Column(Float, default=1.0)
    unit_price = Column(Float, default=0.0)
    total_price = Column(Float, default=0.0)

    invoice = relationship("Invoice", back_populates="items")

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
