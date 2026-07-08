import os
import json
import shutil
import logging
from typing import Dict, Any, List
from difflib import SequenceMatcher

from dotenv import load_dotenv
from serving.pipelines.vlm.pipeline import InvoiceExtractionPipeline

# Tải biến môi trường (.env) để lấy cấu hình API VLM
load_dotenv()

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s - %(message)s")
logger = logging.getLogger("prompt_evaluator")

# Đường dẫn mặc định
EVAL_DIR = "./data_preparation/evaluation_set"
GT_FILE = os.path.join(EVAL_DIR, "ground_truth.json")
REPORT_FILE = "./data_preparation/prompt_tuning/evaluation_report.md"

def get_string_similarity(a: str, b: str) -> float:
    """Tính toán độ tương đồng giữa hai chuỗi từ 0.0 đến 1.0."""
    if not a or not b:
        return 1.0 if a == b else 0.0
    return SequenceMatcher(None, str(a).strip().lower(), str(b).strip().lower()).ratio()

class PromptEvaluator:
    def __init__(self, eval_dir: str = EVAL_DIR, gt_file: str = GT_FILE):
        self.eval_dir = eval_dir
        self.gt_file = gt_file
        
        # Khởi tạo pipeline kết nối trực tiếp với VLM Server
        base_url = os.getenv("VLM_BASE_URL", "https://props-gory-overlay.ngrok-free.dev/v1")
        api_key = os.getenv("VLM_API_KEY", "none")
        model = os.getenv("VLM_MODEL", "cyankiwi/Qwen3-VL-30B-A3B-Instruct-AWQ-4bit")
        
        self.pipeline = InvoiceExtractionPipeline(
            base_url=base_url,
            api_key=api_key,
            model=model
        )

    def setup_mock_data(self):
        """Tạo dữ liệu giả lập mẫu nếu thư mục đánh giá trống để người dùng chạy thử ngay."""
        os.makedirs(self.eval_dir, exist_ok=True)
        
        # Nếu chưa có ground truth file, tạo mẫu
        if not os.path.exists(self.gt_file):
            mock_gt = {
                "invoice_1.png": {
                    "invoice_number": "12345",
                    "invoice_date": "2026-07-08",
                    "tax_amount": 10000.0,
                    "total_amount": 110000.0,
                    "items": [
                        {
                            "description": "Sản phẩm A",
                            "quantity": 1.0,
                            "unit_price": 100000.0,
                            "total_price": 100000.0
                        }
                    ]
                }
            }
            with open(self.gt_file, "w", encoding="utf-8") as f:
                json.dump(mock_gt, f, indent=2, ensure_ascii=False)
            logger.info(f"Đã tạo file Ground Truth mẫu tại: {self.gt_file}")

        # Thử sao chép ảnh mẫu 2.png từ thư mục của user vào thư mục test làm invoice_1.png
        sample_src = "/Users/trannhutquang/Documents/AppLeadRetrieval/media/normal/2.png"
        sample_dest = os.path.join(self.eval_dir, "invoice_1.png")
        if os.path.exists(sample_src) and not os.path.exists(sample_dest):
            shutil.copy(sample_src, sample_dest)
            logger.info(f"Đã sao chép ảnh mẫu '{sample_src}' thành '{sample_dest}' để phục vụ kiểm thử.")
        elif not os.path.exists(sample_dest):
            logger.warning(
                f"Không tìm thấy ảnh mẫu tại '{sample_src}'. "
                f"Vui lòng đặt ít nhất một ảnh hoá đơn tên là 'invoice_1.png' vào thư mục '{self.eval_dir}'."
            )

    def load_ground_truth(self) -> Dict[str, Any]:
        """Tải dữ liệu Ground Truth."""
        if not os.path.exists(self.gt_file):
            raise FileNotFoundError(f"Không tìm thấy file Ground Truth tại: {self.gt_file}")
        with open(self.gt_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def evaluate_invoice(self, image_name: str, expected: Dict[str, Any]) -> Dict[str, Any]:
        """Đánh giá chi tiết kết quả của một hoá đơn."""
        image_path = os.path.join(self.eval_dir, image_name)
        metrics = {
            "image_name": image_name,
            "json_valid": False,
            "invoice_number_acc": 0.0,
            "invoice_date_acc": 0.0,
            "tax_amount_acc": 0.0,
            "total_amount_acc": 0.0,
            "items_f1": 0.0,
            "error": None
        }

        if not os.path.exists(image_path):
            metrics["error"] = f"Không tìm thấy file ảnh: {image_path}"
            return metrics

        try:
            with open(image_path, "rb") as f:
                image_bytes = f.read()

            # Gọi VLM trích xuất
            actual = self.pipeline.extract_invoice(image_bytes)
            metrics["json_valid"] = True

            # 1. Đánh giá số hoá đơn (So sánh độ tương đồng chuỗi)
            metrics["invoice_number_acc"] = get_string_similarity(
                actual.get("invoice_number"), expected.get("invoice_number")
            )

            # 2. Đánh giá ngày hoá đơn (Exact match hoặc tương đồng)
            metrics["invoice_date_acc"] = 1.0 if actual.get("invoice_date") == expected.get("invoice_date") else 0.0

            # 3. Đánh giá tiền thuế VAT (Sai số tương đối)
            act_tax = float(actual.get("tax_amount") or 0.0)
            exp_tax = float(expected.get("tax_amount") or 0.0)
            if exp_tax == 0.0:
                metrics["tax_amount_acc"] = 1.0 if act_tax == 0.0 else 0.0
            else:
                metrics["tax_amount_acc"] = max(0.0, 1.0 - abs(act_tax - exp_tax) / exp_tax)

            # 4. Đánh giá tổng tiền hoá đơn (Sai số tương đối)
            act_total = float(actual.get("total_amount") or 0.0)
            exp_total = float(expected.get("total_amount") or 0.0)
            if exp_total == 0.0:
                metrics["total_amount_acc"] = 1.0 if act_total == 0.0 else 0.0
            else:
                metrics["total_amount_acc"] = max(0.0, 1.0 - abs(act_total - exp_total) / exp_total)

            # 5. Đánh giá dòng hàng (Items) - Tính F1 Score dựa trên độ tương đồng mô tả sản phẩm
            act_items = actual.get("items") or []
            exp_items = expected.get("items") or []
            metrics["items_f1"] = self._calculate_items_f1(act_items, exp_items)

        except Exception as e:
            metrics["error"] = str(e)
            logger.error(f"Lỗi khi đánh giá {image_name}: {e}")

        return metrics

    def _calculate_items_f1(self, actual: List[Dict], expected: List[Dict]) -> float:
        """Tính toán F1 Score cho danh sách mặt hàng dựa trên độ tương đồng tên mô tả sản phẩm."""
        if not actual and not expected:
            return 1.0
        if not actual or not expected:
            return 0.0

        matched_count = 0
        used_indices = set()

        for act_item in actual:
            act_desc = act_item.get("description", "")
            best_match_idx = -1
            best_score = 0.0

            for idx, exp_item in enumerate(expected):
                if idx in used_indices:
                    continue
                exp_desc = exp_item.get("description", "")
                score = get_string_similarity(act_desc, exp_desc)
                
                # Coi là khớp nếu độ tương đồng mô tả sản phẩm > 70%
                if score > 0.7 and score > best_score:
                    best_score = score
                    best_match_idx = idx

            if best_match_idx != -1:
                matched_count += 1
                used_indices.add(best_match_idx)

        if matched_count == 0:
            return 0.0

        precision = matched_count / len(actual)
        recall = matched_count / len(expected)
        return 2 * (precision * recall) / (precision + recall)

    def run(self):
        """Chạy toàn bộ quy trình đánh giá tập dữ liệu và ghi báo cáo."""
        logger.info("Bắt đầu khởi chạy đánh giá Prompt VLM...")
        self.setup_mock_data()
        
        try:
            ground_truth = self.load_ground_truth()
        except Exception as e:
            logger.error(f"Không thể khởi chạy đánh giá: {e}")
            return

        results = []
        for image_name, expected in ground_truth.items():
            logger.info(f"Đang xử lý đánh giá hoá đơn: {image_name}...")
            res = self.evaluate_invoice(image_name, expected)
            results.append(res)

        # Tính toán điểm số trung bình (Averages)
        total_files = len(results)
        valid_json_count = sum(1 for r in results if r["json_valid"])
        avg_inv_num = sum(r["invoice_number_acc"] for r in results if r["json_valid"]) / total_files if total_files else 0
        avg_inv_date = sum(r["invoice_date_acc"] for r in results if r["json_valid"]) / total_files if total_files else 0
        avg_tax = sum(r["tax_amount_acc"] for r in results if r["json_valid"]) / total_files if total_files else 0
        avg_total = sum(r["total_amount_acc"] for r in results if r["json_valid"]) / total_files if total_files else 0
        avg_items = sum(r["items_f1"] for r in results if r["json_valid"]) / total_files if total_files else 0

        # Tạo file báo cáo Markdown
        report_content = f"""# Báo cáo đánh giá câu lệnh (Prompt Evaluation Report)

*Ngày đánh giá: 2026-07-08*
*Mô hình sử dụng: `{self.pipeline.model}`*
*Endpoint: `{self.pipeline.client.base_url}`*

---

## 📊 Chỉ Số Đánh Giá Tổng Hợp (Summary Metrics)

| Chỉ số (Metrics) | Kết quả (Score) | Ý nghĩa |
| :--- | :--- | :--- |
| **JSON Parse Rate** | {valid_json_count / total_files * 100:.1f}% ({valid_json_count}/{total_files}) | Tỷ lệ VLM trả về định dạng JSON hợp lệ |
| **Invoice Number Accuracy** | {avg_inv_num * 100:.1f}% | Độ khớp của Số hoá đơn |
| **Invoice Date Accuracy** | {avg_inv_date * 100:.1f}% | Tỷ lệ khớp ngày tháng (YYYY-MM-DD) |
| **Tax Amount Accuracy** | {avg_tax * 100:.1f}% | Độ khớp tiền thuế VAT (cho phép sai lệch tương đối) |
| **Total Amount Accuracy** | {avg_total * 100:.1f}% | Độ khớp tổng số tiền thanh toán |
| **Line Items (F1 Score)** | {avg_items * 100:.1f}% | Độ khớp các sản phẩm bán ra (tên & số lượng) |

---

## 🧾 Kết Quả Chi Tiết Từng File (Detailed Results)

"""
        for r in results:
            if r["error"]:
                report_content += f"### ❌ {r['image_name']}\n- **Lỗi hệ thống**: `{r['error']}`\n\n"
            else:
                report_content += f"""### 📄 {r['image_name']}
- **Trạng thái JSON**: `Hợp lệ (Valid)`
- **Độ khớp Số hoá đơn**: `{r['invoice_number_acc'] * 100:.1f}%`
- **Độ khớp Ngày xuất**: `{r['invoice_date_acc'] * 100:.1f}%`
- **Độ khớp Tiền thuế**: `{r['tax_amount_acc'] * 100:.1f}%`
- **Độ khớp Tổng tiền**: `{r['total_amount_acc'] * 100:.1f}%`
- **Dòng hàng F1 Score**: `{r['items_f1'] * 100:.1f}%`

"""

        # Lưu file báo cáo
        os.makedirs(os.path.dirname(REPORT_FILE), exist_ok=True)
        with open(REPORT_FILE, "w", encoding="utf-8") as f:
            f.write(report_content)

        logger.info(f"🎉 Quá trình đánh giá hoàn tất! Đã xuất file báo cáo tại: {REPORT_FILE}")
        
        # In ra màn hình terminal
        print("\n=======================================================")
        print(f"📊 KẾT QUẢ ĐÁNH GIÁ CHỈ SỐ PROMPT (Tổng cộng {total_files} file):")
        print(f"- JSON Parse Rate: {valid_json_count / total_files * 100:.1f}%")
        print(f"- Accuracy Số hoá đơn: {avg_inv_num * 100:.1f}%")
        print(f"- Accuracy Ngày xuất: {avg_inv_date * 100:.1f}%")
        print(f"- Accuracy Tiền thuế: {avg_tax * 100:.1f}%")
        print(f"- Accuracy Tổng tiền: {avg_total * 100:.1f}%")
        print(f"- Line Items F1 Score: {avg_items * 100:.1f}%")
        print(f"Chi tiết báo cáo được ghi tại: {REPORT_FILE}")
        print("=======================================================\n")

if __name__ == "__main__":
    evaluator = PromptEvaluator()
    evaluator.run()
