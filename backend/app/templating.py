from fastapi.templating import Jinja2Templates

from app.config import BACKEND_DIR
from app.services import to_kst

templates = Jinja2Templates(directory=str(BACKEND_DIR / "app" / "templates"))


def _kst_strftime(value, fmt: str) -> str:
    """템플릿에서 {{ value | kst(fmt) }}로 UTC 저장값을 KST로 포맷팅한다."""
    kst_value = to_kst(value)
    return kst_value.strftime(fmt) if kst_value is not None else ""


templates.env.filters["kst"] = _kst_strftime
