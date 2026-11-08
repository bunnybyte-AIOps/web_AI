import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.core.database import get_db

bearer_scheme = HTTPBearer(auto_error=False)
_PASSWORD_ITERATIONS = 600_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _PASSWORD_ITERATIONS
    )
    return f"pbkdf2_sha256${_PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    if stored_hash.startswith(("$2a$", "$2b$", "$2y$")):
        try:
            import bcrypt

            return bcrypt.checkpw(
                password.encode("utf-8"), stored_hash.encode("ascii")
            )
        except (ImportError, ValueError):
            return False
    try:
        algorithm, iterations, salt_hex, digest_hex = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        candidate = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(candidate.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def create_access_token(user_id: int, role: str) -> str:
    now = int(time.time())
    header = _b64encode(b'{"alg":"HS256","typ":"JWT"}')
    payload = _b64encode(
        json.dumps(
            {
                "sub": str(user_id),
                "role": role,
                "iat": now,
                "exp": now + settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            },
            separators=(",", ":"),
        ).encode("utf-8")
    )
    message = f"{header}.{payload}".encode("ascii")
    signature = hmac.new(
        settings.SECRET_KEY.encode("utf-8"), message, hashlib.sha256
    ).digest()
    return f"{header}.{payload}.{_b64encode(signature)}"


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        header_part, payload_part, signature_part = token.split(".")
        message = f"{header_part}.{payload_part}".encode("ascii")
        expected = hmac.new(
            settings.SECRET_KEY.encode("utf-8"), message, hashlib.sha256
        ).digest()
        padding = "=" * (-len(signature_part) % 4)
        actual = base64.urlsafe_b64decode(signature_part + padding)
        if not hmac.compare_digest(expected, actual):
            raise ValueError("Invalid token signature")
        payload_padding = "=" * (-len(payload_part) % 4)
        payload = json.loads(
            base64.urlsafe_b64decode(payload_part + payload_padding)
        )
        if int(payload["exp"]) <= int(time.time()):
            raise ValueError("Token expired")
        int(payload["sub"])
        return payload
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Phiên đăng nhập không hợp lệ hoặc đã hết hạn.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any]:
    token = (
        credentials.credentials
        if credentials is not None
        else request.cookies.get("cinai_access_token")
    )
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Vui lòng đăng nhập để tiếp tục.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_access_token(token)
    with get_db() as connection:
        row = connection.execute(
            """
            SELECT id, email, phone, email_verified, phone_verified, full_name, role
            FROM users WHERE id = ?
            """,
            (int(payload["sub"]),),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="Tài khoản không còn tồn tại.")
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


def require_project_owner(project_id: int, user_id: int) -> dict[str, Any]:
    with get_db() as connection:
        row = connection.execute(
            "SELECT * FROM projects WHERE id = ? AND user_id = ?",
            (project_id, user_id),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy dự án.")
    return dict(row)
