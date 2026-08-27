import hashlib
import hmac
import secrets

from fastapi import Header, HTTPException, status

from app.config import get_settings
from app.models import Device


def check_admin_password(password: str) -> bool:
    # compare_digest는 비-ASCII 문자가 섞인 str을 주면 TypeError를 던지므로
    # (한글 등이 섞여 들어오는 경우가 있음) bytes로 맞춰서 비교한다.
    return hmac.compare_digest(password.encode("utf-8"), get_settings().admin_password.encode("utf-8"))


def require_app_token(x_app_token: str = Header(...)) -> None:
    """모바일 앱용 JSON API 의존성 — 관리자 비밀번호를 앱 토큰으로 재사용한다."""
    if not check_admin_password(x_app_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid app token")


def generate_device_token() -> str:
    return secrets.token_urlsafe(24)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_device_token(device: Device, token: str) -> bool:
    return hmac.compare_digest(hash_token(token), device.token_hash)
