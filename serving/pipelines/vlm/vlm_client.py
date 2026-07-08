import json
import os
from serving.pipelines.vlm.pipeline import InvoiceExtractionPipeline

def main():
    # Khởi tạo pipeline trích xuất với cấu hình mặc định (ngrok URL)
    pipeline = InvoiceExtractionPipeline(
        base_url="https://props-gory-overlay.ngrok-free.dev/v1",
        api_key="none",
        model="cyankiwi/Qwen3-VL-30B-A3B-Instruct-AWQ-4bit"
    )

    # Đường dẫn tới ảnh mẫu trên máy bạn
    image_path = "/Users/trannhutquang/Documents/AppLeadRetrieval/media/normal/2.png" 
    
    if not os.path.exists(image_path):
        print(f"❌ Không tìm thấy ảnh hoá đơn tại: {image_path}")
        print("Vui lòng cập nhật đường dẫn `image_path` trong file sang đường dẫn ảnh hoá đơn thực tế trên máy bạn.")
        return

    print(f"🔄 Đang gửi ảnh '{image_path}' tới VLM để trích xuất thông tin...")
    try:
        with open(image_path, "rb") as f:
            image_bytes = f.read()
            
        result = pipeline.extract_invoice(image_bytes)
        print("\n🎉 Kết quả trích xuất thành công (Đã chuẩn hoá):")
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"❌ Lỗi trong quá trình trích xuất: {e}")

if __name__ == "__main__":
    main()

