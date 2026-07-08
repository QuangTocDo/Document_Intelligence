import os
from dotenv import load_dotenv

# Tải cấu hình từ file .env (nếu chạy local)
load_dotenv()

class Settings:
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./data/invoices.db")
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "./data/uploads")
    VLM_BASE_URL: str = os.getenv("VLM_BASE_URL", "https://props-gory-overlay.ngrok-free.dev/v1")
    VLM_MODEL: str = os.getenv("VLM_MODEL", "cyankiwi/Qwen3-VL-30B-A3B-Instruct-AWQ-4bit")
    VLM_API_KEY: str = os.getenv("VLM_API_KEY", "none")
    API_KEY: str = os.getenv("API_KEY", "docunder_secret_token_2026")

settings = Settings()

# Đảm bảo thư mục lưu ảnh upload tồn tại
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
