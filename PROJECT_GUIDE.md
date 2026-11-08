# PROJECT_GUIDE – Xưởng phim AI (Đồ án cơ sở 2)

> File này là tài liệu chuẩn để theo dõi bối cảnh, hiện trạng và lộ trình toàn dự án. Đặt ở thư mục gốc repository; trong cấu trúc hiện tại, file nằm cạnh `README.md` và `index.html`, còn backend ở `backend/`.
> Trước mỗi thay đổi, trợ lý/người phát triển cần đọc file này, kiểm tra trạng thái trong mã nguồn, làm **từng giai đoạn một**, và chỉ chuyển giai đoạn khi đã qua mục "Điều kiện hoàn thành".

## 1. Bối cảnh
- **Tên đề tài:** Xây dựng nền tảng AI đồng sáng tạo và sản xuất nội dung phim đa phương tiện cho Content Creator.
- **Người dùng:** Content Creator cá nhân/nhóm nhỏ. Họ nhập một ý tưởng ngắn, AI đồng sáng tạo, **Creator luôn là người chỉnh sửa và duyệt** (human-in-the-loop).
- **Pipeline đích:** Ý tưởng → Concept → Story Bible → Nhân vật/Thế giới → Kịch bản/Phân cảnh → Hình ảnh + Giọng nói → Video (FFmpeg) → Analytics → Gợi ý tập tiếp theo.
- **Ngôn ngữ giao diện và nội dung AI:** tiếng Việt. Văn phong giao diện: câu ngắn, động từ rõ ràng, thông báo lỗi nói rõ chuyện gì sai và cách sửa.

## 2. Hiện trạng (đã có, đã chạy được)
| Phần | Trạng thái |
|---|---|
| Đăng ký/đăng nhập (JWT, PBKDF2) | **Có OTP qua SMTP hoặc Twilio SMS**, đăng nhập email/điện thoại và đặt lại mật khẩu; cần thông tin nhà cung cấp để gửi thật |
| API dự án và quyền sở hữu | **Đã thêm xác thực/cô lập dự án** cho API dự án, Studio, AI và media |
| API AI | **Có Gemini và Grok tùy chọn** cho concept, Story Bible, kịch bản/phân cảnh và gợi ý; Grok cần `XAI_API_KEY` |
| Giao diện Studio | **Đã nối** đăng nhập, dự án, concept, Story Bible, tập, lịch sử/khôi phục, nhập CSV và vòng đời media trong `studio.html`; `/` hiển thị landing page và `/studio` mở cùng nguồn Studio |
| Season/Episode/World và tính nhất quán | **Có CRUD Season/Episode/World và CRUD phân cảnh**; ngữ cảnh liên tập được đưa vào prompt, nhưng cần đánh giá chất lượng continuity với provider thật |
| Lịch sử AI | **Đã có** xem các phiên bản và khôi phục Story Bible, kịch bản, gợi ý; phạm vi lưu/khôi phục khác nhau theo loại nội dung |
| Analytics và gợi ý tập sau | **Đã có** nhập thủ công/CSV, gợi ý AI và luồng OAuth/sync cho YouTube, TikTok, Facebook Page, Instagram Business/Creator; cần thông tin OAuth được provider cấp quyền và xác minh trên tài khoản thật |
| Sinh ảnh, TTS, dựng video FFmpeg | **Đã có** trạng thái, xem trước, duyệt/thử lại ảnh và audio; render theo tập, xem/tải MP4 và tải SRT. Cần provider/FFmpeg và tư liệu đã duyệt |
| Đóng gói | **Docker Compose chạy app + PostgreSQL 17 và volume riêng cho media/SQLite cũ; health check đã đạt**. Data layer hỗ trợ PostgreSQL; migrator SQLite → PostgreSQL đã chạy nhưng nguồn hiện có 0 bản ghi |

> Cập nhật bảng này sau khi xác minh mã nguồn và chạy thử; không đánh dấu hoàn thành chỉ vì có thư mục, dependency, cấu hình mẫu hoặc nội dung giới thiệu trên landing page.

## 3. Cấu trúc thư mục
```
DACS2/
├─ README.md
├─ PROJECT_GUIDE.md
├─ Dockerfile
├─ docker-compose.yml            # app + PostgreSQL, volume PostgreSQL và media
├─ index.html                   # landing page, tải Studio từ studio.html khi mở Studio
├─ studio.html                  # giao diện Studio, nguồn chính thức
├─ .env.example                  # biến môi trường PostgreSQL cho Docker Compose
├─ backend/
│  ├─ app/
│  │  ├─ api/                   # ai_routes.py, project_routes.py
│  │  ├─ core/                  # config.py
│  │  ├─ schemas/
│  │  ├─ services/              # gemini_service.py
│  │  └─ main.py                # FastAPI entry point
│  ├─ requirements.txt
│  ├─ .env.example
│  └─ storage/
└─ docs/
   └─ USE_CASES_AND_ERD.md      # luồng người dùng và ERD logic
```

## 4. Chạy dự án
```powershell
# Chạy từ thư mục gốc của dự án
Set-Location .\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# Mở backend\.env và điền khóa AI nếu dùng. Cấu hình GOOGLE_CLIENT_ID để bật
# đăng nhập Google; SMTP_* để gửi OTP email hoặc TWILIO_* để gửi SMS.
python -m uvicorn app.main:app --reload --reload-include .env --port 8000
```
Landing page: http://127.0.0.1:8000/  
Swagger kiểm thử API: http://127.0.0.1:8000/docs

Backend cần `GEMINI_API_KEY` để gọi Gemini; khi thiếu key, endpoint báo lỗi cấu hình rõ ràng. Nếu model chính quá tải (HTTP 429/5xx), backend thử model dự phòng `GEMINI_FALLBACK_MODEL` (mặc định `gemini-3.6-flash`). Có thể chọn Grok trong Studio sau khi thêm `XAI_API_KEY` vào `backend/.env`; backend cũng chấp nhận tên cũ `GROK_XAI_API_KEY`. Model mặc định là `grok-4.7`, có thể đổi bằng `XAI_MODEL`. Để bật đăng nhập Google, tạo OAuth 2.0 Client ID loại Web trong Google Cloud Console, đăng ký đúng origin của website trong Authorized JavaScript origins và đặt `GOOGLE_CLIENT_ID` trong `backend/.env`; Google Identity Services sẽ gửi ID token về backend để xác minh chữ ký, audience và email đã xác minh. Không cần gửi client secret về frontend. Để gửi OTP email, cấu hình `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM_EMAIL` và thông tin đăng nhập SMTP nếu nhà cung cấp yêu cầu. Để gửi SMS, cấu hình `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`; số gửi và tài khoản Twilio phải được nhà cung cấp bật. Chỉ cần cấu hình phương thức gửi mà bạn muốn sử dụng. Nếu chưa cấu hình, API báo lỗi cấu hình thay vì giả vờ đã gửi mã. Cấu hình môi trường được đọc khi backend khởi động; nếu server đang chạy mà vừa sửa `.env`, hãy khởi động lại server (lệnh dev ở trên theo dõi `.env` để tự reload). Sinh ảnh cần `STABILITY_API_KEY`; TTS cần package `edge-tts`; render cần FFmpeg và ảnh/audio được lưu cho từng cảnh. Wan2.1 không chạy trên máy không có GPU NVIDIA; cần dịch vụ GPU riêng và adapter/provider được cấu hình nếu muốn dùng model đó. Không lưu khóa thật trong mã nguồn hoặc commit. SQLite mặc định đặt tại `backend/cinai.db`; có thể đổi bằng `DATABASE_PATH`.

`index.html` là landing page; `studio.html` là giao diện Studio duy nhất. `/studio` và `/studio.html` phục vụ trực tiếp Studio, trong khi nút `/#studio` tải cùng `studio.html` trong iframe. Điều hướng tab dùng query `?tab=...`; không còn generator giao diện trùng lặp. Phiên đăng nhập dùng cookie `HttpOnly`, còn dữ liệu dự án được lọc theo chủ sở hữu. Các API xác thực chính: `/api/auth/otp/request`, `/api/auth/register/verify`, `/api/auth/login`, `/api/auth/google/config`, `/api/auth/google`, `/api/auth/password/reset`, `/api/auth/me`, và `/api/auth/logout`. Google OAuth chỉ hoạt động sau khi cấu hình `GOOGLE_CLIENT_ID`; backend xác minh ID token trước khi tạo/đăng nhập tài khoản. `/api/auth/otp/request` chấp nhận `purpose=register` hoặc `password_reset`; mã có thời hạn 10 phút, giới hạn thử/gửi và chỉ lưu dạng băm. `/api/auth/register` cũ bị tắt để không thể bỏ qua xác minh OTP. Các API khác gồm `/api/projects`, `/api/ai/*`, `/api/projects/{id}/analytics`, `/api/projects/{id}/generations`, và `/api/media/*`. Khởi tạo schema là bổ sung/idempotent; xem ERD logic tại `docs/USE_CASES_AND_ERD.md`. Không chạy `migrate_full.py` hoặc `seed_user_data.py` trên dữ liệu cần giữ vì các script đó có thể xóa bảng.

Kiểm thử backend sau khi cài dependencies:
```powershell
Set-Location .\backend
.\.venv\Scripts\Activate.ps1
python -m unittest discover -s .\tests -v
```

## 5. Quy tắc bắt buộc
1. **Làm từng giai đoạn** ở mục 6, mỗi giai đoạn một commit (`feat: …`, `fix: …`). Không làm gộp nhiều giai đoạn.
2. **Không đổi cái đang chạy được** nếu chưa cần: sửa thêm, không viết lại.
3. **Bảo mật:** chỉ gọi AI/ảnh/TTS từ Back-end; không đưa API key vào Front-end hoặc commit; mọi endpoint (trừ login/register) phải kiểm tra JWT và kiểm tra quyền sở hữu dự án.
4. **Mọi kết quả AI phải:** (a) kiểm tra đúng schema JSON trước khi lưu, (b) lưu lại prompt và kết quả để truy vết, (c) cho Creator sửa/tạo lại, (d) báo lỗi rõ ràng, không làm mất dữ liệu cũ khi AI lỗi.
5. **Tác vụ chậm** (sinh ảnh, TTS, render) chạy nền, có trạng thái: `DRAFT → GENERATING → REVIEW → APPROVED`, lỗi là `FAILED` (video: `RENDERING → READY`). Front-end hiển thị đang xử lý và có nút thử lại.
6. **Nội dung:** chỉ hỗ trợ nội dung Creator tự sáng tạo hoặc có quyền sử dụng; prompt không được yêu cầu bắt chước tác phẩm có bản quyền.
7. **Giao diện:** giữ phong cách hiện tại (nền sáng, màu mực `#1b2340`, cobalt `#3b4bdb`, hổ phách `#f2a93b`, dải phim làm điểm nhấn). Phải dùng được trên điện thoại, có focus bàn phím, tôn trọng `prefers-reduced-motion`.
8. Sau mỗi giai đoạn: chạy lại luồng đầy đủ từ đăng ký đến bước mới nhất, chụp màn hình giao diện, ghi vào `docs/` để đưa vào báo cáo.

## 6. Các giai đoạn thực hiện

### GĐ 1 – PostgreSQL và dữ liệu quan hệ (đã hỗ trợ; còn kiểm thử mở rộng)
- Data layer chọn SQLite cho local và PostgreSQL theo `DATABASE_URL`; Docker Compose dùng PostgreSQL 17. ERD logic đã có trong `docs/USE_CASES_AND_ERD.md`; schema hiện vẫn được tạo/cập nhật trực tiếp, chưa dùng SQLAlchemy/Alembic.
- `backend/scripts/migrate_sqlite_to_postgres.py` sao chép các cột tương ứng sang database đích đang trống, giữ nguyên nguồn SQLite và dừng nếu đích đã có dữ liệu. Kiểm chứng lần này chuyển 0 bản ghi vì nguồn tại `/data/cinai.db` không có dữ liệu người dùng.
- Build Compose, health check PostgreSQL/app và CRUD smoke test trên PostgreSQL đã chạy đạt ở lần xác minh trước. Bộ kiểm thử backend hiện có 38 kiểm thử đạt; ERD logic đã được bổ sung. Cần kiểm thử end-to-end auth/Studio trực tiếp trên PostgreSQL trước khi coi giai đoạn hoàn tất.

### GĐ 2 – Season/Episode/Scene và World
- Đã có API/UI tạo, sửa, xóa Season; gán Episode vào Season, quản lý Episode, lọc cảnh theo tập, CRUD Scene và tải phụ đề.
- Khi sinh script, backend ghép tóm tắt Story Bible, nhân vật, thế giới và cảnh tập trước vào context.
- Cần xác minh chất lượng continuity với provider thật; kiểm thử cấu trúc context không thay thế đánh giá nội dung AI.

### GĐ 3 – Phiên bản và lịch sử AI
- Đã có lưu lịch sử, xem input/output và khôi phục Story Bible, kịch bản, gợi ý từ `ai_generations`.
- Khôi phục kịch bản tạo bản ghi mới để giữ lại lịch sử; vẫn cần kiểm thử phục hồi khi provider lỗi trên luồng đầy đủ.

### GĐ 4 – Sinh hình ảnh
- Đã có provider Stability, lưu file/asset, trạng thái, preview, duyệt và retry; cần `STABILITY_API_KEY` để gọi provider thật.
- Chưa xác minh tạo/duyệt một ảnh trên tài khoản provider triển khai.

### GĐ 5 – Giọng đọc (TTS)
- Đã có Edge TTS, lưu file/asset, trạng thái, preview, duyệt và retry; chưa có luồng nghe thử giọng nhân vật độc lập trước khi tạo asset.
- Cần xác minh kết nối dịch vụ mạng và phát audio trên môi trường triển khai.

### GĐ 6 – Dựng video
- Đã có job nền FFmpeg, trạng thái `RENDERING/READY/FAILED`, preview/tải MP4, retry job lỗi và tải phụ đề SRT.
- Render Studio dùng Episode đang chọn; mọi cảnh của tập cần có ảnh và audio đã duyệt. Chưa xác minh render end-to-end trên môi trường triển khai.

### GĐ 7 – Analytics và gợi ý thật
- Đã có nhập thủ công/CSV (tối đa 2 MB, 500 dòng), lưu số liệu, gợi ý AI, OAuth và đồng bộ dữ liệu bài/video từ YouTube, TikTok, Facebook Page và Instagram Business/Creator. Đồng bộ thật còn phụ thuộc quyền API, loại tài khoản, app review, scopes và callback được cấu hình đúng; chưa xác minh với tài khoản/provider thật. Metrics có sẵn khác nhau theo nền tảng, một số chỉ số không được API cung cấp sẽ là 0.

### GĐ 8 – (Tùy chọn, làm khi 1–7 đã ổn) React/Next.js
- Chuyển `static/index.html` sang Next.js + Tailwind, giữ nguyên API và thiết kế. Chỉ làm nếu còn thời gian.

### GĐ 9 – Kiểm thử, đóng gói, tài liệu
- Kiểm thử: đăng nhập sai/hết hạn, truy cập dự án người khác (phải 404/403), AI trả JSON sai, ảnh/TTS/render lỗi, luồng end-to-end.
- Đã build/chạy `Dockerfile` và `docker-compose.yml` với PostgreSQL 17; health check app/database đạt. README có hướng dẫn Compose, biến môi trường, chuyển SQLite và cấu hình OAuth social.
- Đã bổ sung Use Case và ERD logic trong `docs/USE_CASES_AND_ERD.md`. Chưa có ảnh chụp màn hình và video demo trong `docs/`; cần ghi nhận sau khi chạy luồng end-to-end.
- Chưa xác minh đăng nhập/OTP, AI, tạo ảnh, TTS, render và OAuth mạng xã hội trên môi trường triển khai với credential/provider thật. Chưa có gói thuê bao/thanh toán, đăng video tự động, upload media thủ công, nghe thử voice độc lập hoặc trang chính sách/liên hệ; landing page cần không quảng bá các khả năng này như đã sẵn sàng.

## 7. Mốc thời gian đề xuất (khớp đề cương, 01/10 → 20/12/2026)
| Thời gian | Giai đoạn |
|---|---|
| đến 05/11 | Nền tảng + GĐ 1 |
| 06/11 – 25/11 | GĐ 2, 3 |
| 26/11 – 03/12 | GĐ 4, 5 |
| 04/12 – 10/12 | GĐ 6, 7 |
| 11/12 – 16/12 | GĐ 9 (tích hợp, kiểm thử) |
| 17/12 – 20/12 | Báo cáo, slide tiếng Anh, nộp |

## 8. Cách ra lệnh cho trợ lý AI (mẫu)
> Đọc `PROJECT_GUIDE.md`. Thực hiện **GĐ 1** theo đúng mục 6: làm từng bước, chạy thử, rồi cho tôi xem kết quả và đối chiếu "Hoàn thành khi". Chưa làm GĐ 2.

Khi xong một giai đoạn, cập nhật bảng ở mục 2 (Hiện trạng) trước khi sang giai đoạn tiếp theo.
