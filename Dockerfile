FROM python:3.10-slim

WORKDIR /app

# Cài đặt các công cụ biên dịch cơ bản nếu cần
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Sao chép file cấu hình và cài đặt dependencies
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e .

# Sao chép toàn bộ mã nguồn vào container
COPY . .

# Tạo thư mục lưu trữ dữ liệu tải lên và DB SQLite
RUN mkdir -p /app/data

# Môi trường mặc định
ENV PYTHONUNBUFFERED=1
