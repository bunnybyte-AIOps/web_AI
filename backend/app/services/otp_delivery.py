import base64
import logging
import smtplib
from email.message import EmailMessage
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.core.config import settings

logger = logging.getLogger(__name__)


class OTPDeliveryError(RuntimeError):
    pass


def send_otp(destination: str, channel: str, code: str) -> None:
    if channel == "email":
        _send_email(destination, code)
    elif channel == "phone":
        _send_sms(destination, code)
    else:
        raise OTPDeliveryError("Kênh gửi mã OTP không hợp lệ.")


def _send_email(destination: str, code: str) -> None:
    required = (
        settings.SMTP_HOST,
        settings.SMTP_FROM_EMAIL,
    )
    if not all(required):
        # Chế độ thử nghiệm / Đồ án: Khi chưa cấu hình SMTP, ghi nhận mã OTP vào console
        # và cho phép tiếp tục thay vì chặn người dùng đăng ký
        print(f"\n=======================================================")
        print(f"[OTP SIMULATION] Đang gửi mã OTP đến Email: {destination}")
        print(f"[OTP SIMULATION] Mã xác minh của bạn là: {code}")
        print(f"=======================================================\n")
        logger.info("[OTP SIMULATION] Gửi OTP %s tới %s", code, destination)
        return

    message = EmailMessage()
    message["Subject"] = "Mã xác minh CINAI"
    message["From"] = settings.SMTP_FROM_EMAIL
    message["To"] = destination
    message.set_content(
        f"Mã xác minh CINAI của bạn là {code}. Mã có hiệu lực trong 10 phút."
    )

    try:
        if settings.SMTP_USE_SSL:
            with smtplib.SMTP_SSL(
                settings.SMTP_HOST, settings.SMTP_PORT, timeout=15
            ) as server:
                _smtp_login(server)
                server.send_message(message)
        else:
            with smtplib.SMTP(
                settings.SMTP_HOST, settings.SMTP_PORT, timeout=15
            ) as server:
                server.starttls()
                _smtp_login(server)
                server.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        # Nếu gửi SMTP thất bại, fallback sang simulation để không chặn người dùng demo
        print(f"\n[OTP FALLBACK] Lỗi kết nối SMTP ({exc}). Sử dụng OTP mô phỏng: {code}")
        logger.warning("Lỗi gửi email qua SMTP: %s. Fallback mã: %s", exc, code)


def _smtp_login(server: smtplib.SMTP) -> None:
    if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
        server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)


def _send_sms(destination: str, code: str) -> None:
    account_sid = settings.TWILIO_ACCOUNT_SID
    auth_token = settings.TWILIO_AUTH_TOKEN
    from_number = settings.TWILIO_FROM_NUMBER
    if not all((account_sid, auth_token, from_number)):
        print(f"\n=======================================================")
        print(f"[OTP SIMULATION] Đang gửi mã OTP đến SMS: {destination}")
        print(f"[OTP SIMULATION] Mã xác minh của bạn là: {code}")
        print(f"=======================================================\n")
        logger.info("[OTP SIMULATION] Gửi SMS OTP %s tới %s", code, destination)
        return

    body = urlencode(
        {
            "To": destination,
            "From": from_number,
            "Body": f"Mã xác minh CINAI của bạn là {code}. Mã có hiệu lực trong 10 phút.",
        }
    ).encode()
    request = Request(
        f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    request.add_header(
        "Authorization",
        "Basic " + base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode(),
    )
    try:
        with urlopen(request, timeout=15) as response:
            if response.status >= 400:
                print(f"[OTP SMS FALLBACK] Twilio từ chối. Mã OTP mô phỏng: {code}")
    except (HTTPError, URLError, OSError) as exc:
        print(f"[OTP SMS FALLBACK] Lỗi gửi SMS qua Twilio ({exc}). Mã OTP mô phỏng: {code}")
