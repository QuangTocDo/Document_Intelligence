import base64
import json
import logging
import re
import io
from typing import Dict, Any, Optional
from openai import OpenAI
from PIL import Image
from tenacity import retry, stop_after_attempt, wait_exponential

from serving.pipelines.vlm.prompts import SYSTEM_PROMPT, USER_PROMPT

logger = logging.getLogger(__name__)

class InvoiceExtractionPipeline:
    def __init__(
        self,
        base_url: str = "https://props-gory-overlay.ngrok-free.dev/v1",
        api_key: str = "none",
        model: str = "cyankiwi/Qwen3-VL-30B-A3B-Instruct-AWQ-4bit"
    ):
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model

    def _encode_image_bytes(self, image_bytes: bytes) -> str:
        """Mã hoá dữ liệu ảnh dạng bytes sang chuỗi base64."""
        return base64.b64encode(image_bytes).decode("utf-8")

    def _clean_json_response(self, response_text: str) -> str:
        """Làm sạch kết quả text trả về từ LLM để đảm bảo chỉ còn chuỗi JSON hợp lệ."""
        text = response_text.strip()
        # Loại bỏ các block markdown ```json ... ``` hoặc ``` ... ```
        if text.startswith("```"):
            # Tìm dòng tiếp theo sau ```
            match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
            if match:
                text = match.group(1).strip()
        
        # Nếu vẫn còn ký tự thừa xung quanh JSON (đôi khi LLM nói nhảm trước/sau JSON)
        # Tìm dấu ngoặc nhọn mở đầu tiên và đóng cuối cùng
        start_idx = text.find("{")
        end_idx = text.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            text = text[start_idx:end_idx + 1]
            
        return text

    def compress_image(self, image_bytes: bytes, max_size: int = 1600, quality: int = 85) -> bytes:
        """Co kích thước và nén ảnh hoá đơn để tối ưu hoá lượng token gửi đi."""
        try:
            img = Image.open(io.BytesIO(image_bytes))
            # Chuyển đổi định dạng nếu có kênh alpha (JPEG không hỗ trợ RGBA/transparency)
            if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                img = img.convert('RGB')
            elif img.mode != 'RGB':
                img = img.convert('RGB')
                
            width, height = img.size
            if max(width, height) > max_size:
                if width > height:
                    new_width = max_size
                    new_height = int(height * (max_size / width))
                else:
                    new_height = max_size
                    new_width = int(width * (max_size / height))
                logger.info(f"Resizing image from {width}x{height} to {new_width}x{new_height}")
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
            output = io.BytesIO()
            img.save(output, format='JPEG', quality=quality)
            compressed_bytes = output.getvalue()
            logger.info(f"Compressed image size: {len(image_bytes)/1024:.1f}KB -> {len(compressed_bytes)/1024:.1f}KB")
            return compressed_bytes
        except Exception as e:
            logger.warning(f"Failed to compress image, using original bytes: {e}")
            return image_bytes

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    def _call_vlm_api_with_retry(self, base64_image: str):
        """Gọi VLM API của OpenAI client với cơ chế Retry tự động nếu gặp lỗi."""
        logger.info(f"Sending base64 image to VLM API (model: {self.model})...")
        return self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": USER_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=2048,
            temperature=0.1
        )

    def extract_invoice(self, image_bytes: bytes) -> Dict[str, Any]:
        """Trích xuất thông tin hoá đơn từ dữ liệu bytes của ảnh (nén trước khi gửi)."""
        compressed_bytes = self.compress_image(image_bytes)
        base64_image = self._encode_image_bytes(compressed_bytes)
        
        raw_content = ""
        try:
            # Gọi API VLM với cơ chế retry tự động
            response = self._call_vlm_api_with_retry(base64_image)
            
            raw_content = response.choices[0].message.content
            logger.info(f"Raw VLM response: {raw_content}")
            
            cleaned_content = self._clean_json_response(raw_content)
            extracted_data = json.loads(cleaned_content)
            
            # Chuẩn hoá dữ liệu cơ bản
            return self._normalize_extracted_data(extracted_data)
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from VLM response: {e}")
            raise ValueError(f"Không thể parse JSON từ phản hồi của mô hình. Phản hồi thô: {raw_content}")
        except Exception as e:
            logger.error(f"Error in invoice extraction pipeline: {e}")
            raise e

    def _normalize_extracted_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Chuẩn hoá dữ liệu để đảm bảo đầy đủ các trường bắt buộc trước khi trả về."""
        normalized = {
            "invoice_number": data.get("invoice_number"),
            "invoice_date": data.get("invoice_date"),
            "items": [],
            "tax_amount": 0.0,
            "total_amount": 0.0
        }
        
        # Xử lý thuế suất
        try:
            tax = data.get("tax_amount")
            normalized["tax_amount"] = float(tax) if tax is not None else 0.0
        except (ValueError, TypeError):
            normalized["tax_amount"] = 0.0
            
        # Xử lý tổng tiền
        try:
            total = data.get("total_amount")
            normalized["total_amount"] = float(total) if total is not None else 0.0
        except (ValueError, TypeError):
            normalized["total_amount"] = 0.0

        # Xử lý danh sách sản phẩm
        raw_items = data.get("items") or []
        if not isinstance(raw_items, list):
            raw_items = []
            
        for idx, item in enumerate(raw_items):
            if not isinstance(item, dict):
                continue
                
            desc = item.get("description") or f"Sản phẩm {idx + 1}"
            
            try:
                qty = float(item.get("quantity", 1.0))
            except (ValueError, TypeError):
                qty = 1.0
                
            try:
                price = float(item.get("unit_price", 0.0))
            except (ValueError, TypeError):
                price = 0.0
                
            try:
                total_item = float(item.get("total_price", qty * price))
            except (ValueError, TypeError):
                total_item = qty * price
                
            normalized["items"].append({
                "description": desc,
                "quantity": qty,
                "unit_price": price,
                "total_price": total_item
            })
            
        return normalized
