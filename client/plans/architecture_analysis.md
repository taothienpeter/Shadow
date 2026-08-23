# Phân tích sâu Kiến trúc Hệ thống (Shadow Client)

**Path**: `c:\shadow\client\plans\architecture_analysis.md`

Dưới đây là phân tích chuyên sâu về kiến trúc toàn diện của hệ thống **Shadow Client** (Trợ lý AI Desktop dạng nổi - Floating Assistant). Hệ thống này áp dụng mô hình đa luồng (multi-threading) kết hợp với event-loop của PyQt6, Win32 Native Message Loop và asyncio để đạt hiệu suất tối ưu mà không làm đóng băng giao diện (non-blocking GUI).

---

## 1. Kiến trúc Tổng quan (Architecture Overview)

Mô hình hoạt động của ứng dụng xoay quanh luồng sự kiện chính của **PyQt6 (Main Thread)** kết hợp với nhiều **Background Threads & Workers** thực hiện các tác vụ nặng:

```
                                  +---------------------------------------+
                                  |           OS / Windows 11             |
                                  +---------------------------------------+
                                      │                               │
                      Native Hotkeys  │                               │ Inbound HTTP
                      (Win32 Events)  │                               │ (:8080)
                                      ▼                               ▼
                      +─────────────────────────+   +───────────────────────────+
                      |   HotkeyManager Thread  |   | NotificationListener      |
                      |   (Win32 Msg Loop)      |   | (ReusableHTTPServer)      |
                      +─────────────────────────+   +───────────────────────────+
                                      │                               │
                                      │ pyqtSignal                    │ pyqtSignal
                                      ▼                               ▼
+──────────────────────────────────────────────────────────────────────────────────────────+
|                                    MAIN GUI THREAD (PyQt6)                               |
|                                                                                          |
|    +──────────────────────+    +──────────────────────+    +───────────────────────+     |
|    |    FloatingPopup     |    |   TranslationPopup   |    |        TrayApp        |     |
|    | (Chat / Note / Crop) |    | (HUD Cursor Tracking)|    | (Tray Menu & Settings)|     |
|    +──────────────────────+    +──────────────────────+    +───────────────────────+     |
|                                                                                          |
|    +──────────────────────+    +──────────────────────+    +───────────────────────+     |
|    |  ContextCollector    |    |  AutostartManager    |    |   ScreenshotCapture   |     |
|    | (Focus & App Title)  |    | (HKCU Run Registry)  |    | (mss / PIL Multi-Mon) |     |
|    +──────────────────────+    +──────────────────────+    +───────────────────────+     |
+──────────────────────────────────────────────────────────────────────────────────────────+
                                              │
                                              │ asyncio Coroutine Dispatch
                                              ▼
                              +─────────────────────────────────+
                              |      AsyncRunner Thread         |
                              |  (httpx.AsyncClient -> n8n)     |
                              +─────────────────────────────────+
```

**Giao tiếp giữa các Thread:**
Tất cả các Background Thread đều **không trực tiếp thao tác lên giao diện (UI)** để tránh lỗi thread-safety. Thay vào đó, chúng sử dụng **Qt Signals (`pyqtSignal`)** để gửi thông điệp về Main Thread.

---

## 2. Phân tích chi tiết từng Module cốt lõi

### 2.1. `main.py` - Bộ điều phối trung tâm (The Orchestrator)
- **Nhiệm vụ:** Khởi tạo toàn bộ ứng dụng, tạo `QApplication`, cấu hình môi trường, và kết nối (wire) các module lại với nhau.
- **Tính năng nổi bật:**
  1. **Single-Instance Mutex Guard**: Sử dụng `CreateMutexW(None, False, "Local\\ShadowAssistantSingleInstanceMutex")` ngăn chạy trùng lặp 2 instance gây lỗi xung đột phím tắt (Win32 Error 1409).
  2. Khởi tạo `AsyncRunner` để tạo một Thread chạy `asyncio` event loop.
  3. Tạo `ApiClient` sử dụng `AsyncRunner` đó.
  4. Khởi tạo `FloatingPopup` (UI nổi), `TranslationPopup` (HUD dịch nổi) và `TrayApp` (UI dưới System Tray).
  5. Khởi tạo các Background Services: `HotkeyManager`, `ContextCollector`, `NotificationListener`.
  6. Ràng buộc các Signal (Ví dụ: `<alt>+q` mở/đóng Popup, `<alt>+a` mở Scripts Menu, `<alt>+1..N` kích hoạt kịch bản nhanh).

### 2.2. `core/async_runner.py` - Động cơ Bất đồng bộ (Async Engine)
- **Nhiệm vụ:** Tích hợp thư viện bất đồng bộ (`httpx` trong `api_client`) vào ứng dụng đồng bộ của PyQt.
- **Hoạt động:** Sinh ra một Thread độc lập chỉ để chạy một vòng lặp `asyncio`. Cung cấp phương thức `run_coro()` cho phép các thread khác đẩy coroutine (như gọi HTTP POST) vào chạy mà không làm kẹt (block) giao diện, sau đó trả về kết quả qua `concurrent.futures.Future`.

### 2.3. `core/api_client.py` - Cầu nối Giao tiếp (The API Bridge)
- **Nhiệm vụ:** Quản lý mọi kết nối HTTP đi từ Client đến máy chủ n8n webhook.
- **Đặc điểm nổi bật:**
  - **Connection Pooling:** Sử dụng `httpx.AsyncClient` tái sử dụng connection TCP để tối ưu độ trễ.
  - **Resilience (Khả năng chịu lỗi):** Tích hợp sẵn Decorator `@_retry_on_server_error` với cơ chế *Exponential Backoff* tự động thử lại nếu server bị lỗi `5xx` hoặc mất kết nối.
  - **4-Level Error Hierarchy:** Bóc tách các lỗi như `ApiConnectionError`, `ApiTimeoutError`, `ApiServerError`, và `ApiClientError` để xử lý mượt mà.

### 2.4. `core/hotkey.py` - Quản lý Phím Tắt Win32 (Native Win32 Hotkey Manager)
- **Nhiệm vụ:** Đăng ký và lắng nghe phím tắt toàn cục qua Windows Win32 API (`RegisterHotKey`, `UnregisterHotKey`, `GetMessageW`).
- **Ưu điểm:**
  - Tối ưu 0% CPU khi rảnh.
  - Tách luồng xử lý riêng biệt và chuyển tiếp sự kiện qua `pyqtSignal` để đảm bảo 100% thread-safety khi tương tác với UI.

### 2.5. `core/autostart.py` - Quản lý Khởi Động Cùng Windows (Autostart Manager)
- **Nhiệm vụ:** Tự động đăng ký/hủy đăng ký ứng dụng vào khóa Registry: `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`.
- **Đặc điểm:** Không yêu cầu quyền Administrator, tương thích cả khi chạy từ mã nguồn Python (`pythonw.exe`) và khi chạy từ file đóng gói độc lập (`Shadow.exe`).

### 2.6. `core/context_collector.py` - Thu thập Bối cảnh Ứng dụng (Context Engine)
- **Nhiệm vụ:** Theo dõi cửa sổ đang active (`win32gui`, `psutil`) mỗi 300ms, tự động lọc bỏ chính cửa sổ của Shadow Assistant để tránh nhiễu ngữ cảnh.

### 2.7. `ui/popup.py` - Thanh Tìm kiếm Nổi Đa Năng (Floating Search & Command Bar)
- **Nhiệm vụ:** Cung cấp thanh công cụ tương tác tức thì kiểu Apple Spotlight / Raycast.
- **Tính năng chính:**
  - **Screen-Aware Chat (Mặc định chụp toàn màn hình / Nút 📷 chuyển sang vùng khoanh riêng tư)**.
  - **Chế độ Ghi chú (Note Mode Toggle)**.
  - **Nút hành động nhanh: Dịch nhanh (`translate`), Giải thích (`explain`), Kích hoạt Action (`action`)**.
  - **Menu Scripts nhanh (`Alt + A`)**.
  - **Win32 Force Focus (`SendInput ALT` + `SystemParametersInfoW`)**: Đảm bảo cửa sổ nổi luôn chiếm focus mượt mà khi được gọi.

### 2.8. `ui/translation_popup.py` - Cửa Sổ Dịch Nổi Bám Chuột (Minimalist Translation HUD)
- **Nhiệm vụ:** Hiển thị kết quả dịch tức thì theo dạng thẻ HUD bám theo con trỏ chuột (`QCursor.pos()`).
- **Phím tắt điều khiển:**
  - **`Ctrl + C`**: Sao chép nội dung vào Clipboard + nháy viền sáng xanh neon (`#30D158`) xác nhận trong 300ms rồi đóng cửa sổ.
  - **`Ctrl + X` / `Esc`**: Đóng cửa sổ ngay lập tức (không sao chép).

### 2.9. `core/notification_listener.py` - Máy chủ Nhận Thông Báo (Local Notification Listener)
- **Nhiệm vụ:** Chạy một HTTP Server tối giản (`ReusableHTTPServer`) trên port 8080 (hoặc Tailscale IP) để nhận thông báo chủ động từ n8n.
- **Tối ưu:** Sử dụng `threading.Event()` cho phép ngắt kết nối và đóng server tức thì (0ms) khi ứng dụng tắt.

---

## 3. Quản Lý Dữ Liệu & Đóng Gói (Data & Packaging Architecture)

1. **Dữ liệu Người Dùng (Read/Write)**: Lưu trữ tại `%APPDATA%\AI Desktop Assistant\` (`scripts_config.json`, `hotkeys_config.json`, `screenshot_config.json`, `.env`).
2. **File Thực Thi (Read-Only)**: Đóng gói qua PyInstaller với cấu hình `shadow.spec` (`console=False`) và script `build.bat` 1-Click.
3. **Bộ Công Cụ Bảo Trì (`tools/`)**:
   - `tools/backup_settings.bat` & `.py`: Sao lưu toàn bộ cài đặt thành file `.zip`.
   - `tools/uninstall.bat` & `.py`: Dọn dẹp tiến trình, registry và thư mục dữ liệu sạch sẽ.
   - `tools/test_connection.py`: Chẩn đoán và kiểm thử kết nối 2 chiều với n8n qua Tailscale.
