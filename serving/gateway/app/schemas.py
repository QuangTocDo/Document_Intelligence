from pydantic import BaseModel, ConfigDict
from typing import List, Optional, Dict
from datetime import datetime

# ==================== Invoice Item Schemas ====================
class InvoiceItemBase(BaseModel):
    description: str
    quantity: float = 1.0
    unit_price: float = 0.0
    total_price: float = 0.0

class InvoiceItemCreate(InvoiceItemBase):
    pass

class InvoiceItem(InvoiceItemBase):
    id: int
    invoice_id: int

    model_config = ConfigDict(from_attributes=True)

# ==================== Invoice Schemas ====================
class InvoiceBase(BaseModel):
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    tax_amount: float = 0.0
    total_amount: float = 0.0

class InvoiceCreate(InvoiceBase):
    items: List[InvoiceItemCreate] = []

class Invoice(InvoiceBase):
    id: int
    image_path: Optional[str] = None
    status: str = "processing"
    error_message: Optional[str] = None
    created_at: datetime
    items: List[InvoiceItem] = []

    model_config = ConfigDict(from_attributes=True)

# ==================== Statistics Schemas ====================
class RevenueByDate(BaseModel):
    date: str
    revenue: float

class ItemRevenue(BaseModel):
    description: str
    quantity: float
    revenue: float

class StatisticsResponse(BaseModel):
    total_revenue: float
    total_invoices: int
    revenue_by_date: List[RevenueByDate]
    top_items: List[ItemRevenue]
