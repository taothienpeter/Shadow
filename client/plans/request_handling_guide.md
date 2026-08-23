# Hướng dẫn Xử lý Tất cả Request Gửi từ Shadow Client (Backend / n8n Integration Guide)

> **Vị trí tài liệu**: `client/plans/request_handling_guide.md`  
> **Mục đích**: Tài liệu hóa chi tiết toàn bộ các HTTP Request đi ra từ ứng dụng **Shadow Desktop Assistant**, cấu trúc payload, mã phản hồi mong đợi, cũng như luồng gửi thông báo ngược (Server -> Client) và cách xây dựng luồng xử lý trên **n8n / FastAPI / Flask / Node.js**.

---

## 1. Tổng quan Kiến trúc Giao tiếp (Communication Architecture)

Shadow Desktop Assistant giao tiếp hai chiều giữa máy tính cá nhân (Client) và máy chủ xử lý AI (n8n Webhook / Backend API qua mạng LAN hoặc Tailscale):

```
+-------------------------------------------------------------+
|                      SHADOW CLIENT                          |
|                                                             |
|  [FloatingPopup]      [ContextCollector]    [ScriptRunner]  |
|         │                     │                   │         |
|         └──────────────┬──────┴───────────────────┘         |
|                        ▼                                    |
|               [core/api_client.py]                          |
|                        │ (Async HTTP POST)                  |
+────────────────────────┼────────────────────────────────────+
                         │ (1) Gửi Request: Chat / Vision / Context
                         ▼
+─────────────────────────────────────────────────────────────+
|               N8N / BACKEND AI SERVER                       |
|                                                             |
|  1. Nhận Request tại Webhook Endpoint                       |
|  2. Phân loại theo `payload.action`                         |
|  3. Xử lý qua LLM / Vision AI Model / Automation Tools      |
|  4. Trả JSON Response ngay lập tức (Sync Response)          |
|  5. (Tùy chọn) Gửi Notification chủ động về Client          |
+────────────────────────┬────────────────────────────────────+
                         │ (2) Gửi Inbound Notification (HTTP POST)
                         ▼
+─────────────────────────────────────────────────────────────+
|               [core/notification_listener.py]               |
|                 (Chạy Local HTTP Port 8080)                 |
+-------------------------------------------------------------+
```

---

## 2. Chi tiết Toàn bộ Request từ Shadow Client (Outbound Requests)

Tất cả các request từ Shadow Client đều được gửi bằng phương thức **`POST`** tới `N8N_WEBHOOK_URL` (cấu hình trong file `.env`).

### 2.1. Request 1: Trò chuyện Kèm Ngữ Cảnh Màn Hình (`action: "chat"`)

* **Nguồn gốc:** Người dùng nhập tin nhắn vào thanh tìm kiếm `FloatingPopup` (khi chế độ Note = OFF).
* **Đặc tính Bối cảnh Màn hình (Screen-Aware):**
  * **Mặc định:** Tự động chụp toàn màn hình (`capture_mode: "full"`, `screenshot_b64: "..."`) để AI luôn nhìn thấy toàn bộ không gian làm việc.
  * **Chế độ Riêng tư (Privacy Snippet):** Khi người dùng chủ động bấm nút 📷 để khoanh vùng $\rightarrow$ Hệ thống chỉ gửi ảnh vùng được chọn (`capture_mode: "snippet"`).
* **Hàm thực thi:** `FloatingPopup._on_send()` -> `api_client.ask_respond(payload)`
* **Timeout mặc định:** 60 giây.

#### Request Body (JSON):
```json
{
  "action": "chat",
  "message": "Đoạn code trong ảnh này đang bị lỗi gì?",
  "user_prompt": "Đoạn code trong ảnh này đang bị lỗi gì?",
  "capture_mode": "full",
  "screenshot_b64": "<chuỗi_base64_ảnh_jpeg>",
  "active_app": "Code.exe",
  "window_title": "main.py - Shadow - Visual Studio Code",
  "recent_apps": [
    { "app_name": "Code.exe", "window_title": "main.py - Shadow - Visual Studio Code" },
    { "app_name": "chrome.exe", "window_title": "n8n - Workflows - Google Chrome" }
  ],
  "screen_resolution": "1920x1080",
  "timestamp": "2026-08-23T20:30:00.000000+00:00",
  "source": "desktop_assistant"
}
```

---

### 2.2. Request 2: Dịch Nhanh Vùng Màn Hình (`action: "translate"`)

* **Nguồn gốc:** Người dùng bấm nút **Translate** trên thanh popup hoặc gõ `/translate`.
* **Luồng hoạt động:** 
  1. Snipping tool mở để người dùng kéo chọn vùng văn bản cần dịch.
  2. Client gửi ảnh snippet lên n8n webhook (`action: "translate"`).
  3. Server dịch văn bản và trả về kết quả.
  4. Client hiển thị kết quả trên **TranslationPopup** nổi kế bên con trỏ chuột kèm nút Copy.
* **Hàm thực thi:** `FloatingPopup._on_translate_clicked()` -> `api_client.ask_respond(payload)`
* **Timeout mặc định:** 60 giây.

#### Request Body (JSON):
```json
{
  "action": "translate",
  "screenshot_b64": "<chuỗi_base64_vùng_snippet>",
  "capture_mode": "snippet",
  "timestamp": "2026-08-23T20:30:00.000000+00:00",
  "source": "desktop_assistant"
}
```

---

### 2.3. Request 3: Ghi Chú Phân Luồng (`action: "note"`)

* **Nguồn gốc:** Người dùng bật chế độ **[✓ Note]** trên thanh Context Tag của popup.
* **Đặc tính Đính kèm Ảnh:**
  * **Mặc định:** **KHÔNG** chụp màn hình (`screenshot_b64: null`), chỉ gửi text ghi chú thuần túy.
  * **Đính kèm thủ công:** Chỉ gửi kèm ảnh khi người dùng bấm nút máy ảnh 📷 để chọn vùng cụ thể.
* **Hàm thực thi:** `FloatingPopup._on_send()` -> `api_client.ask_respond(payload)`
* **Timeout mặc định:** 60 giây.

#### Request Body (JSON):
```json
{
  "action": "note",
  "content": "Cần refactor lại hàm _compress trong screenshot.py trước thứ 6",
  "message": "Cần refactor lại hàm _compress trong screenshot.py trước thứ 6",
  "screenshot_b64": null,
  "active_app": "Code.exe",
  "window_title": "screenshot.py - Visual Studio Code",
  "recent_apps": [
    { "app_name": "Code.exe", "window_title": "screenshot.py - Visual Studio Code" }
  ],
  "timestamp": "2026-08-23T20:30:00.000000+00:00",
  "source": "desktop_assistant"
}
```

---

### 2.4. Request 4: Kiểm tra Kết nối Webhook (`action: "test"`)

* **Nguồn gốc:** Khi chạy script kiểm tra kết nối `test_connection.py` hoặc bấm Test Connection trên Menu Tray.
* **Hàm thực thi:** `test_connection.py -> test_webhook_api()`

#### Request Body (JSON):
```json
{
  "action": "test",
  "timestamp": "2026-08-23T20:40:00.000000+00:00"
}
```

#### Phản hồi Mong đợi từ Server (JSON):
Server n8n nhận `action: "test"` và chỉ cần trả về JSON xác nhận:
```json
{
  "response": "ack"
}
```

---

## 3. Định dạng Phản hồi Mong đợi từ Server (Response Specification)

Để Shadow Client hiển thị nội dung câu trả lời chính xác lên giao diện popup và thông báo System Tray, Server **bắt buộc** phải trả về HTTP status `200 OK` với định dạng JSON có chứa một trong các key sau (theo thứ tự ưu tiên trích xuất trong `ApiClient.extract_response_text`):

### 3.1. Định dạng Khuyên dùng (Recommended Format)

```json
{
  "response": "Nội dung câu trả lời của trợ lý AI dành cho người dùng."
}
```

### 3.2. Các Định dạng Hợp lệ Khác được Hỗ trợ Tự động

Client hỗ trợ trích xuất tự động qua các cấu trúc phổ biến:

```json
// Cách 1: Sử dụng key "message"
{ "message": "Câu trả lời..." }

// Cách 2: Sử dụng key "text", "answer", "reply", "content"
{ "text": "Câu trả lời..." }
{ "answer": "Câu trả lời..." }

// Cách 3: Lồng trong object "data"
{
  "data": {
    "response": "Câu trả lời nằm bên trong data..."
  }
}

// Cách 4: Khi có lỗi logic từ server
{
  "error": "Mô tả lỗi từ server để hiển thị cho người dùng"
}
```

---

## 4. Xử lý Lỗi & Cơ chế Retry trên Client

Shadow Client được tích hợp cơ chế chịu lỗi tự động (`core/api_client.py`):

| Mã lỗi HTTP | Hành vi của Client | Hướng xử lý phía Backend |
| :--- | :--- | :--- |
| **`200 OK`** | Thành công, trích xuất text và hiển thị lên popup / tray. | Trả đúng JSON schema. |
| **`4xx` (400, 401, 403, 404, 422)** | Ném `ApiClientError`. Hiển thị thông báo lỗi lên popup, **không retry**. | Kiểm tra API Key (`Bearer token`), kiểm tra URL webhook hoặc cú pháp JSON. |
| **`5xx` (500, 502, 503, 504)** | Ném `ApiServerError`. **Tự động retry tối đa 2 lần** với thuật toán Exponential Backoff ($0.5s \rightarrow 1.0s$). | Khắc phục sự cố crash workflow hoặc quá tải tài nguyên trên n8n / server. |
| **Timeout (> 60s)** | Ném `ApiTimeoutError`. Báo lỗi timeout lên UI. | Tối ưu thời gian xử lý LLM hoặc bật streaming nếu cần mở rộng sau này. |
| **Mất kết nối mạng (ConnectError)** | Ném `ApiConnectionError`. Tự động retry 1 lần. | Kiểm tra Tailscale, VPN, firewall hoặc server n8n có đang chạy không. |

---

## 5. Chiều Ngược lại: Gửi Thông báo từ Server về Client (Inbound Notification)

Shadow Client tích hợp sẵn máy chủ HTTP tối giản (`core/notification_listener.py`) chạy ngầm trên máy người dùng để nhận thông báo tức thời từ Server / n8n mà không cần Client phải liên tục gửi request hỏi (Polling).

* **URL nhận thông báo:** `http://<Tailscale_IP_cua_Client>:<NOTIFICATION_PORT>/notification`
  *(Mặc định port là `8080`, cấu hình trong `.env`)*
* **Phương thức:** `POST`

#### Header từ n8n / Server gửi sang Client:
```http
POST /notification HTTP/1.1
Host: 100.x.y.z:8080
Content-Type: application/json
Authorization: Bearer <N8N_AUTH_TOKEN>  (nếu cấu hình N8N_AUTH_TOKEN trong .env)
```

#### Body gửi sang Client (JSON):
```json
{
  "response": "Bạn có một lịch hẹn họp sau 10 phút nữa!",
  "title": "Nhắc nhở công việc"
}
```

#### Phản hồi từ Client trả về cho Server:
```json
{
  "status": "received",
  "timestamp": "2026-08-22T15:25:00.000000+00:00"
}
```

---

## 6. Ví dụ Code Triển khai Xử lý (Backend Implementation Examples)

### 6.1. Ví dụ Template Workflow n8n (Cấu trúc Nodes)

Trong n8n, bạn thiết lập workflow xử lý như sau:

1. **Webhook Node**:
   * *HTTP Method*: `POST`
   * *Path*: `shadow-assistant`
   * *Respond*: `Using 'Respond to Webhook' Node`
2. **Switch Node** (Kiểm tra `$json.body.action`):
   * **Rule 1 (`action == "chat"`):**
     * Kết nối tới Node **AI Agent / OpenAI / Anthropic** với prompt = `$json.body.message`.
   * **Rule 2 (`action == "context_analysis"`):**
     * Kết nối tới Node **OpenAI Chat Model (GPT-4o)**: Truyền ảnh `data:image/jpeg;base64,` + `$json.body.screenshot_b64` cùng prompt phân tích màn hình của `$json.body.active_app`.
   * **Rule 3 (`action.startsWith("context_")`):**
     * Tùy biến prompt theo hành động (`summarize`, `translate`, `explain`) trên nội dung `$json.body.context`.
   * **Rule 4 (Default / `test == true`):**
     * Trả về `{"response": "Connection successful!"}`.
3. **Respond to Webhook Node**:
   * *Response Code*: `200`
   * *Response Body*: `{"response": {{ $json.output }}}`

---

### 6.2. Ví dụ Server Python (FastAPI)

Nếu bạn muốn viết một Backend riêng bằng Python FastAPI:

```python
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from typing import Optional, Any
import uvicorn

app = FastAPI(title="Shadow Assistant Backend")

class ShadowRequest(BaseModel):
    action: Optional[str] = "chat"
    message: Optional[str] = None
    screenshot_b64: Optional[str] = None
    active_app: Optional[str] = None
    window_title: Optional[str] = None
    screen_resolution: Optional[str] = None
    context: Optional[str] = None
    source: Optional[str] = "desktop_assistant"
    test: Optional[bool] = False

@app.post("/webhook/shadow-assistant")
async def handle_shadow_request(
    payload: ShadowRequest, 
    authorization: Optional[str] = Header(None)
):
    # 1. Kiểm tra test connection
    if payload.test:
        return {"response": "Kết nối thành công tới Backend!"}

    # 2. Xử lý Chat Message
    if payload.action == "chat":
        user_message = payload.message or ""
        # TODO: Gọi LLM (OpenAI, Gemini, v.v.)
        ai_reply = f"Đã nhận câu hỏi: {user_message}"
        return {"response": ai_reply}

    # 3. Xử lý Phân tích Bối cảnh Màn hình (Vision)
    elif payload.action == "context_analysis":
        app_name = payload.active_app
        title = payload.window_title
        # payload.screenshot_b64 chứa ảnh Base64
        # TODO: Gửi ảnh vào mô hình Vision AI
        vision_summary = f"Người dùng đang mở ứng dụng {app_name} ({title})."
        return {"response": vision_summary}

    # 4. Xử lý Quick Actions trên Context
    elif payload.action and payload.action.startswith("context_"):
        action_type = payload.action.replace("context_", "")
        ctx_text = payload.context or ""
        return {"response": f"Đã thực hiện {action_type} trên nội dung: {ctx_text[:100]}..."}

    # Mặc định
    return {"response": "Yêu cầu đã được tiếp nhận."}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5678)
```

---

## 7. Bảng Tổng kết Các Loại Request

| Tên Loại Request | Trigger từ Client | Payload Key Nhận diện | Dữ liệu chính gửi kèm | Phản hồi cần trả về |
| :--- | :--- | :--- | :--- | :--- |
| **Chat Message** | Gõ prompt trên popup | `action: "chat"` | `message`, `screenshot_b64` (full/snippet), `active_app`, `recent_apps` | `{"response": "..."}` |
| **Translate** | Bấm nút Translate / `/translate` | `action: "translate"` | `screenshot_b64` (vùng crop) | `{"response": "..."}` |
| **Note Capture** | Bật `[✓ Note]` trên popup | `action: "note"` | `content`, `screenshot_b64` (chỉ khi đính kèm), `active_app` | `{"response": "..."}` |
| **Context Explain** | Bấm nút Explain trên UI | `action: "context_explain"` | `context: string` | `{"response": "..."}` |
| **Context Action** | Bấm nút Action trên UI | `action: "context_action"` | `context: string` | `{"response": "..."}` |
| **Connection Test** | Chạy `tools/test_connection.py` | `action: "test"` | `timestamp: string` | `{"response": "ack"}` |
| **Inbound Notification** | n8n/Backend gửi về máy | Endpoint: `/notification` | `response: string` / `message: string`, `title: string` | `{"status": "delivered"}` |

