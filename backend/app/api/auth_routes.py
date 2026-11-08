import hashlib
import hmac
import re
import secrets
import sqlite3
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token

from app.core.config import settings
from app.core.database import INTEGRITY_ERRORS, get_db
from app.core.security import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.services.otp_delivery import OTPDeliveryError, send_otp

router = APIRouter(prefix="/auth", tags=["Authentication"])
OTP_TTL_SECONDS = 10 * 60
OTP_REQUEST_WINDOW_SECONDS = 15 * 60
OTP_MAX_REQUESTS = 3
OTP_MAX_DAILY_REQUESTS = 10
OTP_MAX_ATTEMPTS = 5


class OTPRequest(BaseModel):
    channel: str
    contact: str = Field(min_length=3, max_length=254)
    purpose: str


class RegisterVerifyRequest(BaseModel):
    channel: str
    contact: str = Field(min_length=3, max_length=254)
    otp: str = Field(pattern=r"^\d{6}$")
    password: str = Field(min_length=10, max_length=128)
    full_name: str = Field(min_length=1, max_length=120)


class PasswordResetRequest(BaseModel):
    channel: str
    contact: str = Field(min_length=3, max_length=254)
    otp: str = Field(pattern=r"^\d{6}$")
    new_password: str = Field(min_length=10, max_length=128)


class LoginRequest(BaseModel):
    identifier: str | None = Field(default=None, min_length=3, max_length=254)
    email: str | None = Field(default=None, min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class GoogleLoginRequest(BaseModel):
    credential: str = Field(min_length=1, max_length=8192)


def _normalize_contact(channel: str, contact: str) -> str:
    value = contact.strip()
    if channel == "email":
        value = value.lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise HTTPException(status_code=422, detail="Email không hợp lệ.")
        return value
    if channel == "phone":
        compact = re.sub(r"[\s().-]", "", value)
        if compact.startswith("00"):
            compact = "+" + compact[2:]
        elif compact.startswith("0"):
            compact = "+84" + compact[1:]
        elif compact.startswith("84"):
            compact = "+" + compact
        if not re.fullmatch(r"\+[1-9]\d{7,14}", compact):
            raise HTTPException(
                status_code=422,
                detail="Số điện thoại cần có mã quốc gia, ví dụ +84901234567.",
            )
        return compact
    raise HTTPException(status_code=422, detail="Chọn email hoặc số điện thoại.")


def _otp_hash(purpose: str, destination: str, code: str) -> str:
    material = f"{purpose}:{destination}:{code}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), material, hashlib.sha256).hexdigest()


def _user_for_contact(
    connection: sqlite3.Connection, channel: str, contact: str
) -> sqlite3.Row | None:
    if channel == "email":
        return connection.execute(
            "SELECT * FROM users WHERE lower(email) = ? AND email_verified = 1",
            (contact,),
        ).fetchone()
    return connection.execute(
        "SELECT * FROM users WHERE phone = ? AND phone_verified = 1", (contact,)
    ).fetchone()


def _user_exists(
    connection: sqlite3.Connection, channel: str, contact: str
) -> bool:
    value = contact
    if channel == "email":
        row = connection.execute(
            "SELECT 1 FROM users WHERE lower(email) = ?", (value,)
        ).fetchone()
    else:
        row = connection.execute(
            "SELECT 1 FROM users WHERE phone = ?", (value,)
        ).fetchone()
    return row is not None


def _public_user(row: sqlite3.Row) -> dict[str, object]:
    email = row["email"]
    if not row["email_verified"] or (
        email and email.endswith("@phone.cinai.invalid")
    ):
        email = None
    return {
        "id": row["id"],
        "email": email,
        "phone": row["phone"] if row["phone_verified"] else None,
        "full_name": row["full_name"],
        "role": row["role"],
    }


def _set_auth_cookie(
    response: Response, request: Request, row: sqlite3.Row
) -> str:
    token = create_access_token(row["id"], row["role"])
    response.set_cookie(
        "cinai_access_token",
        token,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        max_age=24 * 60 * 60,
        path="/",
    )
    return token


@router.post("/otp/request")
def request_otp(item: OTPRequest) -> dict[str, str]:
    if item.purpose not in {"register", "password_reset"}:
        raise HTTPException(status_code=422, detail="Mục đích OTP không hợp lệ.")
    contact = _normalize_contact(item.channel, item.contact)
    now = int(time.time())
    code = f"{secrets.randbelow(1_000_000):06d}"

    with get_db() as connection:
        exists = _user_exists(connection, item.channel, contact)
        if item.purpose == "register" and exists:
            raise HTTPException(
                status_code=409, detail="Email hoặc số điện thoại đã được đăng ký."
            )
        if item.purpose == "password_reset" and not _user_for_contact(
            connection, item.channel, contact
        ):
            return {
                "message": "Nếu thông tin thuộc tài khoản, mã xác minh sẽ được gửi."
            }

        recent_count = connection.execute(
            """
            SELECT COUNT(*) FROM auth_otps
            WHERE destination = ? AND created_at >= ?
            """,
            (contact, now - OTP_REQUEST_WINDOW_SECONDS),
        ).fetchone()[0]
        if recent_count >= OTP_MAX_REQUESTS:
            raise HTTPException(
                status_code=429,
                detail="Đã yêu cầu quá nhiều mã. Vui lòng thử lại sau 15 phút.",
            )
        daily_count = connection.execute(
            "SELECT COUNT(*) FROM auth_otps WHERE destination = ? AND created_at >= ?",
            (contact, now - 24 * 60 * 60),
        ).fetchone()[0]
        if daily_count >= OTP_MAX_DAILY_REQUESTS:
            raise HTTPException(
                status_code=429,
                detail="Đã đạt giới hạn gửi mã trong ngày. Vui lòng thử lại sau.",
            )
        connection.execute(
            "DELETE FROM auth_otps WHERE created_at < ?",
            (now - 24 * 60 * 60,),
        )
        connection.execute(
            """
            UPDATE auth_otps SET consumed_at = ?
            WHERE destination = ? AND purpose = ? AND consumed_at IS NULL
            """,
            (now, contact, item.purpose),
        )
        cursor = connection.execute(
            """
            INSERT INTO auth_otps
                (destination, purpose, code_hash, expires_at, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                contact,
                item.purpose,
                _otp_hash(item.purpose, contact, code),
                now + OTP_TTL_SECONDS,
                now,
            ),
        )
        otp_id = cursor.lastrowid

    try:
        send_otp(contact, item.channel, code)
    except OTPDeliveryError as exc:
        with get_db() as connection:
            connection.execute(
                "UPDATE auth_otps SET consumed_at = ? WHERE id = ?",
                (int(time.time()), otp_id),
            )
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    is_simulated = (
        item.channel == "email"
        and not all((settings.SMTP_HOST, settings.SMTP_FROM_EMAIL))
    ) or (
        item.channel == "phone"
        and not all(
            (
                settings.TWILIO_ACCOUNT_SID,
                settings.TWILIO_AUTH_TOKEN,
                settings.TWILIO_FROM_NUMBER,
            )
        )
    )
    if is_simulated:
        return {
            "message": f"Chế độ thử nghiệm (không cần SMTP): Mã OTP của bạn là {code}",
            "dev_otp": code,
        }

    return {"message": "Mã xác minh đã được gửi."}


@router.post("/register/verify", status_code=status.HTTP_201_CREATED)
def verify_registration(
    item: RegisterVerifyRequest, response: Response, request: Request
) -> dict[str, object]:
    channel = item.channel
    contact = _normalize_contact(channel, item.contact)
    if not item.full_name.strip():
        raise HTTPException(status_code=422, detail="Họ tên không được để trống.")
    now = int(time.time())
    failure = False
    row = None

    with get_db() as connection:
        otp_row = connection.execute(
            """
            SELECT * FROM auth_otps
            WHERE destination = ? AND purpose = 'register' AND consumed_at IS NULL
            ORDER BY created_at DESC LIMIT 1
            """,
            (contact,),
        ).fetchone()
        if (
            otp_row is None
            or otp_row["expires_at"] <= now
            or otp_row["attempts"] >= OTP_MAX_ATTEMPTS
        ):
            failure = True
        elif not hmac.compare_digest(
            otp_row["code_hash"], _otp_hash("register", contact, item.otp)
        ):
            attempts = otp_row["attempts"] + 1
            connection.execute(
                "UPDATE auth_otps SET attempts = ?, consumed_at = ? WHERE id = ?",
                (attempts, now if attempts >= OTP_MAX_ATTEMPTS else None, otp_row["id"]),
            )
            failure = True
        else:
            if _user_exists(connection, channel, contact):
                raise HTTPException(
                    status_code=409,
                    detail="Email hoặc số điện thoại đã được đăng ký.",
                )
            if channel == "email":
                email = contact
                phone = None
                email_verified, phone_verified = 1, 0
            else:
                phone = contact
                phone_identity = hashlib.sha256(contact.encode()).hexdigest()
                email = f"phone-{phone_identity}@phone.cinai.invalid"
                email_verified, phone_verified = 0, 1
            try:
                cursor = connection.execute(
                    """
                    INSERT INTO users
                        (email, phone, hashed_password, full_name, role,
                         email_verified, phone_verified)
                    VALUES (?, ?, ?, ?, 'creator', ?, ?)
                    """,
                    (
                        email,
                        phone,
                        hash_password(item.password),
                        item.full_name.strip(),
                        email_verified,
                        phone_verified,
                    ),
                )
            except INTEGRITY_ERRORS as exc:
                raise HTTPException(
                    status_code=409,
                    detail="Email hoặc số điện thoại đã được đăng ký.",
                ) from exc
            connection.execute(
                "UPDATE auth_otps SET consumed_at = ? WHERE id = ?",
                (now, otp_row["id"]),
            )
            row = connection.execute(
                "SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()

    if failure:
        raise HTTPException(
            status_code=400, detail="Mã OTP không đúng hoặc đã hết hạn."
        )
    if row is None:
        raise HTTPException(status_code=500, detail="Không thể tạo tài khoản.")
    token = _set_auth_cookie(response, request, row)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": _public_user(row),
    }


@router.post("/password/reset")
def reset_password(item: PasswordResetRequest) -> dict[str, str]:
    contact = _normalize_contact(item.channel, item.contact)
    now = int(time.time())
    failure = False

    with get_db() as connection:
        otp_row = connection.execute(
            """
            SELECT * FROM auth_otps
            WHERE destination = ? AND purpose = 'password_reset'
                AND consumed_at IS NULL
            ORDER BY created_at DESC LIMIT 1
            """,
            (contact,),
        ).fetchone()
        if (
            otp_row is None
            or otp_row["expires_at"] <= now
            or otp_row["attempts"] >= OTP_MAX_ATTEMPTS
        ):
            failure = True
        elif not hmac.compare_digest(
            otp_row["code_hash"], _otp_hash("password_reset", contact, item.otp)
        ):
            attempts = otp_row["attempts"] + 1
            connection.execute(
                "UPDATE auth_otps SET attempts = ?, consumed_at = ? WHERE id = ?",
                (attempts, now if attempts >= OTP_MAX_ATTEMPTS else None, otp_row["id"]),
            )
            failure = True
        else:
            user = _user_for_contact(connection, item.channel, contact)
            if user is None:
                failure = True
            else:
                verified_column = (
                    "email_verified" if item.channel == "email" else "phone_verified"
                )
                connection.execute(
                    f"UPDATE users SET hashed_password = ?, {verified_column} = 1 WHERE id = ?",
                    (hash_password(item.new_password), user["id"]),
                )
                connection.execute(
                    "UPDATE auth_otps SET consumed_at = ? WHERE id = ?",
                    (now, otp_row["id"]),
                )

    if failure:
        raise HTTPException(
            status_code=400, detail="Mã OTP không đúng hoặc đã hết hạn."
        )
    return {"message": "Đã đặt lại mật khẩu. Bạn có thể đăng nhập."}


@router.post("/register", status_code=status.HTTP_410_GONE)
def legacy_register() -> None:
    raise HTTPException(
        status_code=410,
        detail="Hãy yêu cầu và xác minh OTP trước khi tạo tài khoản.",
    )


@router.post("/login")
def login(
    item: LoginRequest, response: Response, request: Request
) -> dict[str, object]:
    identifier = (item.identifier or item.email or "").strip()
    if "@" in identifier:
        normalized = identifier.lower()
        query = """
            SELECT * FROM users
            WHERE lower(email) = ? AND email_verified = 1
        """
    else:
        try:
            normalized = _normalize_contact("phone", identifier)
        except HTTPException:
            normalized = ""
        query = """
            SELECT * FROM users
            WHERE phone = ? AND phone_verified = 1
        """
    with get_db() as connection:
        row = connection.execute(query, (normalized,)).fetchone()
    if row is None or not verify_password(item.password, row["hashed_password"]):
        raise HTTPException(
            status_code=401,
            detail="Email/số điện thoại hoặc mật khẩu không chính xác.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = _set_auth_cookie(response, request, row)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": _public_user(row),
    }


@router.get("/google/config")
def google_auth_config() -> dict[str, str | bool | None]:
    return {
        "configured": bool(settings.GOOGLE_CLIENT_ID),
        "client_id": settings.GOOGLE_CLIENT_ID,
    }


@router.post("/google")
def google_login(
    item: GoogleLoginRequest, response: Response, request: Request
) -> dict[str, object]:
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=503,
            detail="Đăng nhập Google chưa được cấu hình trên máy chủ.",
        )
    try:
        claims = id_token.verify_oauth2_token(
            item.credential, GoogleRequest(), settings.GOOGLE_CLIENT_ID
        )
    except (ValueError, GoogleAuthError) as exc:
        raise HTTPException(
            status_code=401, detail="Không thể xác minh tài khoản Google."
        ) from exc

    email = claims.get("email")
    if (
        not isinstance(email, str)
        or not email
        or claims.get("email_verified") is not True
        or not claims.get("sub")
    ):
        raise HTTPException(
            status_code=401,
            detail="Tài khoản Google chưa cung cấp email đã xác minh.",
        )
    email = email.strip().lower()
    full_name = claims.get("name")
    if not isinstance(full_name, str) or not full_name.strip():
        full_name = email.split("@", 1)[0]

    with get_db() as connection:
        row = connection.execute(
            "SELECT * FROM users WHERE lower(email) = ?", (email,)
        ).fetchone()
        if row is None:
            try:
                cursor = connection.execute(
                    """
                    INSERT INTO users
                        (email, hashed_password, full_name, role,
                         email_verified, phone_verified)
                    VALUES (?, ?, ?, 'creator', 1, 0)
                    """,
                    (email, hash_password(secrets.token_urlsafe(32)), full_name.strip()),
                )
            except INTEGRITY_ERRORS as exc:
                raise HTTPException(
                    status_code=409,
                    detail="Không thể tạo tài khoản Google. Hãy thử đăng nhập lại.",
                ) from exc
            row = connection.execute(
                "SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
        elif not row["email_verified"]:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Email này đang chờ xác minh. Hãy hoàn tất xác minh email "
                    "hoặc thử đăng nhập bằng Google sau."
                ),
            )

    token = _set_auth_cookie(response, request, row)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": _public_user(row),
    }


@router.get("/me")
def me(user: dict = Depends(get_current_user)) -> dict:
    return user


@router.post("/logout")
def logout(response: Response, request: Request) -> dict[str, str]:
    response.delete_cookie(
        "cinai_access_token",
        path="/",
        secure=request.url.scheme == "https",
        httponly=True,
        samesite="lax",
    )
    return {"message": "Đã đăng xuất."}
