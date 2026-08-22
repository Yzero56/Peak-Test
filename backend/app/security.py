import hashlib
import hmac
import secrets

from fastapi import HTTPException, Request, status

from app.config import get_settings
from app.models import Device

SESSION_KEY = "authed"


def check_admin_password(password: str) -> bool:
    return hmac.compare_digest(password, get_settings().admin_password)


def log_in(request: Request) -> None:
    request.session[SESSION_KEY] = True


def log_out(request: Request) -> None:
    request.session.pop(SESSION_KEY, None)


def is_logged_in(request: Request) -> bool:
    return bool(request.session.get(SESSION_KEY))


def require_login(request: Request) -> None:
    """대시보드 HTML 라우트용 의존성 — 세션이 없으면 로그인 페이지로 리다이렉트."""
    if not is_logged_in(request):
        raise HTTPException(status_code=status.HTTP_302_FOUND, headers={"Location": "/login"})


def generate_device_token() -> str:
    return secrets.token_urlsafe(24)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_device_token(device: Device, token: str) -> bool:
    return hmac.compare_digest(hash_token(token), device.token_hash)
